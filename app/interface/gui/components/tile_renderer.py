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
from typing import Optional

from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem,
)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import (
    QPainter, QPixmap, QImage, QWheelEvent, QMouseEvent,
    QPen, QColor, QBrush, QPolygonF, QFont,
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QObject, QRunnable, QThreadPool, pyqtSignal

from app.domain.geometry import is_point_in_polygon

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

        # ── Membrane Overlay (Múltiplas segmentações) ─────────────────────────
        show_membrane = True
        if hasattr(self.main_window, "chk_show_membrane"):
            show_membrane = self.main_window.chk_show_membrane.isChecked()

        if show_membrane and hasattr(s, "segmentations"):
            for seg in s.segmentations:
                poly = seg.get("polygon", seg) if isinstance(seg, dict) else seg
                model = seg.get("model", "Imported") if isinstance(seg, dict) else "Imported"
                
                base_color = QColor("#FFFF00") # Default / Imported
                if "nuclick" in model.lower():
                    base_color = QColor("#00FFFF") # Cyan
                elif "cellpose" in model.lower():
                    base_color = QColor("#FF00FF") # Magenta

                membrane_color = QColor(base_color)
                membrane_color.setAlpha(120)
                painter.setBrush(QBrush(membrane_color))
                
                border_pen = QPen(base_color, 0)
                border_pen.setCosmetic(True)
                border_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(border_pen)
                
                if len(poly) >= 3:
                    poly_f = QPolygonF()
                    for pt in poly:
                        sx, sy = self._global_to_scene(pt[0], pt[1])
                        poly_f.append(QPointF(sx, sy))
                    painter.drawPolygon(poly_f)

        # ── Pixel removal borders ────────────────────────────────────────────
        if tile.pixel_mask:
            border_pen = QPen(QColor(210, 40, 40, 230), 0.08 / max(self._zoom, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(border_pen)
            for (px, py) in tile.pixel_mask:
                sx, sy = self._global_to_scene(px, py)
                painter.drawRect(QRectF(float(sx), float(sy), 1.0, 1.0))

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

    # ----- Input: Zoom -------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent):
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
        if tool == "segment" and model_name != "🖌️ Manual Fine Tune" and event.button() == Qt.MouseButton.LeftButton and hasattr(s, "segmentations"):
            scene_pt = self.mapToScene(event.position().toPoint())
            gx, gy = self._scene_to_global(math.floor(scene_pt.x()), math.floor(scene_pt.y()))
            gx, gy = int(gx), int(gy)

            for idx_seg, seg in enumerate(s.segmentations):
                poly = seg.get("polygon", seg) if isinstance(seg, dict) else seg
                if is_point_in_polygon(gx, gy, poly):
                    s.segmentations.pop(idx_seg)
                    sb = getattr(self.main_window, "statusBar", lambda: None)()
                    if sb:
                        sb.showMessage("Segmentation removed.")
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

        # Manual Fine Tune stroke drawing
        if tool == "segment" and model_name == "🖌️ Manual Fine Tune" and self._is_drawing_stroke:
            self._continue_stroke(event, s, self._slice_idx)
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        tool = self.main_window.active_tool
        model_name = self.main_window.combo_model.currentText()

        # Manual Fine Tune stroke completion
        if tool == "segment" and model_name == "🖌️ Manual Fine Tune" and self._is_drawing_stroke:
            self._is_drawing_stroke = False
            self._current_stroke = []
            return

        super().mouseReleaseEvent(event)


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

        # Extract current polygon list (convert to LOCAL coords!)
        old_segmentations = []
        if hasattr(s, "segmentations"):
            old_segmentations = s.segmentations

        poly_list = []
        for seg in old_segmentations:
            poly = seg.get("polygon", seg) if isinstance(seg, dict) else seg
            if not poly or len(poly) < 3:
                continue
            local_poly = [(px - bx1, py - by1) for (px, py) in poly]
            poly_list.append(local_poly)

        service = self.main_window.manual_adjustment_service
        updated_local_polygons = service.apply_fine_tune(
            stroke_points=local_stroke,
            segmentations=poly_list,
            image_width=tile_width,
            image_height=tile_height,
            target_idx=None,
            is_erase=self._is_erasing_stroke
        )

        # Convert back to GLOBAL coords
        updated_polygons = []
        for local_poly in updated_local_polygons:
            global_poly = [(px + bx1, py + by1) for (px, py) in local_poly]
            updated_polygons.append(global_poly)

        # Rebuild metadata for the updated segmentations
        new_segmentations = []
        # Find which polygons match the old ones, or just assign new models if counts don't align
        for new_poly in updated_polygons:
            found_meta = {"polygon": new_poly, "model": "Manual Fine Tune"}
            
            # Revert local coordinate matching check for metadata preservation
            for old_seg in old_segmentations:
                old_poly = old_seg.get("polygon", old_seg) if isinstance(old_seg, dict) else old_seg
                # if exact length match, let's keep metadata... or simply always use Manual Fine Tune for all!
                if new_poly == old_poly:
                    found_meta = old_seg
                    break
            new_segmentations.append(found_meta)

        s.segmentations = new_segmentations
        
        sb = getattr(self.main_window, "statusBar", lambda: None)()
        if sb:
            sb.showMessage("Pixel edited.")

        self.viewport().update()


    # ----- Segmentation callbacks --------------------------------------------

    def _on_seg_done(self, polygon: list, session, slice_idx: int, model_name: str = "Unknown"):
        sb = getattr(self.main_window, "statusBar", lambda: None)()
        if polygon:
            if not hasattr(session, "segmentations"):
                session.segmentations = []
            session.segmentations.append({"polygon": polygon, "model": model_name})
            if sb:
                sb.showMessage(f"Segmentation successful: {len(polygon)} points.")
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

        worker = _BatchSegWorker(
            service, model_name, session, slice_idx,
            diameter=diameter,
            flow_threshold=flow_threshold,
            cellprob_threshold=cellprob_threshold,
        )
        worker.signals.finished.connect(
            lambda polys, _s=session, _idx=slice_idx, _m=model_name: self._on_batch_seg_done(
                polys, _s, _idx, _m
            )
        )
        worker.signals.error.connect(self._on_seg_error)
        self._threadpool.start(worker)

    def _on_batch_seg_done(
        self, polygons: list, session, slice_idx: int, model_name: str = "Unknown"
    ) -> None:
        """Callback when batch segmentation finishes successfully."""
        self._processing = False
        sb = getattr(self.main_window, "statusBar", lambda: None)()
        if polygons:
            if not hasattr(session, "segmentations"):
                session.segmentations = []
            session.segmentations.extend([{"polygon": p, "model": model_name} for p in polygons])
            if sb:
                sb.showMessage(
                    f"Batch segmentation: {len(polygons)} nuclei detected."
                )
        else:
            if sb:
                sb.showMessage("Batch segmentation returned no results.")
        self.viewport().update()

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
