import logging
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import QPainter, QPixmap, QImage, QWheelEvent, QMouseEvent, QPen, QColor, QBrush
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QObject, QRunnable, QThreadPool
from app.domain.selection import subtract_from_slice

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
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        
        # Default Tool: Pan
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.active_tool = "grid"
        
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(4)
        
        self.TILE_SIZE = 256
        self.tile_items = {}
        
        self._brush_points = []
        self._rect_drag_start = None
        
        # Local view matrix properties to allow multiple independent windows
        self.viewport_zoom = 1.0 
        self.isolated_slice_idx = None

    def set_tool(self, tool_name):
        self.active_tool = tool_name
        if tool_name == "grid":
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        elif tool_name == "brush":
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)

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
        self.scene.setSceneRect(0, 0, s.real_width, s.real_height)
        
        self.resetTransform()
        self.scale(zoom, zoom)
        
        # Calculate true visible scene rectangle (Full Res Coords)
        visible_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        
        # Clamp bounds to Pyvips Image limits
        vis_left = max(0, visible_rect.left())
        vis_top = max(0, visible_rect.top())
        vis_right = min(s.real_width, visible_rect.right())
        vis_bottom = min(s.real_height, visible_rect.bottom())
        
        # Size of a LOD tile in Full Res Coords is TILE_SIZE / zoom
        lod_tile_w = self.TILE_SIZE / zoom
        
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
                        
                lod_key = (col, row, zoom)
                if lod_key not in self.tile_items:
                    worker = TileWorker(s, col, row, zoom, self.TILE_SIZE)
                    worker.signals.result.connect(self._on_tile_loaded)
                    self.threadpool.start(worker)
                    self.tile_items[lod_key] = "fetching"
                    
        # Clean up old unseen tiles (LRU basic garbage collection)
        if len(self.tile_items) > 300:
            to_remove = []
            for k, item in self.tile_items.items():
                if k[2] != zoom: # delete all old layers
                    to_remove.append(k)
            for k in to_remove:
                if self.tile_items[k] != "fetching":
                    self.scene.removeItem(self.tile_items[k])
                del self.tile_items[k]
        
        # Force a foreground redraw without changing tiles
        self.viewport().update()

    def _on_tile_loaded(self, key, pixmap):
        col, row, zoom = key
        # Verify Context
        if not self.main_window.current_session or self.viewport_zoom != zoom:
            return
            
        item = QGraphicsPixmapItem(pixmap)
        item.setPos((col * self.TILE_SIZE) / zoom, (row * self.TILE_SIZE) / zoom)
        item.setScale(1.0 / zoom)
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
                slice_rects = s.selected_cells[self.isolated_slice_idx]
                for (sx1, sy1, sx2, sy2) in slice_rects:
                    slice_path.addRect(QRectF(float(sx1), float(sy1), float(sx2 - sx1), float(sy2 - sy1)))
                
            # Boolean subtraction logic natively executed on C++
            mask_path = screen_path.subtracted(slice_path)
            painter.setBrush(QColor("black"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(mask_path)
            
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
                painter.setBrush(QBrush(fill_color))
                
                # Check for brush polygons
                if s.selected_polygons and i < len(s.selected_polygons) and s.selected_polygons[i]:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    pass # TODO: Draw QPolygonF overlay if needed
                
                # Standard Rectangle
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

    # -----------------------------------------------------
    # Input Processing (Mouse / Zoom)
    # -----------------------------------------------------
    def wheelEvent(self, event: QWheelEvent):
        s = self.main_window.current_session
        if not s: return

        zoom_factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        new_zoom = self.viewport_zoom * zoom_factor
        
        if new_zoom < 0.01: new_zoom = 0.01
        if new_zoom > 10.0: new_zoom = 10.0
        
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
        if event.button() == Qt.MouseButton.RightButton:
            self._rect_drag_start = self.mapToScene(event.pos())
            self._brush_points = [self._rect_drag_start]
        elif self.active_tool == "brush" and event.button() == Qt.MouseButton.LeftButton:
            self._brush_points = [(self.mapToScene(event.pos()).x(), self.mapToScene(event.pos()).y())]
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
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
                xs = [p[0] for p in self._brush_points]
                ys = [p[1] for p in self._brush_points]
                s.selected_cells.append({(min(xs), min(ys), max(xs), max(ys))})
                s.sync_metadata()
            self._brush_points = []
            self.redraw()
            self.main_window.slice_previews.update_previews()
        
        super().mouseReleaseEvent(event)
