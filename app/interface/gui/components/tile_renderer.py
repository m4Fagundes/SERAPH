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
    QPen, QColor, QBrush, QPolygonF,
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QObject, QRunnable, QThreadPool, pyqtSignal

from app.application.pixel_mask_service import PixelMaskService

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

        # Services
        self._pms = PixelMaskService()
        self._threadpool = QThreadPool()
        self._threadpool.setMaxThreadCount(2)

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

        # Convert PIL → QPixmap
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
        data = pil_img.tobytes("raw", "RGB")
        qim = QImage(data, pil_img.width, pil_img.height,
                      pil_img.width * 3, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qim)

        self._pixmap_item = QGraphicsPixmapItem(pix)
        self._pixmap_item.setZValue(0)
        self.scene.addItem(self._pixmap_item)

        # Scene rect = exactly the tile image dimensions
        self.scene.setSceneRect(0, 0, pil_img.width, pil_img.height)

        self._slice_idx = idx

        # Fit to viewport
        self._fit_view(pil_img.width, pil_img.height)

        # Rebuild pixel overlay
        self._rebuild_pixel_overlay(session, idx)

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

    def _rebuild_pixel_overlay(self, session, slice_idx: int) -> None:
        self._clear_pixel_overlay()
        if session is None or slice_idx is None:
            return
        if slice_idx >= len(session.tiles):
            return
        mask = session.tiles[slice_idx].pixel_mask
        if not mask:
            return

        remove_color = QColor(220, 30, 30, 160)
        brush = QBrush(remove_color)
        no_pen = QPen(Qt.PenStyle.NoPen)
        for (px, py) in mask:
            sx, sy = self._global_to_scene(px, py)
            item = QGraphicsRectItem(float(sx), float(sy), 1.0, 1.0)
            item.setBrush(brush)
            item.setPen(no_pen)
            item.setZValue(10)
            self.scene.addItem(item)
            self._pixel_overlay_items.append(item)

    # ── Rendering: Explicit background clear (OpenGL framebuffer pattern) ────
    def drawBackground(self, painter: QPainter, rect) -> None:
        """Explicitly clear the OpenGL framebuffer before any scene items are drawn."""
        painter.fillRect(rect, QColor("#1a1a1a"))

    # ── Rendering: Vector overlays on top of the tile pixmap ───────────────

    def drawForeground(self, painter: QPainter, rect):
        s = self.main_window.current_session
        if not s or self._slice_idx is None:
            return

        tile = s.tiles[self._slice_idx]

        left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()

        # ── Membrane Overlay ─────────────────────────────────────────────────
        show_membrane = True
        if hasattr(self.main_window, "chk_show_membrane"):
            show_membrane = self.main_window.chk_show_membrane.isChecked()

        if show_membrane and tile.polygon and len(tile.polygon) >= 3:
            poly_f = QPolygonF()
            for pt in tile.polygon:
                sx, sy = self._global_to_scene(pt[0], pt[1])
                poly_f.append(QPointF(sx, sy))

            base_color = QColor(tile.color)
            membrane_color = QColor(base_color)
            membrane_color.setAlpha(120)
            painter.setBrush(QBrush(membrane_color))
            border_pen = QPen(base_color, 0)  # cosmetic: always 1 screen pixel
            border_pen.setCosmetic(True)
            border_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(border_pen)
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

        idx = self._slice_idx
        tool = self.main_window.active_tool

        # ── Segment tool ─────────────────────────────────────────────────────
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

            sb = getattr(self.main_window, "statusBar", lambda: None)()
            if sb:
                sb.showMessage(f"Processing inference with {model_name}...")

            seg_service = self.main_window.segmentation_service
            worker = _SegWorker(seg_service, model_name, s, idx, gx, gy)
            worker.signals.finished.connect(
                lambda poly, _s=s, _idx=idx: self._on_seg_done(poly, _s, _idx)
            )
            worker.signals.error.connect(self._on_seg_error)
            self._threadpool.start(worker)
            return

        # ── Erase tool ───────────────────────────────────────────────────────
        if tool == "erase" and event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self._erase_at(event, s, idx)
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        s = self.main_window.current_session
        if not s or self._slice_idx is None:
            super().mouseMoveEvent(event)
            return

        tool = self.main_window.active_tool
        if tool == "erase" and (event.buttons() & Qt.MouseButton.LeftButton or event.buttons() & Qt.MouseButton.RightButton):
            self._erase_at(event, s, self._slice_idx)
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)

    # ----- Erase helper ------------------------------------------------------

    def _erase_at(self, event, session, idx):
        scene_pt = self.mapToScene(event.position().toPoint())
        gx, gy = self._scene_to_global(math.floor(scene_pt.x()), math.floor(scene_pt.y()))
        gx, gy = int(gx), int(gy)

        tile = session.tiles[idx]
        in_tile = any(r[0] <= gx < r[2] and r[1] <= gy < r[3] for r in tile.rects)
        if not in_tile:
            return

        # Push undo only on press (not continuous drag)
        if isinstance(event, QMouseEvent) and event.type().name == b"MouseButtonPress":
            undo = getattr(self.main_window, "undo_manager", None)
            if undo:
                undo.push(session, "pixel_mask_toggle")

        is_left = bool(
            (hasattr(event, "button") and event.button() == Qt.MouseButton.LeftButton)
            or (hasattr(event, "buttons") and event.buttons() & Qt.MouseButton.LeftButton)
        )
        mask = self._pms.get_mask(session, idx)
        if is_left:
            mask.add((gx, gy))
        else:
            mask.discard((gx, gy))

        sb = getattr(self.main_window, "statusBar", lambda: None)()
        if sb:
            sb.showMessage(f"Pixel ({gx}, {gy}) {'removed' if is_left else 'restored'}  |  mask: {len(mask)}")

        self._rebuild_pixel_overlay(session, idx)
        self.viewport().update()

    # ----- Segmentation callbacks --------------------------------------------

    def _on_seg_done(self, polygon: list, session, slice_idx: int):
        sb = getattr(self.main_window, "statusBar", lambda: None)()
        if polygon:
            session.tiles[slice_idx].polygon = polygon
            if sb:
                sb.showMessage(f"Segmentation successful: {len(polygon)} points.")
        else:
            if sb:
                sb.showMessage("Failed to find nucleus at coordinates.")
        self.viewport().update()

    def _on_seg_error(self, error_msg: str):
        logger.error("Inference failed: %s", error_msg)
        sb = getattr(self.main_window, "statusBar", lambda: None)()
        if sb:
            sb.showMessage("Inference failed.")
        self.viewport().update()
