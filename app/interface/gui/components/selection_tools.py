import tkinter as tk
from tkinter import colorchooser
from app.domain.selection import subtract_from_slice


class SelectionToolsMixin:
    """Mixin for selection tools: brush, rectangle select, grid click, color."""

    def _activate_tool(self, tool):
        """Switch active tool between 'grid' and 'brush'."""
        self.active_tool = tool
        if self._brush_btn:
            if tool == "brush":
                self._brush_btn.config(bg="#007acc", relief="sunken")
                self.canvas.config(cursor="crosshair")
                self.status_bar.config(text="Brush Mode: drag to draw a selection area")
            else:
                self._brush_btn.config(bg="#444", relief="flat")
                self.canvas.config(cursor="")
                if self.current_session:
                    self.status_bar.config(text=f"Image: {self.current_session.name}")
        self._rebind_canvas()
        self.redraw()

    def _rebind_canvas(self):
        """Reapply canvas event bindings based on the active tool."""
        c = self.canvas
        # Clear all left-button bindings first
        c.unbind("<ButtonPress-1>")
        c.unbind("<B1-Motion>")
        c.unbind("<ButtonRelease-1>")
        c.unbind("<Button-3>")
        c.unbind("<Button-2>")
        c.unbind("<Control-Button-1>")

        if self.active_tool == "brush":
            c.bind("<ButtonPress-1>", self._brush_start)
            c.bind("<B1-Motion>", self._brush_move)
            c.bind("<ButtonRelease-1>", self._brush_end)
        else:
            c.bind("<ButtonPress-1>", self.on_pan_start)
            c.bind("<B1-Motion>", self.on_pan_move)
            c.bind("<Button-3>", self._rect_select_start)
            c.bind("<B3-Motion>", self._rect_select_move)
            c.bind("<ButtonRelease-3>", self._rect_select_end)
            if self.is_mac:
                c.bind("<Button-2>", self._rect_select_start)
                c.bind("<Control-Button-1>", self._rect_select_start)

    def _brush_start(self, e):
        """Start a freehand brush stroke."""
        s = self.current_session
        if not s:
            return
        self._brush_points = []
        # Convert canvas coords to image coords
        ix = s.camera_x + e.x / s.zoom_level
        iy = s.camera_y + e.y / s.zoom_level
        self._brush_points.append((ix, iy))
        self._brush_last_canvas = (e.x, e.y)

    def _brush_move(self, e):
        """Continue freehand stroke — record point and draw preview line."""
        s = self.current_session
        if not s or not self._brush_points:
            return
        ix = s.camera_x + e.x / s.zoom_level
        iy = s.camera_y + e.y / s.zoom_level
        self._brush_points.append((ix, iy))
        lx, ly = self._brush_last_canvas
        self.canvas.create_line(lx, ly, e.x, e.y,
                                fill="#FF6600", width=2, tags="brush_preview")
        self._brush_last_canvas = (e.x, e.y)

    def _brush_end(self, e):
        """Finish stroke — store exact polygon and create a bounding-box slice entry."""
        s = self.current_session
        if not s or len(self._brush_points) < 3:
            self._brush_points = []
            self.canvas.delete("brush_preview")
            return

        polygon = list(self._brush_points)  # keep a copy
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        x1 = max(0, int(min(xs)))
        y1 = max(0, int(min(ys)))
        x2 = min(s.real_width,  int(max(xs)) + 1)
        y2 = min(s.real_height, int(max(ys)) + 1)

        self._brush_points = []
        self.canvas.delete("brush_preview")

        if x2 <= x1 or y2 <= y1:
            return

        self.undo_manager.push(s, "brush_tile")
        s.selected_cells.append({(x1, y1, x2, y2)})
        s.selected_polygons.append(polygon)   # exact freehand shape
        s.sync_metadata()
        self.redraw()
        self._update_slice_previews()
        self.trigger_modification()
        self._auto_reexport(s)

    def on_right_click(self, e):
        s = self.current_session
        if not s: return
        rx = s.camera_x + (e.x / s.zoom_level)
        ry = s.camera_y + (e.y / s.zoom_level)
        if 0 <= rx <= s.real_width and 0 <= ry <= s.real_height:
            col = int(rx // s.grid_w)
            row = int(ry // s.grid_h)
            x1 = col * s.grid_w
            y1 = row * s.grid_h
            x2 = min(x1 + s.grid_w, s.real_width)
            y2 = min(y1 + s.grid_h, s.real_height)
            cell_rect = (x1, y1, x2, y2)

            self.undo_manager.push(s, "grid_click")

            # Find which slice group overlaps the click
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
                s.selected_cells.append({cell_rect})

            s.sync_metadata()
            self.redraw()
            self._update_slice_previews()
            self.trigger_modification()
            self._auto_reexport(s)

    def _rect_select_start(self, e):
        """Start rubber-band selection (right-click drag in grid mode)."""
        self._rect_start_x = e.x
        self._rect_start_y = e.y
        self._rect_dragging = False

    def _rect_select_move(self, e):
        """Draw rubber-band preview rectangle while dragging."""
        if not hasattr(self, '_rect_start_x'):
            return
        # Check if moved enough to call it a drag
        dx = abs(e.x - self._rect_start_x)
        dy = abs(e.y - self._rect_start_y)
        if dx > 5 or dy > 5:
            self._rect_dragging = True
        if self._rect_dragging:
            self.canvas.delete("rect_preview")
            self.canvas.create_rectangle(
                self._rect_start_x, self._rect_start_y, e.x, e.y,
                outline="#FF6600", width=2, dash=(4, 4), tags="rect_preview")

    def _rect_select_end(self, e):
        """Finish rubber-band: if dragged, select all grid cells in the rectangle."""
        self.canvas.delete("rect_preview")
        if not hasattr(self, '_rect_start_x'):
            return

        if not self._rect_dragging:
            # Single right-click — fall back to original behavior
            self.on_right_click(e)
            return

        s = self.current_session
        if not s:
            return

        # Convert canvas coords to image coords
        ix1 = s.camera_x + self._rect_start_x / s.zoom_level
        iy1 = s.camera_y + self._rect_start_y / s.zoom_level
        ix2 = s.camera_x + e.x / s.zoom_level
        iy2 = s.camera_y + e.y / s.zoom_level

        # Normalize to image bounds
        rx1 = max(0, min(ix1, ix2))
        ry1 = max(0, min(iy1, iy2))
        rx2 = min(s.real_width, max(ix1, ix2))
        ry2 = min(s.real_height, max(iy1, iy2))

        if rx2 <= rx1 or ry2 <= ry1:
            return

        # Independent rectangle selection (does not snap to grid)
        rects = {(int(rx1), int(ry1), int(rx2), int(ry2))}

        if rects:
            self.undo_manager.push(s, "rect_select")
            s.selected_cells.append(rects)
            s.sync_metadata()
            self.redraw()
            self._update_slice_previews()
            self.trigger_modification()
            self._auto_reexport(s)

    def choose_color(self):
        if self.current_session:
            c = colorchooser.askcolor()[1]
            if c: 
                self.current_session.grid_color = c
                self.redraw()
                self.trigger_modification()

    def clear_selection(self, e=None):
        if self.current_session:
            self.undo_manager.push(self.current_session, "clear")
            self.current_session.selected_cells.clear()
            self.redraw()
            self._update_slice_previews()
            self.trigger_modification()
