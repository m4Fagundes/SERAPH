import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk


class SlicePreviewsMixin:
    """Mixin for the sidebar slice/tile preview panel."""

    def _toggle_session_collapse(self, session_name):
        """Toggle collapsed state of a session group in slice previews."""
        if session_name in self._collapsed_sessions:
            self._collapsed_sessions.discard(session_name)
        else:
            self._collapsed_sessions.add(session_name)
        self._update_slice_previews()

    def _delete_slice(self, session, slice_idx):
        """Delete a single slice from a session."""
        if slice_idx < 0 or slice_idx >= len(session.selected_cells):
            return
        self.undo_manager.push(session, "delete_tile")
        session.selected_cells.pop(slice_idx)
        if slice_idx < len(session.selected_polygons):
            session.selected_polygons.pop(slice_idx)
        if slice_idx < len(session.slice_metadata):
            session.slice_metadata.pop(slice_idx)
        session.sync_metadata()

        # Close inspector if it was showing this slice
        if (hasattr(self, '_insp_session') and self._insp_session is session
                and hasattr(self, '_insp_slice_idx') and self._insp_slice_idx == slice_idx):
            self._close_slice_inspector()
            return  # _close_slice_inspector already redraws

        self.redraw()
        self._update_slice_previews()
        self.trigger_modification()
        self._auto_reexport(session)

    def _delete_all_slices(self, session):
        """Delete all slices from a session (with confirmation)."""
        n = len(session.selected_cells)
        if n == 0:
            return
        if not messagebox.askyesno("Confirm", f"Delete all {n} tile(s) from {session.name}?"):
            return
        self.undo_manager.push(session, "delete_all")
        session.selected_cells.clear()
        session.selected_polygons.clear()
        session.slice_metadata.clear()
        session.sync_metadata()

        # Close inspector if showing a slice of this session
        if hasattr(self, '_insp_session') and self._insp_session is session:
            self._close_slice_inspector()
            return

        self.redraw()
        self._update_slice_previews()
        self.trigger_modification()
        self._auto_reexport(session)

    def _update_slice_previews(self):
        """Rebuild the slice preview panel with full-width vertical thumbnail cards."""
        # Clear existing
        for w in self._slice_inner.winfo_children():
            w.destroy()
        self._slice_thumbs.clear()

        total_slices = sum(len(s.selected_cells) for s in self.sessions)
        self.slice_header.config(text=f"TILES ({total_slices})")

        if total_slices == 0:
            empty = tk.Label(self._slice_inner, text="Right-click cells to\ncreate tiles",
                     bg=self.colors["sidebar"], fg="#555",
                     font=("Segoe UI", 9, "italic"), justify="center")
            empty.pack(pady=30)
            empty.bind("<MouseWheel>", lambda e: self._slice_canvas.yview_scroll(-1 * (e.delta // 120), "units"))
            return

        thumb_max_w = 220  # Full width card thumbnail

        for session in self.sessions:
            if not session.selected_cells:
                continue

            n = len(session.selected_cells)
            collapsed = session.name in self._collapsed_sessions
            arrow = "▶" if collapsed else "▼"

            # Session header (clickable to collapse)
            header = tk.Frame(self._slice_inner, bg="#2d2d2d", cursor="hand2")
            header.pack(fill=tk.X, pady=(6, 0), padx=4)
            hdr_text = f" {arrow}  {session.name}  ({n})"
            lbl = tk.Label(header, text=hdr_text,
                          bg="#2d2d2d", fg="#ccc",
                          font=("Segoe UI", 9, "bold"), anchor="w")
            lbl.pack(fill=tk.X, padx=6, pady=4, side=tk.LEFT, expand=True)
            name = session.name
            for widget in (lbl, header):
                widget.bind("<Button-1>", lambda e, n=name: self._toggle_session_collapse(n))
                widget.bind("<MouseWheel>", lambda e: self._slice_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

            # Delete All button in session header
            del_all_btn = tk.Button(header, text="🗑️",
                                    command=lambda sr=session: self._delete_all_slices(sr),
                                    bg="#c0392b", fg="white", relief="flat",
                                    font=("Segoe UI", 8), padx=4, pady=1,
                                    activebackground="#e74c3c", activeforeground="white",
                                    cursor="hand2")
            del_all_btn.pack(side=tk.RIGHT, padx=(0, 6), pady=4)

            if collapsed:
                continue

            # Vertical card list
            for idx, slice_rects in enumerate(session.selected_cells):
                try:
                    # Bounding box
                    bx1 = min(r[0] for r in slice_rects)
                    by1 = min(r[1] for r in slice_rects)
                    bx2 = max(r[2] for r in slice_rects)
                    by2 = max(r[3] for r in slice_rects)
                    orig_w, orig_h = bx2 - bx1, by2 - by1

                    # Use pyramid viewport to generate thumbnail (no RAM image)
                    if session.pyramid_ready and orig_w > 0 and orig_h > 0:
                        ratio = min(thumb_max_w / orig_w, 120 / orig_h)
                        tw = max(1, int(orig_w * ratio))
                        th = max(1, int(orig_h * ratio))
                        crop = session.pyramid.get_viewport(bx1, by1, tw, th, ratio)
                    else:
                        crop = Image.new("RGB", (thumb_max_w, 60), (40, 40, 40))

                    # Apply polygon mask for brush-drawn slices
                    poly = session.selected_polygons[idx] \
                           if idx < len(session.selected_polygons) else None
                    if poly and len(poly) >= 3:
                        from PIL import ImageDraw as _ImageDraw
                        mask = Image.new("L", crop.size, 0)
                        draw = _ImageDraw.Draw(mask)
                        local_pts = [((x - bx1) * ratio, (y - by1) * ratio) for (x, y) in poly]
                        draw.polygon(local_pts, fill=255)
                        # Apply eraser strokes
                        exclusions = session.slice_exclusions[idx] if idx < len(session.slice_exclusions) else []
                        from app.domain.selection import draw_exclusion_rects as _draw_excl
                        _draw_excl(draw, exclusions, bx1, by1, ratio)
                        crop = crop.convert("RGBA")
                        crop.putalpha(mask)

                    tk_thumb = ImageTk.PhotoImage(crop)
                    self._slice_thumbs.append(tk_thumb)

                    # Card frame
                    card = tk.Frame(self._slice_inner, bg="#2a2a2a", padx=0, pady=0)
                    card.pack(fill=tk.X, padx=8, pady=3)

                    # Image
                    img_lbl = tk.Label(card, image=tk_thumb, bg="#222", anchor="center")
                    img_lbl.pack(fill=tk.X, padx=4, pady=(4, 0))

                    # Info row with delete button
                    info_row = tk.Frame(card, bg="#2a2a2a")
                    info_row.pack(fill=tk.X, padx=4, pady=(2, 4))

                    # Color dot indicator
                    tile_color = session.tile_colors[idx] if idx < len(session.tile_colors) else "#00FFFF"
                    dot = tk.Canvas(info_row, width=10, height=10, bg="#2a2a2a",
                                   highlightthickness=0)
                    dot.create_oval(1, 1, 9, 9, fill=tile_color, outline="")
                    dot.pack(side=tk.LEFT, padx=(4, 0))

                    tile_name = session.slice_metadata[idx].get("name", "") if idx < len(session.slice_metadata) else ""
                    label_text = tile_name if tile_name else f"Tile {idx+1}"
                    info = tk.Label(info_row, text=f"  {label_text}   •   {orig_w}×{orig_h}px",
                                   bg="#2a2a2a", fg="#999", anchor="w",
                                   font=("Segoe UI", 8))
                    info.pack(side=tk.LEFT, fill=tk.X, expand=True)

                    del_btn = tk.Button(info_row, text="🗑️",
                                        command=lambda sr=session, si=idx: self._delete_slice(sr, si),
                                        bg="#c0392b", fg="white", relief="flat",
                                        font=("Segoe UI", 8), padx=4, pady=0,
                                        activebackground="#e74c3c", activeforeground="white",
                                        cursor="hand2")
                    del_btn.pack(side=tk.RIGHT, padx=(2, 2))

                    # Propagate mousewheel from all card children
                    for w in (card, img_lbl, info, info_row):
                        w.bind("<MouseWheel>", lambda e: self._slice_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

                    # Click to open inspector
                    sess_ref = session
                    slice_idx = idx
                    for w in (card, img_lbl, info):
                        w.configure(cursor="hand2")
                        w.bind("<Button-1>", lambda e, sr=sess_ref, si=slice_idx: self._open_slice_inspector(sr, si))

                except Exception as ex:
                    print(f"Slice preview error: {ex}")
