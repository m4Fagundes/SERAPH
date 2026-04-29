"""
TileRenderer — Micro Context (Bounded Context: Isolated Tile Editing)

Architecture: Clean Architecture + DDD (python-patterns / architecture-patterns)
- This widget is a completely INDEPENDENT QGraphicsView with its OWN QGraphicsScene.
- It does NOT share scene, tiles, workers, or zoom state with the CanvasRenderer.
- It renders a SINGLE Tile entity from memory-resident PIL pixels (no pyramid access).
- All Segment/Erase tools live exclusively here (SRP).

Design Decision (python-patterns §4 — Separate concerns):
  routes → services → repos  ⟹  MainWindow → TileRenderer → Tile entity
"""

import logging
import math
import io
import time
from typing import Optional

import numpy as np

from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem,
)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import (
    QPainter, QPixmap, QImage, QWheelEvent, QMouseEvent,
    QPen, QColor, QBrush, QPolygonF, QFont,
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QObject, QRunnable, QThreadPool, pyqtSignal

from app.domain.geometry import is_point_in_polygon, get_polygon_centroid

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background worker for segmentation (reused pattern from canvas_renderer)
# ---------------------------------------------------------------------------

class _SegSignals(QObject):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)


class _SegWorker(QRunnable):
    """Off-thread inference — keeps the UI responsive."""

    def __init__(self, service, model_name, session, slice_idx, gx, gy):
        super().__init__()
        self.service = service
        self.model_name = model_name
        self.session = session
        self.slice_idx = slice_idx
        self.gx, self.gy = gx, gy
        self.signals = _SegSignals()

    def run(self):
        try:
            polygon = self.service.segment_at_point(
                self.model_name, self.session, self.slice_idx, self.gx, self.gy
            )
            self.signals.finished.emit(polygon)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.signals.error.emit(str(e))


class _BatchSegSignals(QObject):
    """Signals for batch segmentation worker."""
    finished = pyqtSignal(list)   # list of polygons
    error = pyqtSignal(str)


class _BatchSegWorker(QRunnable):
    """Off-thread batch inference — segments the entire tile at once."""

    def __init__(self, service, model_name, session, slice_idx,
                 diameter=None, flow_threshold=None, cellprob_threshold=None):
        super().__init__()
        self.service = service
        self.model_name = model_name
        self.session = session
        self.slice_idx = slice_idx
        self.diameter = diameter
        self.flow_threshold = flow_threshold
        self.cellprob_threshold = cellprob_threshold
        self.signals = _BatchSegSignals()

    def run(self):
        try:
            polygons = self.service.segment_tile(
                self.model_name, self.session, self.slice_idx,
                diameter=self.diameter,
                flow_threshold=self.flow_threshold,
                cellprob_threshold=self.cellprob_threshold,
            )
            self.signals.finished.emit(polygons)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.signals.error.emit(str(e))


class _NuclickAllWorker(QRunnable):
    """Off-thread batch inference — runs NuClick on centroids of existing segmentations."""

    def __init__(self, service, session, slice_idx, centroids):
        super().__init__()
        self.service = service
        self.session = session
        self.slice_idx = slice_idx
        self.centroids = centroids
        self.signals = _BatchSegSignals() # Reuse batch signals

    def run(self):
        try:
            # Send all centroids in a single batch to leverage GPU parallelism
            polygons = self.service.segment_at_points(
                "NuClick (PyTorch)", self.session, self.slice_idx, self.centroids
            )
            self.signals.finished.emit(polygons)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.signals.error.emit(str(e))


# ---------------------------------------------------------------------------
# TileRenderer — Independent Micro-Context Widget
# ---------------------------------------------------------------------------

class TileRenderer(QGraphicsView):
    """Self-contained viewer/editor for a single `Tile` entity.

    Lifecycle:
        1. ``load_tile(session, idx)`` extracts pixels via ``tile.load_pixels``
           and places a single QPixmap on an independent scene.
        2. The user can zoom/pan freely — no TileWorkers, no pyramid lookups.
        3. Segment and Erase tools modify the Tile entity directly.
        4. ``unload()`` clears the scene and releases memory.
    """

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        # Independent scene — shares NOTHING with CanvasRenderer
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.setViewport(QOpenGLWidget())
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # ── Architecture: Explicit GPU framebuffer clear ──────────────────────
        # Same pattern as CanvasRenderer: QOpenGLWidget retains the framebuffer
        # between frames. FullViewportUpdate forces a complete repaint each frame.
        from PyQt6.QtWidgets import QGraphicsView as _QGV
        self.setViewportUpdateMode(_QGV.ViewportUpdateMode.FullViewportUpdate)
        self.scene.setBackgroundBrush(QBrush(QColor("#1a1a1a")))

        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QGraphicsView { background-color: #1a1a1a; }")

        # Track mouse for brush preview
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        # Internal state
        self._slice_idx: Optional[int] = None
        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._pixel_overlay_items: list = []
        self._zoom = 1.0

        # Manual fine-tune stroke state
        self._current_stroke: list = []
        self._is_drawing_stroke: bool = False
        self._is_erasing_stroke: bool = False
        self._stroke_color_add = QColor(255, 255, 0, 180)  # Yellow with transparency
        self._stroke_color_erase = QColor(255, 0, 0, 180)  # Red with transparency

        # Services
        self._threadpool = QThreadPool()
        self._threadpool.setMaxThreadCount(2)

        # Processing state (loading overlay)
        self._processing = False

    # ----- public API -------------------------------------------------------

    @property
    def slice_idx(self) -> Optional[int]:
        return self._slice_idx

    def load_tile(self, session, idx: int) -> None:
        """Extract pixels from the pyramid into the Tile, then display them."""
        self.unload()
        if idx >= len(session.tiles):
            return

        tile = session.tiles[idx]
        pil_img = tile.load_pixels(session.pyramid)
        if pil_img is None:
            return

        # ── python-patterns §4 Separate concerns ─────────────────────────────
        # Domain entity owns the polygon geometry → delegates masking to Tile.
        # TileRenderer only handles format conversion and display.
        pil_img = tile.apply_polygon_mask(pil_img)

        # Convert PIL → QPixmap (RGBA if polygon-masked, RGB for grid tiles)
        if pil_img.mode == "RGBA":
            data = pil_img.tobytes("raw", "RGBA")
            qim = QImage(data, pil_img.width, pil_img.height,
                         pil_img.width * 4, QImage.Format.Format_RGBA8888)
        else:
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            data = pil_img.tobytes("raw", "RGB")
            qim = QImage(data, pil_img.width, pil_img.height,
                         pil_img.width * 3, QImage.Format.Format_RGB888)
                         
        qim.setDevicePixelRatio(1.0)
        pix = QPixmap.fromImage(qim)
        pix.setDevicePixelRatio(1.0)

        self._pixmap_item = QGraphicsPixmapItem(pix)
        self._pixmap_item.setZValue(0)
        self.scene.addItem(self._pixmap_item)

        # Scene rect = exactly the tile image dimensions
        self.scene.setSceneRect(0, 0, pil_img.width, pil_img.height)

        self._slice_idx = idx

        # Fit to viewport
        self._fit_view(pil_img.width, pil_img.height)

        # Switch tools
        self.main_window.update_tool_context(True)

    def unload(self) -> None:
        """Clear the scene and release tile memory."""
        if self._slice_idx is not None:
            s = self.main_window.current_session
            if s and self._slice_idx < len(s.tiles):
                s.tiles[self._slice_idx].clear_cache()
        self._clear_pixel_overlay()
        self.scene.clear()
        self._pixmap_item = None
        self._slice_idx = None

    # ----- private helpers ---------------------------------------------------

    def _fit_view(self, w: int, h: int) -> None:
        vw = self.viewport().width()
        vh = self.viewport().height()
        fit = min((vw * 0.9) / max(w, 1), (vh * 0.9) / max(h, 1), 5.0)
        self._zoom = fit
        self.resetTransform()
        self.scale(fit, fit)
        self.centerOn(w / 2, h / 2)

    # ---- Coordinate helpers ------------------------------------------------
    # The tile image is placed at scene (0,0). The Tile entity stores global
    # coordinates. We convert between the two using the bounding_box offset.

    def _global_offset(self):
        """Return (ox, oy) — the top-left corner of the tile in global coords."""
        s = self.main_window.current_session
        if s and self._slice_idx is not None and self._slice_idx < len(s.tiles):
            bb = s.tiles[self._slice_idx].bounding_box
            return bb[0], bb[1]
        return 0, 0

    def _scene_to_global(self, sx: float, sy: float):
        ox, oy = self._global_offset()
        return sx + ox, sy + oy

    def _global_to_scene(self, gx: float, gy: float):
        ox, oy = self._global_offset()
        return gx - ox, gy - oy

    # ---- Pixel overlay (scene items) ----------------------------------------

    def _clear_pixel_overlay(self):
        for item in self._pixel_overlay_items:
            if item.scene() == self.scene:
                self.scene.removeItem(item)
        self._pixel_overlay_items.clear()

    def _apply_circular_brush(self, event: QMouseEvent, is_erase: bool):
        """Apply brush stroke using numpy vectorized circular mask.

        Performance: O(1) mask computation via meshgrid instead of O(r²) Python loop.
        The old implementation iterated pixel-by-pixel causing CPU saturation and
        fan noise. This version generates the entire circular region as a numpy
        boolean mask, then batch-updates the pixel_mask set.
        """
        s = self.main_window.current_session
        if not s or self._slice_idx is None:
            return

        # Throttle to ~60 fps to prevent event-loop congestion
        now = time.monotonic()
        if now - getattr(self, '_last_brush_time', 0.0) < 0.016:
            return
        self._last_brush_time = now

        idx = self._slice_idx
        tile = s.tiles[idx]

        scene_pt = self.mapToScene(event.position().toPoint())
        gx, gy = self._scene_to_global(scene_pt.x(), scene_pt.y())

        radius = self.main_window.properties_dock.slider_brush_size.value()

        # Compute iteration bounds clipped to tile bounding box
        tbx1, tby1, tbx2, tby2 = tile.bounding_box
        bx1 = max(int(gx - radius), tbx1)
        by1 = max(int(gy - radius), tby1)
        bx2 = min(int(gx + radius) + 1, tbx2)
        by2 = min(int(gy + radius) + 1, tby2)

        if bx1 >= bx2 or by1 >= by2:
            return

        # ── Vectorized circular mask via numpy ────────────────────────────────
        xs = np.arange(bx1, bx2)
        ys = np.arange(by1, by2)
        xx, yy = np.meshgrid(xs, ys)
        dist_sq = (xx - gx) ** 2 + (yy - gy) ** 2
        circle_mask = dist_sq <= (radius * radius)

        # Build a rect-inclusion mask (which pixels belong to tile rects)
        rect_mask = np.zeros_like(circle_mask, dtype=bool)
        for r in tile.rects:
            rx_mask = (xx >= r[0]) & (xx < r[2])
            ry_mask = (yy >= r[1]) & (yy < r[3])
            rect_mask |= (rx_mask & ry_mask)

        valid = circle_mask & rect_mask
        # Extract affected pixel coordinates directly from the meshgrid
        affected_pixels = set(zip(xx[valid].tolist(), yy[valid].tolist()))

        if not affected_pixels:
            return

        # ── Batch set update ──────────────────────────────────────────────────
        old_size = len(tile.pixel_mask)
        if is_erase:
            tile.pixel_mask |= affected_pixels
        else:
            tile.pixel_mask -= affected_pixels

        if len(tile.pixel_mask) != old_size:
            self.viewport().update()

    def _refresh_membrane_controls(self):
        """Refresh the layer dropdown in the toolbar."""
        dropdown = getattr(self.main_window, "layer_dropdown", None)
        if dropdown:
            s = self.main_window.current_session
            if s and self._slice_idx is not None and self._slice_idx < len(s.tiles):
                dropdown.set_tile(s.tiles[self._slice_idx])
            else:
                dropdown.clear()


    # ── Rendering: Explicit background clear (OpenGL framebuffer pattern) ────
    def drawBackground(self, painter: QPainter, rect) -> None:
        """Explicitly clear the OpenGL framebuffer before any scene items are drawn."""
        painter.fillRect(rect, QColor("#1a1a1a"))

    # ── Rendering: Vector overlays on top of the tile pixmap ───────────────

    def drawForeground(self, painter: QPainter, rect):
        s = self.main_window.current_session
        if not s or self._slice_idx is None:
            # Still draw loading overlay if processing
            if self._processing:
                self._draw_loading_overlay(painter, rect)
            return

        tile = s.tiles[self._slice_idx]

        left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()

        # ── Membrane Overlay (segmentation layers) ─────────────────────────────
        show_membrane = True
        if hasattr(self.main_window, "chk_show_membrane"):
            show_membrane = self.main_window.chk_show_membrane.isChecked()

        if show_membrane:
            for poly, color_hex in tile.get_visible_polygons():
                base_color = QColor(color_hex)
                membrane_color = QColor(base_color)
                membrane_color.setAlpha(120)
                painter.setBrush(QBrush(membrane_color))

                border_pen = QPen(base_color, 0)
                border_pen.setCosmetic(True)
                border_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(border_pen)

                poly_f = QPolygonF()
                for pt in poly:
                    sx, sy = self._global_to_scene(pt[0], pt[1])
                    poly_f.append(QPointF(sx, sy))
                painter.drawPolygon(poly_f)

        # ── Pixel removal overlay (batch QPainterPath for performance) ────────
        if tile.pixel_mask:
            fill_color = QColor(210, 40, 40, 160)
            painter.setBrush(QBrush(fill_color))
            painter.setPen(Qt.PenStyle.NoPen)

            # Batch all pixel rects into a single QPainterPath for one draw call
            from PyQt6.QtGui import QPainterPath
            path = QPainterPath()
            ox, oy = self._global_offset()
            for (px, py) in tile.pixel_mask:
                path.addRect(QRectF(float(px - ox), float(py - oy), 1.0, 1.0))
            painter.drawPath(path)

        # ── Pixel grid (visible at high zoom) ────────────────────────────────
        if self._zoom >= 4.0:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            grid_color = QColor(200, 200, 200, 55)
            pen = QPen(grid_color, 0.0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            sr = self.scene.sceneRect()
            px_left = max(0, math.floor(left))
            px_top = max(0, math.floor(top))
            px_right = min(int(sr.width()), math.ceil(right) + 1)
            px_bottom = min(int(sr.height()), math.ceil(bottom) + 1)

            if (px_right - px_left) < 800 and (px_bottom - px_top) < 800:
                for x in range(px_left, px_right + 1):
                    painter.drawLine(QPointF(x, float(px_top)), QPointF(x, float(px_bottom)))
                for y in range(px_top, px_bottom + 1):
                    painter.drawLine(QPointF(float(px_left), y), QPointF(float(px_right), y))

        # ── Loading overlay (drawn on top of everything) ──────────────────
        if self._processing:
            self._draw_loading_overlay(painter, rect)
            
        # ── Brush Tool Preview ───────────────────────────────────────────────
        tool = getattr(self.main_window, "active_tool", None)
        if tool in ("brush_eraser", "brush_select") and hasattr(self, '_last_mouse_scene_pt') and self._last_mouse_scene_pt is not None:
            radius = self.main_window.properties_dock.slider_brush_size.value()
            pt = self._last_mouse_scene_pt
            color = QColor(255, 50, 50, 100) if tool == "brush_eraser" else QColor(50, 255, 50, 100)
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.GlobalColor.white, 1.0 / max(self._zoom, 1)))
            painter.drawEllipse(pt, radius, radius)

    # ----- Input: Zoom -------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent):
        # Allow adjusting brush size with Shift + Scroll
        if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            tool = getattr(self.main_window, "active_tool", None)
            if tool in ("brush_eraser", "brush_select"):
                delta = 1 if event.angleDelta().y() > 0 else -1
                current_size = self.main_window.properties_dock.slider_brush_size.value()
                # Change faster if size is larger
                step = 2 if current_size < 20 else 5
                new_size = max(1, min(500, current_size + delta * step))
                self.main_window.properties_dock.slider_brush_size.setValue(new_size)
                self.viewport().update()
                return

        zoom_factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        new_zoom = self._zoom * zoom_factor
        new_zoom = max(0.05, min(new_zoom, 200.0))

        old_pos = self.mapToScene(event.position().toPoint())
        self._zoom = new_zoom
        self.resetTransform()
        self.scale(new_zoom, new_zoom)

        new_pos = self.mapFromScene(old_pos)
        delta = new_pos - event.position().toPoint()
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + delta.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + delta.y())

        self.viewport().update()

    # ----- Input: Mouse events -----------------------------------------------

    def mousePressEvent(self, event: QMouseEvent):
        s = self.main_window.current_session
        if not s or self._slice_idx is None:
            super().mousePressEvent(event)
            return

        # Block all interaction while processing
        if self._processing:
            return

        idx = self._slice_idx
        tool = self.main_window.active_tool

        model_name = self.main_window.combo_model.currentText()

        # Check if clicked inside an existing segmentation to remove it (works for ML tools, but NOT for Manual Fine Tune)
        if tool == "segment" and model_name != "🖌️ Manual Fine Tune" and event.button() == Qt.MouseButton.LeftButton:
            scene_pt = self.mapToScene(event.position().toPoint())
            gx, gy = self._scene_to_global(math.floor(scene_pt.x()), math.floor(scene_pt.y()))
            gx, gy = int(gx), int(gy)

            tile = s.tiles[idx]
            for layer in tile.segmentation_layers:
                # Only allow removing polygons from VISIBLE layers.
                # Hidden layers are untouchable — the user can't see them,
                # so clicking "through" them must trigger a new segmentation.
                if not layer.get("visible", True):
                    continue
                for pi, poly in enumerate(layer.get("polygons", [])):
                    if is_point_in_polygon(gx, gy, poly):
                        layer["polygons"].pop(pi)
                        # Remove empty layers
                        if not layer["polygons"]:
                            tile.segmentation_layers.remove(layer)
                        sb = getattr(self.main_window, "statusBar", lambda: None)()
                        if sb:
                            sb.showMessage("Segmentation removed.")
                        self._refresh_membrane_controls()
                        self.viewport().update()
                        return

        # ── Manual Fine Tune tool ─────────────────────────────────────────────
        if tool == "segment" and model_name == "🖌️ Manual Fine Tune":
            if event.button() == Qt.MouseButton.LeftButton:
                self._start_stroke(event, s, idx, False)
                return
            elif event.button() == Qt.MouseButton.RightButton:
                self._start_stroke(event, s, idx, True)
                return

        # ── Eraser & Selection Brush ──────────────────────────────────────────
        if tool in ("brush_eraser", "brush_select"):
            if event.button() == Qt.MouseButton.LeftButton:
                undo = getattr(self.main_window, "undo_manager", None)
                if undo:
                    undo.push(s, tool)
                self._apply_circular_brush(event, tool == "brush_eraser")
                self._is_brushing = True
                self._brushing_button = Qt.MouseButton.LeftButton
            elif event.button() == Qt.MouseButton.RightButton:
                undo = getattr(self.main_window, "undo_manager", None)
                if undo:
                    undo.push(s, tool)
                self._apply_circular_brush(event, tool != "brush_eraser")
                self._is_brushing = True
                self._brushing_button = Qt.MouseButton.RightButton
            return

        # ── Segment tool (regular segmentation models) ───────────────────────
        if tool == "segment" and event.button() == Qt.MouseButton.LeftButton:
            scene_pt = self.mapToScene(event.position().toPoint())
            gx, gy = self._scene_to_global(math.floor(scene_pt.x()), math.floor(scene_pt.y()))
            gx, gy = int(gx), int(gy)

            tile = s.tiles[idx]
            in_tile = any(r[0] <= gx < r[2] and r[1] <= gy < r[3] for r in tile.rects)
            if not in_tile:
                super().mousePressEvent(event)
                return

            model_name = self.main_window.combo_model.currentText()
            if not model_name:
                return

            # Route to the correct service based on model type
            batch_service = self.main_window.batch_segmentation_service
            
            if model_name == "🧠 Nuclick All":
                self.run_nuclick_all(s, idx, self.main_window.segmentation_service)
                return
                
            if batch_service.is_batch_model(model_name):
                # Read parameters from main_window spinboxes
                diameter = self.main_window.spin_diameter.value()
                if diameter == 0.0:
                    diameter = None
                flow_threshold = self.main_window.spin_flow.value()
                cellprob_threshold = self.main_window.spin_cellprob.value()
                # Batch model: segment the entire tile at once
                self.run_batch_segmentation(
                    model_name, s, idx, batch_service,
                    diameter=diameter,
                    flow_threshold=flow_threshold,
                    cellprob_threshold=cellprob_threshold,
                )
                return

            sb = getattr(self.main_window, "statusBar", lambda: None)()
            if sb:
                sb.showMessage(f"Processing inference with {model_name}...")

            seg_service = self.main_window.segmentation_service
            worker = _SegWorker(seg_service, model_name, s, idx, gx, gy)
            worker.signals.finished.connect(
                lambda poly, _s=s, _idx=idx, _m=model_name: self._on_seg_done(poly, _s, _idx, _m)
            )
            worker.signals.error.connect(self._on_seg_error)
            self._threadpool.start(worker)
            return


        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        s = self.main_window.current_session
        if not s or self._slice_idx is None:
            super().mouseMoveEvent(event)
            return

        tool = self.main_window.active_tool
        model_name = self.main_window.combo_model.currentText()
        
        # Track mouse for brush preview
        self._last_mouse_scene_pt = self.mapToScene(event.position().toPoint())
        if tool in ("brush_eraser", "brush_select"):
            if self.viewport().cursor().shape() != Qt.CursorShape.BlankCursor:
                self.viewport().setCursor(Qt.CursorShape.BlankCursor)
                
            if getattr(self, "_is_brushing", False):
                is_erase = tool == "brush_eraser"
                if getattr(self, "_brushing_button", Qt.MouseButton.LeftButton) == Qt.MouseButton.RightButton:
                    is_erase = not is_erase
                self._apply_circular_brush(event, is_erase)
            self.viewport().update()
        else:
            if self.viewport().cursor().shape() == Qt.CursorShape.BlankCursor:
                self.viewport().unsetCursor()

        # Manual Fine Tune stroke drawing
        if tool == "segment" and model_name == "🖌️ Manual Fine Tune" and self._is_drawing_stroke:
            self._continue_stroke(event, s, self._slice_idx)
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        tool = self.main_window.active_tool
        model_name = self.main_window.combo_model.currentText()

        if tool in ("brush_eraser", "brush_select") and getattr(self, "_is_brushing", False):
            self._is_brushing = False
            return

        # Manual Fine Tune stroke completion
        if tool == "segment" and model_name == "🖌️ Manual Fine Tune" and self._is_drawing_stroke:
            self._is_drawing_stroke = False
            self._current_stroke = []
            return

        super().mouseReleaseEvent(event)


    def leaveEvent(self, event):
        self._last_mouse_scene_pt = None
        self.viewport().update()
        super().leaveEvent(event)

    # ----- Manual Fine Tune stroke helpers -----------------------------------

    def _start_stroke(self, event: QMouseEvent, session, idx: int, is_erase: bool):
        """Start a new manual fine-tune stroke and apply instantly."""
        scene_pt = self.mapToScene(event.position().toPoint())
        gx, gy = self._scene_to_global(math.floor(scene_pt.x()), math.floor(scene_pt.y()))
        gx, gy = int(gx), int(gy)

        tile = session.tiles[idx]
        in_tile = any(r[0] <= gx < r[2] and r[1] <= gy < r[3] for r in tile.rects)
        if not in_tile:
            return

        self._current_stroke = [(gx, gy)]
        self._is_drawing_stroke = True
        self._is_erasing_stroke = is_erase

        # Push undo state once per drag
        undo = getattr(self.main_window, "undo_manager", None)
        if undo:
            undo.push(session, "manual_fine_tune")

        self._apply_instant_fine_tune(session, idx, [(gx, gy)])

    def _continue_stroke(self, event: QMouseEvent, session, idx: int):
        """Continue drawing the current stroke and apply instantly."""
        scene_pt = self.mapToScene(event.position().toPoint())
        gx, gy = self._scene_to_global(math.floor(scene_pt.x()), math.floor(scene_pt.y()))
        gx, gy = int(gx), int(gy)

        tile = session.tiles[idx]
        in_tile = any(r[0] <= gx < r[2] and r[1] <= gy < r[3] for r in tile.rects)
        if not in_tile:
            return

        if self._current_stroke and self._current_stroke[-1] == (gx, gy):
            return  # Didn't move to a new pixel

        self._current_stroke.append((gx, gy))
        self._apply_instant_fine_tune(session, idx, [(gx, gy)])

    def _apply_instant_fine_tune(self, session, idx: int, points: list):
        """Perform fine-tuning pixel calculation and update instantly."""
        s = session
        tile = s.tiles[idx]
        if not tile.rects:
            return

        bx1, by1, bx2, by2 = tile.bounding_box
        tile_width = bx2 - bx1
        tile_height = by2 - by1

        local_stroke = [(x - bx1, y - by1) for x, y in points]

        # Collect ALL polygons from ALL visible layers into a flat list
        all_polys = []
        poly_to_layer = []  # track which layer each poly belongs to
        for li, layer in enumerate(tile.segmentation_layers):
            for poly in layer.get("polygons", []):
                if poly and len(poly) >= 3:
                    local_poly = [(px - bx1, py - by1) for (px, py) in poly]
                    all_polys.append(local_poly)
                    poly_to_layer.append(li)

        if not all_polys:
            return

        service = self.main_window.manual_adjustment_service
        updated_local_polygons = service.apply_fine_tune(
            stroke_points=local_stroke,
            segmentations=all_polys,
            image_width=tile_width,
            image_height=tile_height,
            target_idx=None,
            is_erase=self._is_erasing_stroke
        )

        # Convert back to GLOBAL coords and redistribute to layers
        # Clear all layers' polygons first, then re-add
        layer_polys = {li: [] for li in range(len(tile.segmentation_layers))}
        for i, local_poly in enumerate(updated_local_polygons):
            global_poly = [(px + bx1, py + by1) for (px, py) in local_poly]
            if i < len(poly_to_layer):
                layer_polys[poly_to_layer[i]].append(global_poly)
            else:
                # New polygon from fine-tune → add to Manual layer
                manual_li = self._find_or_create_manual_layer(tile)
                layer_polys.setdefault(manual_li, []).append(global_poly)

        for li, polys in layer_polys.items():
            if li < len(tile.segmentation_layers):
                tile.segmentation_layers[li]["polygons"] = polys

        # Remove empty layers
        tile.segmentation_layers = [l for l in tile.segmentation_layers if l.get("polygons")]
        
        sb = getattr(self.main_window, "statusBar", lambda: None)()
        if sb:
            sb.showMessage("Pixel edited.")

        self._refresh_membrane_controls()
        self.viewport().update()

    def _find_or_create_manual_layer(self, tile) -> int:
        """Find existing Manual Fine Tune layer or create one. Returns layer index."""
        for i, layer in enumerate(tile.segmentation_layers):
            if "manual" in layer.get("model", "").lower():
                return i
        from app.domain.tile import LAYER_COLORS
        tile.add_layer("Manual Fine Tune", "manual_fine_tune", [], "#00FF88")
        return len(tile.segmentation_layers) - 1


    # ----- Segmentation callbacks --------------------------------------------

    def _on_seg_done(self, polygon: list, session, slice_idx: int, model_name: str = "Unknown"):
        """Single-polygon segmentation completed (e.g. NuClick click)."""
        sb = getattr(self.main_window, "statusBar", lambda: None)()
        if polygon:
            tile = session.tiles[slice_idx]
            # Find existing layer for this model, or create a new one
            layer_found = False
            for layer in tile.segmentation_layers:
                if layer.get("model", "").lower() == model_name.lower():
                    layer["polygons"].append(polygon)
                    layer_found = True
                    break
            if not layer_found:
                tile.add_layer(model_name, model_name, [polygon])
            if sb:
                sb.showMessage(f"Segmentation successful: {len(polygon)} points.")
            self._refresh_membrane_controls()
        else:
            if sb:
                sb.showMessage("Failed to find nucleus at coordinates.")
        self.viewport().update()

    def _on_seg_error(self, error_msg: str):
        logger.error("Inference failed: %s", error_msg)
        self._processing = False
        sb = getattr(self.main_window, "statusBar", lambda: None)()
        if sb:
            sb.showMessage("Inference failed.")
        self.viewport().update()

    # ----- Batch segmentation ------------------------------------------------

    def run_batch_segmentation(
        self, model_name: str, session, slice_idx: int, service,
        diameter=None, flow_threshold=None, cellprob_threshold=None,
    ) -> None:
        """Launch batch segmentation on the entire tile in a background thread.

        Called from the MainWindow when the user clicks 'Segment All'.
        """
        if self._processing:
            return  # prevent double-clicks

        self._processing = True
        self.viewport().update()  # trigger overlay redraw

        sb = getattr(self.main_window, "statusBar", lambda: None)()
        if sb:
            sb.showMessage(
                f"Running batch segmentation ({model_name})... please wait."
            )

        import time
        start_time = time.monotonic()
        if hasattr(self.main_window, "lbl_execution_time"):
            self.main_window.lbl_execution_time.setText("⏱️ Processando...")
            self.main_window.lbl_execution_time.setStyleSheet("color: #F1C40F; font-weight: bold; font-family: 'Segoe UI', sans-serif; font-size: 9pt; margin-left: 8px;")
            self.main_window.lbl_execution_time.show()

        worker = _BatchSegWorker(
            service, model_name, session, slice_idx,
            diameter=diameter,
            flow_threshold=flow_threshold,
            cellprob_threshold=cellprob_threshold,
        )
        worker.signals.finished.connect(
            lambda polys, _s=session, _idx=slice_idx, _m=model_name, _t=start_time: self._on_batch_seg_done(
                polys, _s, _idx, _m, _t
            )
        )
        worker.signals.error.connect(self._on_seg_error)
        self._threadpool.start(worker)

    def _on_batch_seg_done(
        self, polygons: list, session, slice_idx: int, model_name: str = "Unknown", start_time: float = None
    ) -> None:
        """Callback when batch segmentation finishes successfully."""
        self._processing = False
        sb = getattr(self.main_window, "statusBar", lambda: None)()
        
        time_msg = ""
        if start_time is not None:
            import time
            elapsed = time.monotonic() - start_time
            time_msg = f" em {elapsed:.2f}s"
            if hasattr(self.main_window, "lbl_execution_time"):
                if polygons:
                    self.main_window.lbl_execution_time.setText(f"⏱️ {len(polygons)} núcleos detectados em {elapsed:.2f}s")
                    self.main_window.lbl_execution_time.setStyleSheet("color: #00FF88; font-weight: bold; font-family: 'Segoe UI', sans-serif; font-size: 9pt; margin-left: 8px;")
                else:
                    self.main_window.lbl_execution_time.setText(f"⏱️ 0 núcleos em {elapsed:.2f}s")
                    self.main_window.lbl_execution_time.setStyleSheet("color: #E74C3C; font-weight: bold; font-family: 'Segoe UI', sans-serif; font-size: 9pt; margin-left: 8px;")
                self.main_window.lbl_execution_time.show()

        if polygons:
            tile = session.tiles[slice_idx]
            # Always create a NEW layer for batch runs
            tile.add_layer(model_name, model_name, polygons)
            if sb:
                sb.showMessage(
                    f"Batch segmentation: {len(polygons)} núcleos detectados{time_msg}."
                )
            self._refresh_membrane_controls()
        else:
            if sb:
                sb.showMessage(f"Batch segmentation retornou 0 resultados{time_msg}.")
        self.viewport().update()

    def run_nuclick_all(self, session, slice_idx: int, seg_service) -> None:
        """Run Nuclick on the centroid of every existing visible polygon."""
        if self._processing:
            return

        tile = session.tiles[slice_idx]
        
        # Get all centroids of visible polygons
        centroids = []
        for poly, _ in tile.get_visible_polygons():
            centroids.append(get_polygon_centroid(poly))
            
        if not centroids:
            sb = getattr(self.main_window, "statusBar", lambda: None)()
            if sb:
                sb.showMessage("No visible segmentations found to process with Nuclick.")
            return

        self._processing = True
        self.viewport().update()

        sb = getattr(self.main_window, "statusBar", lambda: None)()
        if sb:
            sb.showMessage(f"Running Nuclick on {len(centroids)} cells... please wait.")

        import time
        start_time = time.monotonic()
        if hasattr(self.main_window, "lbl_execution_time"):
            self.main_window.lbl_execution_time.setText(f"⏱️ Processando {len(centroids)} núcleos...")
            self.main_window.lbl_execution_time.setStyleSheet("color: #F1C40F; font-weight: bold; font-family: 'Segoe UI', sans-serif; font-size: 9pt; margin-left: 8px;")
            self.main_window.lbl_execution_time.show()

        worker = _NuclickAllWorker(seg_service, session, slice_idx, centroids)
        worker.signals.finished.connect(
            lambda polys, _s=session, _idx=slice_idx, _m="Nuclick All", _t=start_time: self._on_batch_seg_done(
                polys, _s, _idx, _m, _t
            )
        )
        worker.signals.error.connect(self._on_seg_error)
        self._threadpool.start(worker)

    # ----- Loading overlay ---------------------------------------------------

    def _draw_loading_overlay(self, painter: QPainter, rect) -> None:
        """Draw a semi-transparent overlay with a 'Processing...' message."""
        # Semi-transparent dark background
        overlay_color = QColor(0, 0, 0, 160)
        painter.fillRect(rect, overlay_color)

        # Text
        painter.setPen(QPen(QColor(255, 255, 255, 230)))
        font = QFont("Segoe UI", 14, QFont.Weight.Bold)
        painter.setFont(font)

        # Center text in visible viewport (use viewport rect, not scene rect)
        vp_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        painter.drawText(
            vp_rect, Qt.AlignmentFlag.AlignCenter,
            "🔬 Processing...\nPlease wait",
        )
