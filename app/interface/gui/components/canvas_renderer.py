import tkinter as tk
from PIL import ImageTk
from app.domain.selection import rect_to_cells


class CanvasRendererMixin:
    """Mixin for main canvas rendering: redraw, selection fill, scale bar."""

    def on_resize(self, event):
        if self.current_session: self.redraw()

    def _draw_selection_fill(self, x1, y1, x2, y2, color="#00FFFF"):
        """Draw hatching fill only (no border)."""
        line_spacing = 2
        y = y1
        while y < y2:
            self.canvas.create_line(x1, y, x2, y, fill=color, width=1)
            y += line_spacing * 2
        x = x1
        while x < x2:
            self.canvas.create_line(x, y1, x, y2, fill=color, width=1)
            x += line_spacing * 2

    def redraw(self):
        s = self.current_session
        if not s or not s.pyramid_ready: return

        try:
            s.grid_w = max(10, int(self.entry_w.get()))
            s.grid_h = max(10, int(self.entry_h.get()))
        except Exception:
            pass

        w_can = self.canvas.winfo_width()
        h_can = self.canvas.winfo_height()
        if w_can < 2 or h_can < 2:
            return
        
        l = s.camera_x
        t = s.camera_y
        r = l + (w_can / s.zoom_level)
        b = t + (h_can / s.zoom_level)

        self.canvas.delete("all")

        try:
            # Use pyramid tile-based viewport compositing
            img = s.pyramid.get_viewport(l, t, w_can, h_can, s.zoom_level)

            self.tk_image = ImageTk.PhotoImage(img)
            self.canvas.create_image(0, 0, image=self.tk_image, anchor="nw")
            
            # Draw slice fill (skip for polygon-based brush slices)
            for i, slice_rects in enumerate(s.selected_cells):
                tile_color = s.tile_colors[i] if i < len(s.tile_colors) else "#00FFFF"
                poly = s.selected_polygons[i] if i < len(s.selected_polygons) else None
                if poly:
                    continue  # polygon slices: outline only, no fill hatching
                for (sx1, sy1, sx2, sy2) in slice_rects:
                    if sx2 >= l and sx1 <= r and sy2 >= t and sy1 <= b:
                        cx1 = (sx1 - l) * s.zoom_level
                        cy1 = (sy1 - t) * s.zoom_level
                        cx2 = (sx2 - l) * s.zoom_level
                        cy2 = (sy2 - t) * s.zoom_level
                        self._draw_selection_fill(cx1, cy1, cx2, cy2, tile_color)

            # Draw slice outlines — polygon outline for brush slices, cell-edge logic for grid
            if self.active_tool == "brush":
                for i, slice_rects in enumerate(s.selected_cells):
                    tile_color = s.tile_colors[i] if i < len(s.tile_colors) else "#00FFFF"
                    poly = s.selected_polygons[i] if i < len(s.selected_polygons) else None
                    if poly and len(poly) >= 2:
                        # Draw exact polygon shape
                        canvas_pts = [((x - l) * s.zoom_level, (y - t) * s.zoom_level)
                                      for (x, y) in poly]
                        flat = [coord for pt in canvas_pts for coord in pt]
                        if len(flat) >= 4:
                            self.canvas.create_polygon(flat, outline=tile_color,
                                                       fill="", width=2)
                    else:
                        for (sx1, sy1, sx2, sy2) in slice_rects:
                            ex1 = (sx1 - l) * s.zoom_level
                            ey1 = (sy1 - t) * s.zoom_level
                            ex2 = (sx2 - l) * s.zoom_level
                            ey2 = (sy2 - t) * s.zoom_level
                            self.canvas.create_rectangle(ex1, ey1, ex2, ey2,
                                                         outline=tile_color, width=2)
            else:
                if (r - l) / s.grid_w < 400:
                    sc, ec = int(l // s.grid_w), int(r // s.grid_w) + 1
                    sr, er = int(t // s.grid_h), int(b // s.grid_h) + 1

                    for i, slice_rects in enumerate(s.selected_cells):
                        tile_color = s.tile_colors[i] if i < len(s.tile_colors) else "#00FFFF"
                        slice_cells = set()
                        for rect in slice_rects:
                            slice_cells |= rect_to_cells(rect, s.grid_w, s.grid_h)
                        for (c, ro) in slice_cells:
                            if c < sc or c > ec or ro < sr or ro > er:
                                continue
                            ex1 = (c * s.grid_w - l) * s.zoom_level
                            ey1 = (ro * s.grid_h - t) * s.zoom_level
                            ex2 = (min((c + 1) * s.grid_w, s.real_width) - l) * s.zoom_level
                            ey2 = (min((ro + 1) * s.grid_h, s.real_height) - t) * s.zoom_level
                            if (c - 1, ro) not in slice_cells:
                                self.canvas.create_line(ex1, ey1, ex1, ey2, fill=tile_color, width=3)
                            if (c + 1, ro) not in slice_cells:
                                self.canvas.create_line(ex2, ey1, ex2, ey2, fill=tile_color, width=3)
                            if (c, ro - 1) not in slice_cells:
                                self.canvas.create_line(ex1, ey1, ex2, ey1, fill=tile_color, width=3)
                            if (c, ro + 1) not in slice_cells:
                                self.canvas.create_line(ex1, ey2, ex2, ey2, fill=tile_color, width=3)

                    # Grid lines (only in grid mode)
                    cx = sc * s.grid_w
                    if cx < l: cx += s.grid_w
                    while cx < r:
                        sx = (cx - l) * s.zoom_level
                        self.canvas.create_line(sx, 0, sx, h_can, fill=s.grid_color, dash=(2, 4))
                        cx += s.grid_w
                    cy = sr * s.grid_h
                    if cy < t: cy += s.grid_h
                    while cy < b:
                        sy = (cy - t) * s.zoom_level
                        self.canvas.create_line(0, sy, w_can, sy, fill=s.grid_color, dash=(2, 4))
                        cy += s.grid_h

        except Exception as e:
            print(f"Redraw error: {e}")
            import traceback; traceback.print_exc()

        # Scale bar overlay (only when microns_per_pixel is set)
        self._draw_scale_bar()

    def _draw_scale_bar(self):
        """Draw a scale bar in the bottom-right corner of the canvas."""
        s = self.current_session
        if not s:
            return

        # Find microns_per_pixel from any tile's metadata
        mpp = None
        for meta in s.slice_metadata:
            try:
                val = meta.get("microns_per_pixel", "")
                if val:
                    mpp = float(val)
                    break
            except (ValueError, TypeError):
                continue
        if not mpp:
            return

        w_can = self.canvas.winfo_width()
        h_can = self.canvas.winfo_height()

        # Calculate a nice bar length: aim for ~100-200 px on screen
        # pixels_per_micron at current zoom
        ppm = s.zoom_level / mpp  # screen pixels per micron

        # Choose a nice round value in microns
        target_px = 150
        target_um = target_px / ppm
        nice_values = [1, 2, 5, 10, 20, 50, 100, 200, 500,
                       1000, 2000, 5000, 10000, 20000, 50000]
        bar_um = nice_values[0]
        for v in nice_values:
            if v >= target_um:
                bar_um = v
                break
        else:
            bar_um = nice_values[-1]

        bar_px = int(bar_um * ppm)
        if bar_px < 20 or bar_px > w_can - 20:
            return

        # Label
        if bar_um >= 1000:
            label = f"{bar_um / 1000:.0f} mm"
        else:
            label = f"{bar_um:.0f} µm"

        # Position: bottom-right corner
        margin = 20
        x2 = w_can - margin
        x1 = x2 - bar_px
        y = h_can - margin

        # Draw background for readability
        self.canvas.create_rectangle(x1 - 5, y - 20, x2 + 5, y + 8,
                                     fill="#000000", stipple="gray50", outline="")
        # Bar line
        self.canvas.create_line(x1, y, x2, y, fill="white", width=3)
        # End caps
        self.canvas.create_line(x1, y - 6, x1, y + 6, fill="white", width=2)
        self.canvas.create_line(x2, y - 6, x2, y + 6, fill="white", width=2)
        # Label
        self.canvas.create_text((x1 + x2) / 2, y - 10, text=label,
                                fill="white", font=("Segoe UI", 9, "bold"))
