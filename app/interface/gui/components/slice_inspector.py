import tkinter as tk
from PIL import Image, ImageTk
from app.domain.selection import (
    rect_to_cells, find_connected_components, cells_to_rects,
    draw_exclusion_rects,
)


class SliceInspectorMixin:
    """Mixin for the tile detail inspector view."""

    def _open_slice_inspector(self, session, slice_idx):
        """Open a detail inspector for a specific slice with full-res navigation."""
        print(f"Opening inspector: session={session.name}, slice_idx={slice_idx}")
        # Close existing inspector first (one at a time)
        if hasattr(self, '_inspector_frame') and self._inspector_frame:
            self._save_inspector_metadata()
            self._inspector_frame.destroy()
            self._inspector_frame = None

        session.sync_metadata()
        meta = session.slice_metadata[slice_idx]
        slice_rects = session.selected_cells[slice_idx]

        # Bounding box
        bx1 = min(r[0] for r in slice_rects)
        by1 = min(r[1] for r in slice_rects)
        bx2 = max(r[2] for r in slice_rects)
        by2 = max(r[3] for r in slice_rects)
        orig_w, orig_h = bx2 - bx1, by2 - by1

        # Store bounding box instead of cropping full image into RAM
        self._insp_slice_bbox = (bx1, by1, bx2, by2)
        self._insp_slice_w = orig_w
        self._insp_slice_h = orig_h
        self._insp_zoom = 1.0
        self._insp_cam_x = 0.0
        self._insp_cam_y = 0.0

        # Hide main canvas, show inspector
        self.canvas.pack_forget()

        self._inspector_frame = tk.Frame(self.canvas_area, bg="#1e1e1e")
        self._inspector_frame.pack(fill=tk.BOTH, expand=True)

        # --- Top header bar ---
        header = tk.Frame(self._inspector_frame, bg="#2d2d2d")
        header.pack(fill=tk.X)

        back_btn = tk.Button(header, text="\u2190 Back to Grid",
                            command=lambda: self._close_slice_inspector(),
                            bg="#444", fg="white", relief="flat",
                            font=("Segoe UI", 10), padx=12, pady=4,
                            activebackground="#555", activeforeground="white",
                            cursor="hand2")
        back_btn.pack(side=tk.LEFT, padx=10, pady=6)

        tile_name = meta.get("name", "") if meta else ""
        header_label = tile_name if tile_name else f"Tile {slice_idx+1}"
        tk.Label(header, text=f"{header_label}  \u2014  {session.name}",
                 bg="#2d2d2d", fg="#ccc", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT, padx=8, pady=6)

        self._insp_zoom_label = tk.Label(header, text="100%", bg="#2d2d2d", fg="#888",
                                          font=("Segoe UI", 9))
        self._insp_zoom_label.pack(side=tk.RIGHT, padx=10, pady=6)

        tk.Label(header, text=f"{orig_w}\u00d7{orig_h} px", bg="#2d2d2d", fg="#888",
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT, padx=5, pady=6)

        # Grid cell size control for eraser
        self._insp_grid_size = 1  # default: 1 image pixel per cell
        grid_frame = tk.Frame(header, bg="#2d2d2d")
        grid_frame.pack(side=tk.RIGHT, padx=8, pady=4)
        tk.Label(grid_frame, text="Grid", bg="#2d2d2d", fg="#FF6666",
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(grid_frame, text="\u2212", command=self._insp_grid_shrink,
                  bg="#444", fg="white", relief="flat", font=("Segoe UI", 9, "bold"),
                  width=2, padx=0, pady=0, cursor="hand2",
                  activebackground="#555", activeforeground="white").pack(side=tk.LEFT, padx=1)
        self._insp_grid_label = tk.Label(grid_frame, text="1px",
                                         bg="#2d2d2d", fg="#FF9999",
                                         font=("Segoe UI", 9), width=5)
        self._insp_grid_label.pack(side=tk.LEFT)
        tk.Button(grid_frame, text="+", command=self._insp_grid_grow,
                  bg="#444", fg="white", relief="flat", font=("Segoe UI", 9, "bold"),
                  width=2, padx=0, pady=0, cursor="hand2",
                  activebackground="#555", activeforeground="white").pack(side=tk.LEFT, padx=1)

        # --- Content: Canvas (left) + Properties (right) ---
        content = tk.Frame(self._inspector_frame, bg="#1e1e1e")
        content.pack(fill=tk.BOTH, expand=True)

        # Full-res navigable canvas
        self._insp_canvas = tk.Canvas(content, bg="#111", highlightthickness=0)
        self._insp_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Left-click drag: pan (movement)
        self._insp_canvas.bind("<ButtonPress-1>", self._insp_pan_start)
        self._insp_canvas.bind("<B1-Motion>", self._insp_pan_move)

        # Right-click: toggle grid cell (erase/fill)
        self._insp_canvas.bind("<ButtonPress-3>", self._insp_cell_start)
        self._insp_canvas.bind("<B3-Motion>", self._insp_cell_drag)
        self._insp_canvas.bind("<ButtonRelease-3>", self._insp_cell_end)
        self._insp_canvas.bind("<Motion>", self._insp_show_cell_cursor)

        # Zoom and resize
        self._insp_canvas.bind("<MouseWheel>", self._insp_on_scroll)
        self._insp_canvas.bind("<Configure>", lambda e: self._insp_redraw())

        # --- Right properties panel ---
        props_panel = tk.Frame(content, width=280, bg="#252526")
        props_panel.pack(side=tk.RIGHT, fill=tk.Y)
        props_panel.pack_propagate(False)

        # Scrollable properties
        props_canvas = tk.Canvas(props_panel, bg="#252526", highlightthickness=0, bd=0)
        props_scroll = tk.Scrollbar(props_panel, orient="vertical", command=props_canvas.yview)
        props_inner = tk.Frame(props_canvas, bg="#252526")

        props_win = props_canvas.create_window((0, 0), window=props_inner, anchor="nw")
        props_canvas.configure(yscrollcommand=props_scroll.set)

        def _on_props_configure(e):
            props_canvas.itemconfig(props_win, width=e.width)
        props_canvas.bind("<Configure>", _on_props_configure)
        props_inner.bind("<Configure>", lambda e: props_canvas.configure(scrollregion=props_canvas.bbox("all")))
        props_canvas.bind("<MouseWheel>", lambda e: props_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        props_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        props_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Properties header
        tk.Label(props_inner, text="PROPERTIES", bg="#252526", fg="#888",
                 font=("Segoe UI", 8, "bold"), anchor="w").pack(fill=tk.X, padx=12, pady=(12, 8))

        # Field builder
        def add_field(parent, label, value, editable=False):
            row = tk.Frame(parent, bg="#252526")
            row.pack(fill=tk.X, padx=12, pady=3)
            tk.Label(row, text=label, bg="#252526", fg="#999",
                     font=("Segoe UI", 9), anchor="w").pack(fill=tk.X)
            if editable:
                entry = tk.Entry(row, bg="#333", fg="white", relief="flat",
                                font=("Segoe UI", 10), insertbackground="white")
                entry.insert(0, str(value) if value else "")
                entry.pack(fill=tk.X, pady=(2, 0))
                return entry
            else:
                tk.Label(row, text=str(value), bg="#252526", fg="#ddd",
                         font=("Segoe UI", 10), anchor="w").pack(fill=tk.X)
                return None

        # Editable tile name
        self._insp_name = add_field(props_inner, "Tile Name", meta.get("name", ""), editable=True)

        # Separator
        tk.Frame(props_inner, height=1, bg="#3a3a3a").pack(fill=tk.X, padx=12, pady=8)

        # Read-only fields
        add_field(props_inner, "Resolution", f"{orig_w} \u00d7 {orig_h} px")
        add_field(props_inner, "Rectangles", f"{len(slice_rects)} rect(s)")
        add_field(props_inner, "Source", session.name)

        # Separator
        tk.Frame(props_inner, height=1, bg="#3a3a3a").pack(fill=tk.X, padx=12, pady=8)

        # Microns per pixel
        self._insp_microns = add_field(props_inner, "Microns / pixel", meta.get("microns_per_pixel", ""), editable=True)

        # Auto-calculated physical size
        self._insp_phys_label = tk.Label(props_inner, text="", bg="#252526", fg="#7cb342",
                                          font=("Segoe UI", 9, "italic"), anchor="w")
        self._insp_phys_label.pack(fill=tk.X, padx=12, pady=(0, 6))

        def _update_phys_size(*args):
            try:
                mpp = float(self._insp_microns.get())
                phys_w = orig_w * mpp
                phys_h = orig_h * mpp
                if phys_w >= 1000:
                    self._insp_phys_label.config(text=f"{phys_w/1000:.2f} \u00d7 {phys_h/1000:.2f} mm")
                else:
                    self._insp_phys_label.config(text=f"{phys_w:.1f} \u00d7 {phys_h:.1f} \u00b5m")
            except (ValueError, TypeError):
                self._insp_phys_label.config(text="")

        self._insp_microns.bind("<KeyRelease>", _update_phys_size)
        _update_phys_size()

        # Separator
        tk.Frame(props_inner, height=1, bg="#3a3a3a").pack(fill=tk.X, padx=12, pady=8)

        # Description
        tk.Label(props_inner, text="DESCRIPTION", bg="#252526", fg="#888",
                 font=("Segoe UI", 8, "bold"), anchor="w").pack(fill=tk.X, padx=12, pady=(0, 4))

        self._insp_desc = tk.Text(props_inner, bg="#333", fg="white", relief="flat",
                                  font=("Segoe UI", 10), height=6,
                                  insertbackground="white", wrap="word")
        self._insp_desc.insert("1.0", meta.get("description", ""))
        self._insp_desc.pack(fill=tk.X, padx=12, pady=(0, 12))

        # Store refs for saving
        self._insp_session = session
        self._insp_slice_idx = slice_idx
        self._insp_tk_img = None

        # Initial fit-to-view
        self._inspector_frame.update_idletasks()
        cw = self._insp_canvas.winfo_width()
        ch = self._insp_canvas.winfo_height()
        if cw > 10 and ch > 10:
            self._insp_zoom = min(cw / orig_w, ch / orig_h) * 0.9
        self._insp_redraw()

    def _insp_clamp_camera(self):
        """Clamp inspector camera so the tile never fully leaves the viewport."""
        if not hasattr(self, '_insp_canvas') or not hasattr(self, '_insp_slice_w'):
            return
        cw = self._insp_canvas.winfo_width()
        ch = self._insp_canvas.winfo_height()
        z  = self._insp_zoom
        # Keep at least 50 screen-px of the tile visible on each axis
        margin = 50 / z
        self._insp_cam_x = max(-cw / z + margin,
                               min(self._insp_cam_x, self._insp_slice_w - margin))
        self._insp_cam_y = max(-ch / z + margin,
                               min(self._insp_cam_y, self._insp_slice_h - margin))

    def _insp_redraw(self):
        """Redraw the inspector canvas — renders only the selected tile region."""
        if not hasattr(self, '_insp_canvas') or not hasattr(self, '_insp_slice_bbox'):
            return
        if self._insp_slice_bbox is None:
            return
        c = self._insp_canvas
        c.delete("all")

        cw = c.winfo_width()
        ch = c.winfo_height()
        if cw < 2 or ch < 2:
            return

        # Clamp camera before rendering so we never show pixels outside the tile
        self._insp_clamp_camera()

        bx1, by1, bx2, by2 = self._insp_slice_bbox
        z = self._insp_zoom
        cx, cy = self._insp_cam_x, self._insp_cam_y

        # Inspector camera is in slice-local coords; convert to full-image coords
        img_cam_x = bx1 + cx
        img_cam_y = by1 + cy

        # Use pyramid viewport for rendering
        session = self._insp_session
        if session and session.pyramid_ready:
            img = session.pyramid.get_viewport(img_cam_x, img_cam_y, cw, ch, z)
        else:
            img = Image.new("RGB", (cw, ch), (20, 20, 20))

        # Apply polygon mask for brush-drawn slices
        idx = getattr(self, '_insp_slice_idx', None)
        poly = None
        if session and idx is not None and idx < len(session.selected_polygons):
            poly = session.selected_polygons[idx]
        if poly and len(poly) >= 3:
            from PIL import ImageDraw as _ImageDraw
            mask = Image.new("L", img.size, 0)
            draw = _ImageDraw.Draw(mask)
            screen_pts = [((x - img_cam_x) * z, (y - img_cam_y) * z) for (x, y) in poly]
            draw.polygon(screen_pts, fill=255)
            # Apply exclusion rects
            exclusions = session.slice_exclusions[idx] if idx < len(session.slice_exclusions) else []
            draw_exclusion_rects(draw, exclusions, img_cam_x, img_cam_y, z)
            img = img.convert("RGBA")
            img.putalpha(mask)

        self._insp_tk_img = ImageTk.PhotoImage(img)
        c.create_image(0, 0, anchor="nw", image=self._insp_tk_img)

        # Mask area outside tile boundary with dark overlay
        tile_left   = (0    - cx) * z
        tile_top    = (0    - cy) * z
        tile_right  = (self._insp_slice_w - cx) * z
        tile_bottom = (self._insp_slice_h - cy) * z

        bg = "#111"  # matches canvas background
        # Top overlay
        if tile_top > 0:
            c.create_rectangle(0, 0, cw, tile_top, fill=bg, outline="")
        # Bottom overlay
        if tile_bottom < ch:
            c.create_rectangle(0, tile_bottom, cw, ch, fill=bg, outline="")
        # Left overlay (between top and bottom)
        if tile_left > 0:
            c.create_rectangle(0, max(0, tile_top), tile_left, min(ch, tile_bottom), fill=bg, outline="")
        # Right overlay (between top and bottom)
        if tile_right < cw:
            c.create_rectangle(tile_right, max(0, tile_top), cw, min(ch, tile_bottom), fill=bg, outline="")

        # Draw grid lines over the tile for cell visibility
        session = self._insp_session
        if session and not poly:
            bx1, by1 = self._insp_slice_bbox[0], self._insp_slice_bbox[1]
            gw, gh = session.grid_w, session.grid_h

            # Vertical grid lines
            first_col = int(bx1 // gw)
            img_cam_x_local = bx1 + cx
            img_cam_y_local = by1 + cy
            gx = (first_col + 1) * gw
            while gx < self._insp_slice_bbox[2]:
                sx = (gx - img_cam_x_local) * z
                if 0 <= sx <= cw:
                    c.create_line(sx, max(0, tile_top), sx, min(ch, tile_bottom),
                                  fill="#444", dash=(2, 4))
                gx += gw

            # Horizontal grid lines
            first_row = int(by1 // gh)
            gy = (first_row + 1) * gh
            while gy < self._insp_slice_bbox[3]:
                sy = (gy - img_cam_y_local) * z
                if 0 <= sy <= ch:
                    c.create_line(max(0, tile_left), sy, min(cw, tile_right), sy,
                                  fill="#444", dash=(2, 4))
                gy += gh

            # Draw cell boundaries to show which cells belong to this tile
            slice_rects = session.selected_cells[idx] if idx < len(session.selected_cells) else set()
            tile_cells = set()
            for rect in slice_rects:
                tile_cells |= rect_to_cells(rect, gw, gh)

            for (tc, tr) in tile_cells:
                ex1 = (tc * gw - img_cam_x_local) * z
                ey1 = (tr * gh - img_cam_y_local) * z
                ex2 = (min((tc + 1) * gw, session.real_width) - img_cam_x_local) * z
                ey2 = (min((tr + 1) * gh, session.real_height) - img_cam_y_local) * z
                # Draw visible border only on edges that face a non-selected neighbor
                if (tc - 1, tr) not in tile_cells:
                    c.create_line(ex1, ey1, ex1, ey2, fill="#00AAFF", width=2)
                if (tc + 1, tr) not in tile_cells:
                    c.create_line(ex2, ey1, ex2, ey2, fill="#00AAFF", width=2)
                if (tc, tr - 1) not in tile_cells:
                    c.create_line(ex1, ey1, ex2, ey1, fill="#00AAFF", width=2)
                if (tc, tr + 1) not in tile_cells:
                    c.create_line(ex1, ey2, ex2, ey2, fill="#00AAFF", width=2)

        # Update zoom label
        if hasattr(self, '_insp_zoom_label'):
            self._insp_zoom_label.config(text=f"{int(z * 100)}%")

    def _insp_pan_start(self, e):
        self._insp_last_x = e.x
        self._insp_last_y = e.y

    def _insp_pan_move(self, e):
        dx = e.x - self._insp_last_x
        dy = e.y - self._insp_last_y
        self._insp_cam_x -= dx / self._insp_zoom
        self._insp_cam_y -= dy / self._insp_zoom
        self._insp_last_x = e.x
        self._insp_last_y = e.y
        self._insp_clamp_camera()
        self._insp_redraw()

    def _insp_on_scroll(self, e):
        ctrl = (e.state & 0x4) != 0
        if ctrl or True:  # always zoom on scroll in inspector
            factor = 1.25 if e.delta > 0 else 0.8
            new_zoom = self._insp_zoom * factor
            if new_zoom < 0.01:
                return
            # Zoom centered on mouse
            wx = self._insp_cam_x + (e.x / self._insp_zoom)
            wy = self._insp_cam_y + (e.y / self._insp_zoom)
            self._insp_zoom = new_zoom
            self._insp_cam_x = wx - (e.x / new_zoom)
            self._insp_cam_y = wy - (e.y / new_zoom)
            self._insp_clamp_camera()
            self._insp_redraw()

    # ---- Grid cell toggle tool (left-click) ----

    def _insp_grid_shrink(self):
        self._insp_grid_size = max(1, self._insp_grid_size - 1)
        self._insp_grid_label.config(text=f"{self._insp_grid_size}px")
        self._insp_redraw()

    def _insp_grid_grow(self):
        self._insp_grid_size = min(50, self._insp_grid_size + 1)
        self._insp_grid_label.config(text=f"{self._insp_grid_size}px")
        self._insp_redraw()

    def _insp_screen_to_cell(self, sx, sy):
        """Convert screen coords to sub-grid cell (col, row) and rect (x1,y1,x2,y2)."""
        bx1, by1 = self._insp_slice_bbox[0], self._insp_slice_bbox[1]
        ix = bx1 + self._insp_cam_x + sx / self._insp_zoom
        iy = by1 + self._insp_cam_y + sy / self._insp_zoom
        g = self._insp_grid_size
        col = int(ix // g)
        row = int(iy // g)
        return (col * g, row * g, (col + 1) * g, (row + 1) * g)

    def _insp_is_excluded(self, rect):
        """Check if a rect is in the current exclusion list."""
        session = self._insp_session
        idx = self._insp_slice_idx
        if not session or idx is None:
            return False
        exclusions = session.slice_exclusions[idx] if idx < len(session.slice_exclusions) else []
        return tuple(rect) in [tuple(e) for e in exclusions]

    def _insp_show_cell_cursor(self, e):
        """Highlight the grid cell under the mouse."""
        c = self._insp_canvas
        c.delete("cell_cursor")
        rect = self._insp_screen_to_cell(e.x, e.y)
        bx1, by1 = self._insp_slice_bbox[0], self._insp_slice_bbox[1]
        z = self._insp_zoom
        cam_x = bx1 + self._insp_cam_x
        cam_y = by1 + self._insp_cam_y
        sx1 = (rect[0] - cam_x) * z
        sy1 = (rect[1] - cam_y) * z
        sx2 = (rect[2] - cam_x) * z
        sy2 = (rect[3] - cam_y) * z
        color = "#FF3333" if not self._insp_is_excluded(rect) else "#33FF33"
        c.create_rectangle(sx1, sy1, sx2, sy2, outline=color, width=2, tags="cell_cursor")

    def _insp_cell_start(self, e):
        """Start toggling grid cells — decide mode (erase or fill)."""
        session = self._insp_session
        idx = self._insp_slice_idx
        if not session or idx is None:
            return

        self.undo_manager.push(session, "insp_grid_toggle")
        session.sync_metadata()

        rect = self._insp_screen_to_cell(e.x, e.y)
        is_excluded = self._insp_is_excluded(rect)

        # Mode: True = erasing, False = filling
        self._insp_toggle_mode = not is_excluded
        self._insp_toggled_cells = set()
        self._insp_toggle_cell(rect)

    def _insp_toggle_cell(self, rect):
        """Toggle a single cell based on current mode."""
        rect_t = tuple(rect)
        if rect_t in self._insp_toggled_cells:
            return  # already toggled this drag
        self._insp_toggled_cells.add(rect_t)

        session = self._insp_session
        idx = self._insp_slice_idx
        excl = session.slice_exclusions[idx]

        if self._insp_toggle_mode:  # erasing
            if rect_t not in [tuple(e) for e in excl]:
                excl.append(rect_t)
        else:  # filling back
            session.slice_exclusions[idx] = [e for e in excl if tuple(e) != rect_t]

        self._insp_redraw()

    def _insp_cell_drag(self, e):
        """Continue toggling cells while dragging."""
        if not hasattr(self, '_insp_toggle_mode'):
            return
        rect = self._insp_screen_to_cell(e.x, e.y)
        self._insp_toggle_cell(rect)

    def _insp_cell_end(self, e):
        """Finish cell toggle — update previews and trigger save."""
        if not hasattr(self, '_insp_toggle_mode'):
            return
        self._insp_toggle_mode = None
        self._insp_toggled_cells = None
        self._insp_redraw()
        self.redraw()
        self._update_slice_previews()
        self.trigger_modification()
        session = self._insp_session
        if session:
            self._auto_reexport(session)

    def _save_inspector_metadata(self):
        """Save current inspector field values to metadata."""
        if hasattr(self, '_insp_session') and self._insp_session:
            session = self._insp_session
            idx = self._insp_slice_idx
            session.sync_metadata()
            if idx < len(session.slice_metadata):
                try:
                    session.slice_metadata[idx]["name"] = self._insp_name.get().strip()
                    session.slice_metadata[idx]["microns_per_pixel"] = self._insp_microns.get().strip()
                    session.slice_metadata[idx]["description"] = self._insp_desc.get("1.0", "end-1c").strip()
                except Exception:
                    pass

    def _close_slice_inspector(self):
        """Close inspector, save metadata, return to grid."""
        self._save_inspector_metadata()

        # Cleanup
        if hasattr(self, '_inspector_frame') and self._inspector_frame:
            self._inspector_frame.destroy()
        self._inspector_frame = None
        self._insp_slice_bbox = None
        self._insp_tk_img = None
        self._insp_session = None

        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.redraw()
        self._update_slice_previews()
        self.trigger_modification()

    def _delete_current_tile(self):
        """Delete key: delete tile if inspector is open."""
        if (hasattr(self, '_insp_session') and self._insp_session
                and hasattr(self, '_insp_slice_idx')):
            self._delete_slice(self._insp_session, self._insp_slice_idx)
