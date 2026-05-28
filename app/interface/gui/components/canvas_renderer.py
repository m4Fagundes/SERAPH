import logging
import math
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem, QApplication
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import QPainter, QPixmap, QImage, QWheelEvent, QMouseEvent, QPen, QColor, QBrush, QPolygonF
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QObject, QRunnable, QThreadPool
import io
import time
from PIL import Image
from app.domain.selection import subtract_from_slice
from app.application.pixel_mask_service import PixelMaskService
from app.domain.geometry import is_point_in_polygon

logger = logging.getLogger(__name__)

class WorkerSignals(QObject):
    result = pyqtSignal(tuple, object)

class SegmentationSignals(QObject):
    """Signals emitted by the background segmentation worker."""
    finished = pyqtSignal(list)   # polygon in global coords
    error = pyqtSignal(str)

class SegmentationWorker(QRunnable):
    """Runs interactive segmentation inference off the main thread."""

    def __init__(self, segmentation_service, model_name, session, slice_idx, gx, gy):
        super().__init__()
        self.segmentation_service = segmentation_service
        self.model_name = model_name
        self.session = session
        self.slice_idx = slice_idx
        self.gx = gx
        self.gy = gy
        self.signals = SegmentationSignals()

    def run(self):
        try:
            print(f"[SegmentationWorker] Starting inference: model={self.model_name}, "
                  f"slice={self.slice_idx}, click=({self.gx},{self.gy})", flush=True)
            polygon = self.segmentation_service.segment_at_point(
                self.model_name, self.session, self.slice_idx, self.gx, self.gy
            )
            print(f"[SegmentationWorker] Result: {len(polygon)} polygon points", flush=True)
            self.signals.finished.emit(polygon)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.signals.error.emit(str(e))

class TileWorker(QRunnable):
    def __init__(self, session, col, row, zoom, tile_size):
        super().__init__()
        self.session = session
        self.col = col
        self.row = row
        self.zoom = zoom
        self.tile_size = tile_size
        self.signals = WorkerSignals()

    def run(self):
        try:
            # Fast bailout if session is unloaded
            if not self.session.pyramid_ready: return
            
            pil_img = self.session.pyramid.get_tile(self.col, self.row, self.zoom, self.tile_size)
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            data = pil_img.tobytes("raw", "RGB")
            qim = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGB888).copy()
            qim.setDevicePixelRatio(1.0)
            pix = QPixmap.fromImage(qim)
            pix.setDevicePixelRatio(1.0)
            self.signals.result.emit((self.col, self.row, self.zoom), pix)
        except Exception as e:
            logger.error(f"TileWorker error coords {self.col},{self.row}: {e}")

class CanvasRenderer(QGraphicsView):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        self.setViewport(QOpenGLWidget())
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        
        # ── Architecture: Explicit GPU framebuffer clear ──────────────────────
        # QOpenGLWidget does NOT auto-clear the framebuffer between frames.
        # FullViewportUpdate forces the ENTIRE viewport to repaint each frame,
        # preventing ghost tile residues from prior zoom levels bleeding through.
        from PyQt6.QtWidgets import QGraphicsView as _QGV
        self.setViewportUpdateMode(_QGV.ViewportUpdateMode.FullViewportUpdate)
        
        # Scene background brush: solid dark fill as GPU-level fallback.
        # drawBackground() below overrides this for OpenGL, but the brush
        # covers any non-OpenGL fallback paths.
        self.scene.setBackgroundBrush(QBrush(QColor("#111111")))
        
        # Default Tool: Pan
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.active_tool = "grid"
        
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Connect pan dragging events to the tile loader pipeline
        self.verticalScrollBar().valueChanged.connect(lambda _: self.redraw())
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.redraw())
        
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(4)
        
        self.TILE_SIZE = 256
        self.tile_items = {}
        
        self._brush_points = []
        self._rect_drag_start = None
        
        # Local view matrix properties to allow multiple independent windows
        self.viewport_zoom = 1.0 
        self._isolated_slice_idx = None
        
        # Shared pixel mask service (stateless, safe to reuse across events)
        self._pms = PixelMaskService()

        # Scene items that represent removed pixels.
        # Stored here so we can surgically add/remove them without a full redraw.
        # Using QGraphicsRectItem (scene-space) instead of drawForeground (QPainter/OpenGL)
        # ensures pixel-perfect alignment with the image bitmap below.
        self._pixel_overlay_items: list = []

    def on_session_closed(self):
        """Call immediately after scene.clear() when a session is closed.

        scene.clear() destroys all C++ QGraphicsItem objects, so we must NOT
        call item.scene() or any Qt method on stale wrappers afterwards.
        Simply drop the Python references so _do_redraw starts clean.
        """
        self.tile_items.clear()
        self._pixel_overlay_items.clear()
        # Reset zoom tracking so the eviction loop won't iterate stale items
        # on the first redraw of the new session.
        self._last_tile_zoom = None

    @property
    def isolated_slice_idx(self):
        return self._isolated_slice_idx

    @isolated_slice_idx.setter
    def isolated_slice_idx(self, val):
        self._isolated_slice_idx = val
        self.main_window.update_tool_context(val is not None)

        # When entering or leaving isolated mode, immediately clear all active graphics tiles
        # to guarantee strict isolation boundaries and no artifact bleeding from cached pyvips tiles.
        for k, item in list(self.tile_items.items()):
            if item != "fetching" and item.scene() == self.scene:
                self.scene.removeItem(item)
        self.tile_items.clear()

        # Sync pixel overlay here (not on every frame): build on enter, clear on exit.
        # Scene items are in scene-space, so they move correctly with pan/zoom without rebuilding.
        s = self.main_window.current_session
        if val is not None and s:
            self._rebuild_pixel_overlay(s, val)
        else:
            for item in self._pixel_overlay_items:
                if item.scene() == self.scene:
                    self.scene.removeItem(item)
            self._pixel_overlay_items.clear()

        self.redraw()

    # ------------------------------------------------------------------
    # Pixel Overlay (scene items — aligned with image bitmap)
    # ------------------------------------------------------------------

    def _rebuild_pixel_overlay(self, session, slice_idx: int) -> None:
        """Rebuild scene-based pixel removal overlay for *slice_idx*.

        Replaces the old drawForeground-based checkerboard with
        ``QGraphicsRectItem`` objects that live inside the QGraphicsScene.
        Because they share the same coordinate space as the image pixmap tiles,
        they are rendered through the identical OpenGL pipeline — guaranteeing
        sub-pixel-accurate alignment regardless of zoom or pan position.

        Design principle (python-patterns): single responsibility — this method
        *only* manages scene items; it does not read events or mutate the mask.
        """
        # --- 1. Remove stale overlay items from the scene ------------------
        for item in self._pixel_overlay_items:
            if item.scene() == self.scene:
                self.scene.removeItem(item)
        self._pixel_overlay_items.clear()

        if session is None or slice_idx is None:
            return
        if slice_idx >= len(session.tiles):
            return

        mask = session.tiles[slice_idx].pixel_mask
        if not mask:
            return

        # --- 2. Create one QGraphicsRectItem per removed pixel -------------
        # Red semi-transparent fill, no border (border drawn in drawForeground)
        remove_color = QColor(220, 30, 30, 160)
        brush = QBrush(remove_color)
        no_pen = QPen(Qt.PenStyle.NoPen)

        for (px, py) in mask:
            item = QGraphicsRectItem(float(px), float(py), 1.0, 1.0)
            item.setBrush(brush)
            item.setPen(no_pen)
            item.setZValue(10)   # above image tiles (z=0), below grid (z=20)
            self.scene.addItem(item)
            self._pixel_overlay_items.append(item)

    def set_tool(self, tool_name):
        self.active_tool = tool_name
        if tool_name == "grid":
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        elif tool_name == "brush":
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(self._make_pencil_cursor())
        elif tool_name == "erase":
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        elif tool_name == "segment":
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)

    @staticmethod
    def _make_pencil_cursor() -> "QCursor":
        """Build a slim 24×24 pencil cursor with the hot-spot at the pencil tip."""
        from PyQt6.QtGui import QCursor, QPainterPath
        SIZE = 24
        pix = QPixmap(SIZE, SIZE)
        pix.fill(Qt.GlobalColor.transparent)

        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Pencil runs bottom-left (tip) → top-right (eraser), very narrow body
        tip_x,    tip_y    =  1, 22   # hot-spot: sharp tip
        body_x,   body_y   = 18,  5   # start of eraser band
        eraser_x, eraser_y = 22,  1   # top of eraser cap

        # ── Pencil body (very thin parallelogram, only ~2 px wide) ────────────
        body_path = QPainterPath()
        body_path.moveTo(tip_x,      tip_y)        # tip bottom
        body_path.lineTo(tip_x + 2,  tip_y - 2)   # tip top-edge
        body_path.lineTo(body_x + 2, body_y)       # body top-right
        body_path.lineTo(body_x,     body_y + 2)   # body top-left
        body_path.closeSubpath()

        p.setBrush(QBrush(QColor(255, 215, 60)))   # golden-yellow body
        p.setPen(QPen(QColor(80, 55, 10), 0.8))
        p.drawPath(body_path)

        # ── Eraser band (small pink cap) ──────────────────────────────────────
        eraser_path = QPainterPath()
        eraser_path.moveTo(body_x,      body_y + 2)
        eraser_path.lineTo(body_x + 2,  body_y)
        eraser_path.lineTo(eraser_x,    eraser_y + 2)
        eraser_path.lineTo(eraser_x - 2, eraser_y + 4)
        eraser_path.closeSubpath()

        p.setBrush(QBrush(QColor(235, 110, 110)))  # pink eraser
        p.setPen(QPen(QColor(150, 50, 50), 0.7))
        p.drawPath(eraser_path)

        # ── Sharp graphite tip (tiny dark triangle) ───────────────────────────
        tip_path = QPainterPath()
        tip_path.moveTo(tip_x,      tip_y)
        tip_path.lineTo(tip_x + 2,  tip_y - 2)
        tip_path.lineTo(tip_x + 1,  tip_y - 4)
        tip_path.closeSubpath()

        p.setBrush(QBrush(QColor(25, 20, 10)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(tip_path)

        p.end()

        # Hotspot at the very tip
        return QCursor(pix, tip_x, tip_y)

    # ── Rendering: Explicit background clear (OpenGL framebuffer pattern) ────
    def drawBackground(self, painter: QPainter, rect) -> None:
        """Explicitly clear the OpenGL framebuffer before any scene items are drawn.
        
        QOpenGLWidget does NOT auto-clear the framebuffer between frames.
        Without this, old tile pixels from prior zoom levels persist as ghosts.
        """
        painter.fillRect(rect, QColor("#111111"))



    def redraw(self):
        # Debounce the viewport updates to ~60fps to prevent Event loop congestion
        if getattr(self, "_redraw_job", False):
            return
        self._redraw_job = True
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(16, self._do_redraw)

    def _do_redraw(self):
        self._redraw_job = False
        s = self.main_window.current_session
        if not s or not s.pyramid_ready: return
        
        zoom = self.viewport_zoom
        
        # Stop requesting tiny micro-tiles when zoomed way past 1.0. 
        # Qt's hardware camera will gracefully scale the actual 1.0 tiles for us.
        tile_zoom = min(zoom, 1.0)
        
        self.scene.setSceneRect(0, 0, s.real_width, s.real_height)
        
        self.resetTransform()
        self.scale(zoom, zoom)
        
        # ── Zoom-level hard eviction ──────────────────────────────────────────
        # When tile_zoom changes, ALL scene items from the previous zoom level
        # must be removed IMMEDIATELY from the QGraphicsScene.
        # Without this, they accumulate as ghost layers causing the kaleidoscope effect.
        last_tile_zoom = getattr(self, "_last_tile_zoom", tile_zoom)
        if last_tile_zoom is not None and last_tile_zoom != tile_zoom:
            to_remove = [k for k in self.tile_items if k[2] != tile_zoom]
            for k in to_remove:
                item = self.tile_items.pop(k)
                try:
                    if item != "fetching" and item.scene() == self.scene:
                        self.scene.removeItem(item)
                except RuntimeError:
                    pass  # C++ object already deleted (e.g. after scene.clear())
        self._last_tile_zoom = tile_zoom
        
        # Instantiate Base Layer Thumbnail for black-flash protection
        if not hasattr(s, "base_layer_item"):
            # Load large 2k thumbnail
            thumb_pil = Image.open(io.BytesIO(s.get_thumbnail(2048))) if isinstance(s.get_thumbnail(2048), bytes) else s.get_thumbnail(2048)
            
            # Use PIL for guaranteed RGB byte parity
            if thumb_pil.mode != "RGB":
                thumb_pil = thumb_pil.convert("RGB")
                
            data = thumb_pil.tobytes("raw", "RGB")
            qim = QImage(data, thumb_pil.width, thumb_pil.height, thumb_pil.width * 3, QImage.Format.Format_RGB888)
            qim.setDevicePixelRatio(1.0)
            pix = QPixmap.fromImage(qim)
            pix.setDevicePixelRatio(1.0)
            
            base_item = QGraphicsPixmapItem(pix)
            # Scale the low-res thumb to cover the entire full-res scene
            base_item.setScale(s.real_width / thumb_pil.width)
            # Push it behind all other pyvips tiles
            base_item.setZValue(-1)
            
            s.base_layer_item = base_item
            
        if self.isolated_slice_idx is not None:
            if s.base_layer_item.scene() == self.scene:
                self.scene.removeItem(s.base_layer_item)
        else:
            if s.base_layer_item.scene() != self.scene:
                self.scene.addItem(s.base_layer_item)
        
        # Calculate true visible scene rectangle (Full Res Coords)
        visible_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        
        # Clamp bounds to Pyvips Image limits
        vis_left = max(0, visible_rect.left())
        vis_top = max(0, visible_rect.top())
        vis_right = min(s.real_width, visible_rect.right())
        vis_bottom = min(s.real_height, visible_rect.bottom())
        
        # Size of a LOD tile in Full Res Coords is TILE_SIZE / tile_zoom
        lod_tile_w = self.TILE_SIZE / tile_zoom
        
        start_col = int(vis_left // lod_tile_w)
        end_col = int(vis_right // lod_tile_w)
        
        start_row = int(vis_top // lod_tile_w)
        end_row = int(vis_bottom // lod_tile_w)
        
        # Abort if bounds are completely broken (e.g > 100 tiles requested at once)
        if (end_col - start_col) * (end_row - start_row) > 150:
            return
            
        isolation_bounds = None
        if self.isolated_slice_idx is not None and self.isolated_slice_idx < len(s.tiles):
            isolation_bounds = s.tiles[self.isolated_slice_idx].bounding_box
            
        for col in range(start_col, end_col + 1):
            for row in range(start_row, end_row + 1):
                # Skip tiles completely outside the isolated slice if isolated mode is active
                if self.isolated_slice_idx is not None and isolation_bounds is not None:
                    tile_x1 = col * lod_tile_w
                    tile_y1 = row * lod_tile_w
                    tile_x2 = tile_x1 + lod_tile_w
                    tile_y2 = tile_y1 + lod_tile_w
                    
                    sx1, sy1, sx2, sy2 = isolation_bounds
                    if not (sx2 > tile_x1 and sx1 < tile_x2 and sy2 > tile_y1 and sy1 < tile_y2):
                        continue
                        
                lod_key = (col, row, tile_zoom)
                if lod_key not in self.tile_items:
                    worker = TileWorker(s, col, row, tile_zoom, self.TILE_SIZE)
                    worker.signals.result.connect(self._on_tile_loaded)
                    self.threadpool.start(worker)
                    self.tile_items[lod_key] = "fetching"
                    
        # Lightweight LRU: remove tiles that are way off-screen (> 300 cached)
        if len(self.tile_items) > 300:
            visible_keys = set(
                (c, r, tile_zoom)
                for c in range(start_col - 2, end_col + 3)
                for r in range(start_row - 2, end_row + 3)
            )
            to_remove = [k for k in self.tile_items if k not in visible_keys]
            for k in to_remove:
                item = self.tile_items.pop(k)
                if item != "fetching" and item.scene() == self.scene:
                    self.scene.removeItem(item)

        # Force a foreground redraw without changing tiles
        self.viewport().update()


    def _on_tile_loaded(self, key, pixmap):
        col, row, fetched_zoom = key
        # Verify Context
        if not self.main_window.current_session or min(self.viewport_zoom, 1.0) != fetched_zoom:
            return
            
        item = QGraphicsPixmapItem(pixmap)
        item.setPos((col * self.TILE_SIZE) / fetched_zoom, (row * self.TILE_SIZE) / fetched_zoom)
        item.setScale(1.0 / fetched_zoom)
        self.scene.addItem(item)
        self.tile_items[key] = item

    # -----------------------------------------------------
    # GPU Overlays: Grid and Selections 
    # -----------------------------------------------------
    def drawForeground(self, painter: QPainter, rect):
        """Native Qt callback to draw vector graphics over the scene GPU pixels."""
        s = self.main_window.current_session
        if not s: return

        # Rect is the visible scene bounding box in full-resolution coordinates
        left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
        
        # ---------------------------------------------------------------------
        # ISOLATION MODE: Membrane Overlay
        # ---------------------------------------------------------------------
        if self.isolated_slice_idx is not None:
            # 1. Check if the user wants to see the segmentation membrane
            show_membrane = True
            if hasattr(self.main_window, 'chk_show_membrane'):
                show_membrane = self.main_window.chk_show_membrane.isChecked()

            # 2. Draw the membrane for all visible layers if toggled ON
            if show_membrane and self.isolated_slice_idx < len(s.tiles):
                tile = s.tiles[self.isolated_slice_idx]
                for poly, color_hex in tile.get_visible_polygons():
                    base_color = QColor(color_hex)
                    membrane_color = QColor(base_color)
                    membrane_color.setAlpha(120)
                    
                    painter.setBrush(QBrush(membrane_color))
                    border_pen = QPen(base_color, max(2.0 / self.viewport_zoom, 1.0))
                    border_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                    painter.setPen(border_pen)
                    
                    poly_f = QPolygonF()
                    for pt in poly:
                        poly_f.append(QPointF(pt[0], pt[1]))
                    painter.drawPolygon(poly_f)

            # ── Pixel removal borders (thin red outline only) ────────────────
            # The fill is handled by _rebuild_pixel_overlay() via QGraphicsRectItem
            # (scene-space items, same render pipeline as the image → perfect alignment).
            # Here we only draw the 1-px border which does NOT need sub-pixel accuracy.
            i = self.isolated_slice_idx
            if i < len(s.tiles) and s.tiles[i].pixel_mask:
                border_pen = QPen(QColor(210, 40, 40, 230), 0.08 / max(self.viewport_zoom, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(border_pen)
                for (px, py) in s.tiles[i].pixel_mask:
                    painter.drawRect(QRectF(float(px), float(py), 1.0, 1.0))

            # ── Pixel grid — only when each real pixel is clearly visible ────
            # FIX: use math.floor() for grid start to snap to integer pixel
            # boundaries, and disable antialiasing so lines render crispy.
            if self.viewport_zoom >= 4.0:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                grid_color = QColor(200, 200, 200, 55)
                pen = QPen(grid_color, 0.0)   # cosmetic pen = always 1 screen pixel wide
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)

                # Snap start positions to integer pixel boundaries
                px_left   = max(0, math.floor(left))
                px_top    = max(0, math.floor(top))
                px_right  = min(s.real_width,  math.ceil(right)  + 1)
                px_bottom = min(s.real_height, math.ceil(bottom) + 1)

                # Guard: avoid drawing thousands of lines at low zoom
                if (px_right - px_left) < 800 and (px_bottom - px_top) < 800:
                    for x in range(px_left, px_right + 1):
                        painter.drawLine(QPointF(x, float(px_top)), QPointF(x, float(px_bottom)))
                    for y in range(px_top, px_bottom + 1):
                        painter.drawLine(QPointF(float(px_left), y), QPointF(float(px_right), y))

            return
        
        # Draw Selections (Normal Mode) — iterate all tiles for visible layers
        show_membrane = True
        if hasattr(self.main_window, 'chk_show_membrane'):
            show_membrane = self.main_window.chk_show_membrane.isChecked()

        # LOD threshold: a typical nucleus is ~40 full-res px wide.
        # At viewport_zoom 0.15 that is 6 screen pixels — sub-perceptual.
        # Skip the polygon loop entirely at lower zoom levels; tile outlines
        # drawn below still give full spatial context at no meaningful cost.
        _NUCLEUS_LOD_ZOOM = 0.15

        if show_membrane and self.viewport_zoom >= _NUCLEUS_LOD_ZOOM:
            _pen_cache: dict = {}
            _brush_cache: dict = {}
            pen_width = max(2.0 / self.viewport_zoom, 1.0)
            for tile in s.tiles:
                # Skip tiles completely outside the visible viewport
                sx1, sy1, sx2, sy2 = tile.bounding_box
                if not (sx2 > left and sx1 < right and sy2 > top and sy1 < bottom):
                    continue
                for poly, color_hex in tile.get_visible_polygons():
                    if color_hex not in _pen_cache:
                        base_color = QColor(color_hex)
                        fill_color = QColor(base_color)
                        fill_color.setAlpha(80)
                        pen = QPen(base_color, pen_width)
                        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                        _pen_cache[color_hex] = pen
                        _brush_cache[color_hex] = QBrush(fill_color)
                    painter.setBrush(_brush_cache[color_hex])
                    painter.setPen(_pen_cache[color_hex])
                    poly_f = QPolygonF()
                    for pt in poly:
                        poly_f.append(QPointF(pt[0], pt[1]))
                    painter.drawPolygon(poly_f)

        if s.tiles:
            for i, tile in enumerate(s.tiles):
                color = QColor(tile.color)
                fill_color = QColor(color)
                fill_color.setAlpha(80) 
                painter.setPen(QPen(color, 0))
                # Standard Rectangle
                painter.setBrush(QBrush(fill_color))
                for (sx1, sy1, sx2, sy2) in tile.rects:
                    if sx2 > left and sx1 < right and sy2 > top and sy1 < bottom:
                        painter.drawRect(QRectF(float(sx1), float(sy1), float(sx2 - sx1), float(sy2 - sy1)))

        # Draw Grid — only when grid cells are visible at ≥8 screen pixels wide
        # Use a cosmetic pen (width=0) so lines are ALWAYS 1 screen pixel, regardless of zoom.
        # The old `max(1.0/viewport_zoom, 1.0)` caused 20+ px wide lines at low zoom → yellow flood.
        cell_screen_w = s.grid_w * self.viewport_zoom
        cell_screen_h = s.grid_h * self.viewport_zoom
        if cell_screen_w >= 8 and (right - left) / s.grid_w < 800:
            grid_color = QColor(s.grid_color)
            grid_color.setAlpha(180)
            pen = QPen(grid_color, 0, Qt.PenStyle.DashLine)  # 0 = cosmetic: 1 screen-pixel always
            pen.setCosmetic(True)
            painter.setPen(pen)

            sc = int(left // s.grid_w)
            ec = int(right // s.grid_w) + 1
            for c in range(sc, ec + 1):
                x = c * s.grid_w
                painter.drawLine(x, int(top), x, int(bottom))
                
            sr = int(top // s.grid_h)
            er = int(bottom // s.grid_h) + 1
            for r in range(sr, er + 1):
                y = r * s.grid_h
                painter.drawLine(int(left), y, int(right), y)


        # Draw rect select preview
        if self._rect_drag_start is not None and len(self._brush_points) == 1:
            pen = QPen(QColor("#FF6600"), 0, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = self._rect_drag_start
            c = self._brush_points[0]
            painter.drawRect(QRectF(min(r.x(), c.x()), min(r.y(), c.y()), abs(r.x()-c.x()), abs(r.y()-c.y())))

        # Draw live brush stroke
        if self.active_tool == "brush" and len(self._brush_points) > 1:
            pen = QPen(QColor("#00FF00"), 0)
            pen.setCosmetic(True)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            poly_live = QPolygonF()
            for p in self._brush_points:
                poly_live.append(QPointF(p[0], p[1]))
            painter.drawPolyline(poly_live)

    # -----------------------------------------------------
    # Input Processing (Mouse / Zoom)
    # -----------------------------------------------------
    def wheelEvent(self, event: QWheelEvent):
        s = self.main_window.current_session
        if not s: return

        zoom_factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        new_zoom = self.viewport_zoom * zoom_factor
        
        if new_zoom < 0.01: new_zoom = 0.01
        if new_zoom > 200.0: new_zoom = 200.0
        
        old_pos = self.mapToScene(event.position().toPoint())
        self.viewport_zoom = new_zoom
        
        self.resetTransform()
        self.scale(new_zoom, new_zoom)
        
        new_pos = self.mapFromScene(old_pos)
        delta = new_pos - event.position().toPoint()
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + delta.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + delta.y())
        
        self.redraw()

    def _on_segmentation_done(self, polygon: list, session, slice_idx: int, model_name: str = "Unknown"):
        """Callback invoked on the main thread when background segmentation finishes."""
        self.setStyleSheet("")
        sb = getattr(self.main_window, 'statusBar', lambda: None)()

        if polygon:
            tile = session.tiles[slice_idx]
            # Find existing layer for this model or create new
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
            # Refresh layer dropdown
            dropdown = getattr(self.main_window, 'layer_dropdown', None)
            if dropdown:
                dropdown.set_tile(tile)
        else:
            if sb:
                sb.showMessage("Failed to find nucleus at coordinates.")

        self.viewport().update()

    def _on_segmentation_error(self, error_msg: str):
        """Callback invoked on the main thread when background segmentation fails."""
        self.setStyleSheet("")
        logger.error("Inference failed: %s", error_msg)
        sb = getattr(self.main_window, 'statusBar', lambda: None)()
        if sb:
            sb.showMessage("Inference failed.")
        self.viewport().update()

    def mousePressEvent(self, event: QMouseEvent):
        s = self.main_window.current_session
        if self.isolated_slice_idx is not None:
            # INTERACTIVE SEGMENTATION MODE (Left Click)
            if self.active_tool == "segment" and event.button() == Qt.MouseButton.LeftButton and s:
                scene_pt = self.mapToScene(event.position().toPoint())
                px = math.floor(scene_pt.x())
                py = math.floor(scene_pt.y())
                idx = self.isolated_slice_idx

                # Check if clicked inside an existing segmentation to remove it
                tile = s.tiles[idx]
                for layer in tile.segmentation_layers:
                    for pi, poly in enumerate(layer.get("polygons", [])):
                        if is_point_in_polygon(px, py, poly):
                            layer["polygons"].pop(pi)
                            if not layer["polygons"]:
                                tile.segmentation_layers.remove(layer)
                            sb = getattr(self.main_window, 'statusBar', lambda: None)()
                            if sb:
                                sb.showMessage("Segmentation removed.")
                            dropdown = getattr(self.main_window, 'layer_dropdown', None)
                            if dropdown:
                                dropdown.set_tile(tile)
                            self.viewport().update()
                            return

                slice_rects = s.tiles[idx].rects
                in_tile = any(r[0] <= px < r[2] and r[1] <= py < r[3] for r in slice_rects)
                if not in_tile:
                    super().mousePressEvent(event)
                    return

                model_name = self.main_window.combo_model.currentText()
                if not model_name: return

                sb = getattr(self.main_window, 'statusBar', lambda: None)()
                if sb: sb.showMessage(f"Processing inference with {model_name}...")

                self.setStyleSheet("opacity: 0.5;")

                # Delegate to Application Service on a background thread (Error 3 & 5 fix)
                seg_service = self.main_window.segmentation_service
                worker = SegmentationWorker(seg_service, model_name, s, idx, px, py)
                worker.signals.finished.connect(
                    lambda poly, _s=s, _idx=idx, _m=model_name: self._on_segmentation_done(poly, _s, _idx, _m)
                )
                worker.signals.error.connect(
                    lambda err: self._on_segmentation_error(err)
                )
                self.threadpool.start(worker)
                return

            # PIXEL ERASE MODE (Left Click drag to paint erase, Right Click to restore)
            if self.active_tool == "erase" and (event.button() == Qt.MouseButton.LeftButton or event.button() == Qt.MouseButton.RightButton) and s:
                scene_pt = self.mapToScene(event.position().toPoint())
                px = math.floor(scene_pt.x())
                py = math.floor(scene_pt.y())
                idx = self.isolated_slice_idx

                slice_rects = s.tiles[idx].rects
                in_tile = any(r[0] <= px < r[2] and r[1] <= py < r[3] for r in slice_rects)
                if not in_tile:
                    super().mousePressEvent(event)
                    return

                undo = getattr(self.main_window, 'undo_manager', None)
                if undo:
                    undo.push(s, 'pixel_mask_toggle')
                    
                erase_mode = event.button() == Qt.MouseButton.LeftButton
                mask = self._pms.get_mask(s, idx)
                if erase_mode:
                    mask.add((px, py))
                else:
                    mask.discard((px, py))
                    
                sb = getattr(self.main_window, 'statusBar', lambda: None)()
                if sb:
                    sb.showMessage(f"Pixel ({px}, {py}) {'removed' if erase_mode else 'restored'}  |  mask size: {len(mask)}")
                
                self._rebuild_pixel_overlay(s, idx)
                self.viewport().update()
                return
            
            # Left-click (pan) — fall through to default QGraphicsView handler
            super().mousePressEvent(event)
            return
            
        if event.button() == Qt.MouseButton.RightButton:
            self._rect_drag_start = self.mapToScene(event.pos())
            self._brush_points = [self._rect_drag_start]
        elif self.active_tool == "brush" and event.button() == Qt.MouseButton.LeftButton:
            self._brush_points = [(self.mapToScene(event.pos()).x(), self.mapToScene(event.pos()).y())]
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        s = self.main_window.current_session
        if self.isolated_slice_idx is not None:
            # If mouse button held while moving in isolation mode AND active_tool == "erase"
            if self.active_tool == "erase" and (event.buttons() & Qt.MouseButton.LeftButton or event.buttons() & Qt.MouseButton.RightButton) and s:
                scene_pt = self.mapToScene(event.position().toPoint())
                px = math.floor(scene_pt.x())
                py = math.floor(scene_pt.y())
                idx = self.isolated_slice_idx

                slice_rects = s.tiles[idx].rects
                in_tile = any(r[0] <= px < r[2] and r[1] <= py < r[3] for r in slice_rects)
                if not in_tile:
                    super().mouseMoveEvent(event)
                    return

                erase_mode = bool(event.buttons() & Qt.MouseButton.LeftButton)
                mask = self._pms.get_mask(s, idx)
                if erase_mode:
                    mask.add((px, py))
                else:
                    mask.discard((px, py))
                    
                self._rebuild_pixel_overlay(s, idx)
                self.viewport().update()
                return
            super().mouseMoveEvent(event)
            return
            
        if self._rect_drag_start is not None:
            self._brush_points = [self.mapToScene(event.pos())]
            self.viewport().update()
        elif self.active_tool == "brush" and event.buttons() == Qt.MouseButton.LeftButton:
            # We skip full freehand tracking here for simplicity, replacing it with bounding box logic
            self._brush_points.append((self.mapToScene(event.pos()).x(), self.mapToScene(event.pos()).y()))
            self.viewport().update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        s = self.main_window.current_session
        if not s: return

        if self.isolated_slice_idx is not None:
            super().mouseReleaseEvent(event)
            return
        
        # Right Click Selection
        if event.button() == Qt.MouseButton.RightButton and self._rect_drag_start is not None:
            end_pt = self.mapToScene(event.pos())
            rx1 = min(self._rect_drag_start.x(), end_pt.x())
            ry1 = min(self._rect_drag_start.y(), end_pt.y())
            rx2 = max(self._rect_drag_start.x(), end_pt.x())
            ry2 = max(self._rect_drag_start.y(), end_pt.y())
            
            self._rect_drag_start = None
            self._brush_points = []
            
            if abs(rx2 - rx1) < 5 and abs(ry2 - ry1) < 5:
                # Single Right Click (Toggle Grid Cell)
                col, row = int(rx1 // s.grid_w), int(ry1 // s.grid_h)
                x1, y1 = col * s.grid_w, row * s.grid_h
                x2, y2 = min(x1 + s.grid_w, s.real_width), min(y1 + s.grid_h, s.real_height)
                
                # Check overlap (naive subtraction logic port)
                from app.domain.tile import Tile
                found_idx = None
                for i, tile in enumerate(s.tiles):
                    for r in tile.rects:
                        if r[0] < x2 and r[2] > x1 and r[1] < y2 and r[3] > y1:
                            found_idx = i
                            break
                    if found_idx is not None:
                        break

                if found_idx is not None:
                    # SUBTRACT from this slice group
                    old_tile = s.tiles.pop(found_idx)
                    new_slices = subtract_from_slice(
                        old_tile.rects, col, row,
                        s.grid_w, s.grid_h, s.real_width, s.real_height)
                    for ns in new_slices:
                        s.tiles.append(Tile(rects=list(ns)))
                else:
                    # ADD as new independent slice
                    s.tiles.append(Tile(rects=[(x1, y1, x2, y2)]))
                self.redraw()
                self.main_window.slice_previews.update_previews()
            else:
                # Drag Select Area (independent of grids)
                from app.domain.tile import Tile
                s.tiles.append(Tile(rects=[(int(rx1), int(ry1), int(rx2), int(ry2))]))
                self.redraw()
                self.main_window.slice_previews.update_previews()
            return
            
        if self.active_tool == "brush" and event.button() == Qt.MouseButton.LeftButton:
            if len(self._brush_points) > 2:
                from app.domain.tile import Tile
                new_tile = Tile(polygon=self._brush_points.copy())

                # 2. Map the stroke to grid rectangles using QPainterPath area intersection.
                # QPainterPath.intersects() checks true AREA overlap (filled region),
                # while QPolygonF.intersects() was edge-based and selected the entire bounding box.
                from PyQt6.QtGui import QPainterPath as _QPainterPath
                poly_f = QPolygonF()
                for p in self._brush_points:
                    poly_f.append(QPointF(p[0], p[1]))
                bbox = poly_f.boundingRect()

                # Build a closed filled path from the freehand stroke
                stroke_path = _QPainterPath()
                stroke_path.addPolygon(poly_f)
                stroke_path.closeSubpath()

                # Use the precise bounding box of the brush stroke instead of snapping to grid cells
                x1 = max(0, int(bbox.left()))
                y1 = max(0, int(bbox.top()))
                x2 = min(s.real_width, int(bbox.right()))
                y2 = min(s.real_height, int(bbox.bottom()))

                if x2 > x1 and y2 > y1:
                    new_tile.rects = [(x1, y1, x2, y2)]
                    s.tiles.append(new_tile)
            
            self._brush_points = []
            self.redraw()
            self.main_window.slice_previews.update_previews()
        
        super().mouseReleaseEvent(event)


