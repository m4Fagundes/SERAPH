import logging
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import QPainter, QPixmap, QImage, QWheelEvent, QMouseEvent, QPen, QColor, QBrush, QPolygonF
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QObject, QRunnable, QThreadPool
import io
from app.domain.selection import subtract_from_slice
from app.application.services import PixelMaskService

logger = logging.getLogger(__name__)

class WorkerSignals(QObject):
    result = pyqtSignal(tuple, object)

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
            pix = QPixmap.fromImage(qim)
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
        self.isolated_slice_idx = None
        
        # Shared pixel mask service (stateless, safe to reuse across events)
        self._pms = PixelMaskService()

    def set_tool(self, tool_name):
        self.active_tool = tool_name
        if tool_name == "grid":
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        elif tool_name == "brush":
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(self._make_pencil_cursor())

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
        
        # Instantiate Base Layer Thumbnail for black-flash protection
        if not hasattr(s, "base_layer_item"):
            # Load large 2k thumbnail
            thumb_pil = Image.open(io.BytesIO(s.get_thumbnail(2048))) if isinstance(s.get_thumbnail(2048), bytes) else s.get_thumbnail(2048)
            
            # Use PIL for guaranteed RGB byte parity
            if thumb_pil.mode != "RGB":
                thumb_pil = thumb_pil.convert("RGB")
                
            data = thumb_pil.tobytes("raw", "RGB")
            qim = QImage(data, thumb_pil.width, thumb_pil.height, thumb_pil.width * 3, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qim)
            
            base_item = QGraphicsPixmapItem(pix)
            # Scale the low-res thumb to cover the entire full-res scene
            base_item.setScale(s.real_width / thumb_pil.width)
            # Push it behind all other pyvips tiles
            base_item.setZValue(-1)
            
            self.scene.addItem(base_item)
            s.base_layer_item = base_item
        elif s.base_layer_item.scene() != self.scene:
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
            
        isolation_rects = []
        if self.isolated_slice_idx is not None and self.isolated_slice_idx < len(s.selected_cells):
            isolation_rects = s.selected_cells[self.isolated_slice_idx]
            
        for col in range(start_col, end_col + 1):
            for row in range(start_row, end_row + 1):
                # Skip tiles completely outside the isolated slice if isolated mode is active
                if self.isolated_slice_idx is not None and isolation_rects:
                    tile_x1 = col * lod_tile_w
                    tile_y1 = row * lod_tile_w
                    tile_x2 = tile_x1 + lod_tile_w
                    tile_y2 = tile_y1 + lod_tile_w
                    overlap = False
                    for (sx1, sy1, sx2, sy2) in isolation_rects:
                        if sx2 > tile_x1 and sx1 < tile_x2 and sy2 > tile_y1 and sy1 < tile_y2:
                            overlap = True
                            break
                    if not overlap:
                        continue
                        
                lod_key = (col, row, tile_zoom)
                if lod_key not in self.tile_items:
                    worker = TileWorker(s, col, row, tile_zoom, self.TILE_SIZE)
                    worker.signals.result.connect(self._on_tile_loaded)
                    self.threadpool.start(worker)
                    self.tile_items[lod_key] = "fetching"
                    
        # Clean up old unseen tiles (LRU basic garbage collection)
        if len(self.tile_items) > 300:
            to_remove = []
            for k, item in self.tile_items.items():
                if k[2] != tile_zoom: # delete all old layers
                    to_remove.append(k)
            for k in to_remove:
                if self.tile_items[k] != "fetching":
                    self.scene.removeItem(self.tile_items[k])
                del self.tile_items[k]
        
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
        # ISOLATION MODE: Paint an absolute black vignette outside the selected slice
        # ---------------------------------------------------------------------
        if self.isolated_slice_idx is not None:
            from PyQt6.QtGui import QPainterPath
            screen_path = QPainterPath()
            screen_path.addRect(QRectF(left, top, right - left, bottom - top))
            
            slice_path = QPainterPath()
            if self.isolated_slice_idx < len(s.selected_cells):
                poly = s.selected_polygons[self.isolated_slice_idx] if hasattr(s, 'selected_polygons') and self.isolated_slice_idx < len(s.selected_polygons) else None
                if poly and len(poly) >= 3:
                    poly_f = QPolygonF()
                    for pt in poly:
                        poly_f.append(QPointF(pt[0], pt[1]))
                    slice_path.addPolygon(poly_f)
                else:
                    slice_rects = s.selected_cells[self.isolated_slice_idx]
                    for (sx1, sy1, sx2, sy2) in slice_rects:
                        slice_path.addRect(QRectF(float(sx1), float(sy1), float(sx2 - sx1), float(sy2 - sy1)))
                
            # Boolean subtraction logic natively executed on C++
            mask_path = screen_path.subtracted(slice_path)
            painter.setBrush(QColor("black"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(mask_path)
            
            # ── Pixel mask overlay — checkerboard transparency pattern ──────────
            i = self.isolated_slice_idx
            if hasattr(s, 'pixel_masks') and i < len(s.pixel_masks) and s.pixel_masks[i]:
                # Colours for the two checkerboard cells (Photoshop-style alpha)
                dark_cell  = QColor(80,  80,  80,  200)
                light_cell = QColor(180, 180, 180, 200)
                border_pen = QPen(QColor(210, 40, 40, 230), 0.08 / max(self.viewport_zoom, 1))
                painter.setPen(Qt.PenStyle.NoPen)
                for (px, py) in s.pixel_masks[i]:
                    # Four sub-quadrants (each 0.5 × 0.5 real px)
                    for qx in range(2):
                        for qy in range(2):
                            cell_color = dark_cell if (qx + qy) % 2 == 0 else light_cell
                            painter.setBrush(QBrush(cell_color))
                            painter.drawRect(
                                QRectF(float(px) + qx * 0.5,
                                       float(py) + qy * 0.5,
                                       0.5, 0.5)
                            )
                    # Thin red border around the whole 1×1 pixel
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(border_pen)
                    painter.drawRect(QRectF(float(px), float(py), 1.0, 1.0))
                    painter.setPen(Qt.PenStyle.NoPen)

            # ── Pixel grid — only when each real pixel is clearly visible ───────
            if self.viewport_zoom >= 4.0:
                grid_color = QColor(200, 200, 200, 55)
                pen = QPen(grid_color, 1.0 / self.viewport_zoom)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                px_left   = max(0, int(left))
                px_top    = max(0, int(top))
                px_right  = min(s.real_width, int(right) + 2)
                px_bottom = min(s.real_height, int(bottom) + 2)
                # Guard: avoid drawing thousands of lines at low zoom
                if (px_right - px_left) < 800 and (px_bottom - px_top) < 800:
                    for x in range(px_left, px_right + 1):
                        painter.drawLine(QPointF(x, px_top), QPointF(x, px_bottom))
                    for y in range(px_top, px_bottom + 1):
                        painter.drawLine(QPointF(px_left, y), QPointF(px_right, y))

            # Draw a bounding box contour line around it to frame the viewport
            if self.isolated_slice_idx < len(s.selected_cells):
                painter.setBrush(Qt.BrushStyle.NoBrush)
                color_hex = s.tile_colors[self.isolated_slice_idx] if self.isolated_slice_idx < len(s.tile_colors) else "#00FFFF"
                painter.setPen(QPen(QColor(color_hex), max(2.0 / self.viewport_zoom, 1.0)))
                painter.drawPath(slice_path)
            return
        
        # Draw Selections (Normal Mode)
        if s.selected_cells:
            for i, slice_rects in enumerate(s.selected_cells):
                color_hex = s.tile_colors[i] if i < len(s.tile_colors) else "#00FFFF"
                color = QColor(color_hex)
                fill_color = QColor(color)
                fill_color.setAlpha(80) 
                painter.setPen(QPen(color, 2.0 / self.viewport_zoom))
                poly = s.selected_polygons[i] if hasattr(s, 'selected_polygons') and i < len(s.selected_polygons) else None
                # Check for brush polygons
                if poly and len(poly) >= 3:
                    poly_w = QPolygonF()
                    for pt in poly:
                        poly_w.append(QPointF(pt[0], pt[1]))
                    
                    painter.setBrush(QBrush(fill_color))
                    poly_pen = QPen(color, max(2.0 / self.viewport_zoom, 1.0))
                    poly_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                    painter.setPen(poly_pen)
                    painter.drawPolygon(poly_w)
                else:
                    # Standard Rectangle
                    painter.setBrush(QBrush(fill_color))
                    for (sx1, sy1, sx2, sy2) in slice_rects:
                        if sx2 > left and sx1 < right and sy2 > top and sy1 < bottom:
                            painter.drawRect(QRectF(float(sx1), float(sy1), float(sx2 - sx1), float(sy2 - sy1)))

        # Draw Grid (if reasonably sized)
        if (right - left) / s.grid_w < 800:
            grid_color = QColor(s.grid_color)
            pen = QPen(grid_color, max(1.0 / self.viewport_zoom, 1.0), Qt.PenStyle.DashLine)
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
            pen = QPen(QColor("#FF6600"), 2.0 / self.viewport_zoom, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = self._rect_drag_start
            c = self._brush_points[0]
            painter.drawRect(QRectF(min(r.x(), c.x()), min(r.y(), c.y()), abs(r.x()-c.x()), abs(r.y()-c.y())))

        # Draw live brush stroke
        if self.active_tool == "brush" and len(self._brush_points) > 1:
            pen = QPen(QColor("#00FF00"), max(2.5 / self.viewport_zoom, 1.0))
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

    def mousePressEvent(self, event: QMouseEvent):
        s = self.main_window.current_session
        if self.isolated_slice_idx is not None:
            if event.button() == Qt.MouseButton.RightButton and s:
                # Right-click in isolation mode = toggle individual pixel
                scene_pt = self.mapToScene(event.position().toPoint())
                px = int(scene_pt.x())
                py = int(scene_pt.y())
                idx = self.isolated_slice_idx
                # Push undo snapshot before mutating
                undo = getattr(self.main_window, 'undo_manager', None)
                if undo:
                    undo.push(s, 'pixel_mask_toggle')
                removed = self._pms.toggle_pixel(s, idx, px, py)
                state = "removed" if removed else "restored"
                sb = getattr(self.main_window, 'statusBar', lambda: None)()
                if sb:
                    sb.showMessage(f"Pixel ({px}, {py}) {state}  |  mask size: {len(self._pms.get_mask(s, idx))}")
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
            # If right-button held while moving in isolation mode = drag-paint pixels
            if event.buttons() & Qt.MouseButton.RightButton and s:
                scene_pt = self.mapToScene(event.position().toPoint())
                px = int(scene_pt.x())
                py = int(scene_pt.y())
                idx = self.isolated_slice_idx
                # Don't push undo on every move step; only the initial press pushed one
                self._pms.get_mask(s, idx).add((px, py))  # always remove on drag
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
                found_idx = None
                for i, slice_rects in enumerate(s.selected_cells):
                    for r in slice_rects:
                        if r[0] < x2 and r[2] > x1 and r[1] < y2 and r[3] > y1:
                            found_idx = i
                            break
                    if found_idx is not None:
                        break

                if found_idx is not None:
                    # SUBTRACT from this slice group
                    old_slice = s.selected_cells.pop(found_idx)
                    new_slices = subtract_from_slice(
                        old_slice, col, row,
                        s.grid_w, s.grid_h, s.real_width, s.real_height)
                    for ns in new_slices:
                        s.selected_cells.append(ns)
                else:
                    # ADD as new independent slice
                    s.selected_cells.append({(x1, y1, x2, y2)})
                    
                s.sync_metadata()
                self.redraw()
                self.main_window.slice_previews.update_previews()
            else:
                # Drag Select Cells
                sc, ec = int(rx1 // s.grid_w), int((rx2 - 1) // s.grid_w)
                sr, er = int(ry1 // s.grid_h), int((ry2 - 1) // s.grid_h)
                rects = set()
                for c in range(sc, ec + 1):
                    for r in range(sr, er + 1):
                        rects.add((c * s.grid_w, r * s.grid_h, (c+1)*s.grid_w, (r+1)*s.grid_h))
                s.selected_cells.append(rects)
                s.sync_metadata()
                self.redraw()
                self.main_window.slice_previews.update_previews()
            return
            
        if self.active_tool == "brush" and event.button() == Qt.MouseButton.LeftButton:
            if len(self._brush_points) > 2:
                # 1. Store the raw polygon stroke
                if not hasattr(s, 'selected_polygons'):
                    s.selected_polygons = []
                while len(s.selected_polygons) < len(s.selected_cells):
                    s.selected_polygons.append(None)
                s.selected_polygons.append(self._brush_points.copy())

                # 2. Map the stroke to grid rectangles using QPolygonF native intersection
                poly_f = QPolygonF()
                for p in self._brush_points:
                    poly_f.append(QPointF(p[0], p[1]))
                bbox = poly_f.boundingRect()

                sc = int(bbox.left() // s.grid_w)
                ec = int(bbox.right() // s.grid_w)
                sr = int(bbox.top() // s.grid_h)
                er = int(bbox.bottom() // s.grid_h)
                
                intersecting_rects = set()
                for c in range(sc, ec + 1):
                    for r in range(sr, er + 1):
                        x1 = c * s.grid_w
                        y1 = r * s.grid_h
                        x2 = min(x1 + s.grid_w, s.real_width)
                        y2 = min(y1 + s.grid_h, s.real_height)
                        cell_rect = QRectF(x1, y1, x2 - x1, y2 - y1)
                        cell_poly = QPolygonF(cell_rect)
                        if poly_f.intersects(cell_poly) or poly_f.containsPoint(cell_rect.center(), Qt.FillRule.WindingFill):
                            intersecting_rects.add((x1, y1, x2, y2))

                if intersecting_rects:
                    s.selected_cells.append(intersecting_rects)
                    s.sync_metadata()
            
            self._brush_points = []
            self.redraw()
            self.main_window.slice_previews.update_previews()
        
        super().mouseReleaseEvent(event)


