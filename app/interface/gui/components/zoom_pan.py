import tkinter as tk


class ZoomPanMixin:
    """Mixin for zoom, pan, and scroll handling."""

    def _setup_zoom_controls(self):
        f = tk.Frame(self.toolbar, bg=self.colors["toolbar"])
        f.pack(side=tk.LEFT, padx=3)
        
        self.ui.create_button(f, "−", self.zoom_out_btn, style_type="zoom", width=2, pady=2)
        
        self.zoom_label = tk.Label(f, text="100%", bg=self.colors["toolbar"], fg="white", 
                                   font=("Segoe UI", 9), width=5)
        self.zoom_label.pack(side=tk.LEFT, padx=2)
        
        self.ui.create_button(f, "+", self.zoom_in_btn, style_type="zoom", width=2, pady=2)
        
        self.ui.create_button(f, "⟲", self.zoom_reset_btn, style_type="zoom", width=2, padx=(3,0), pady=2)

    def zoom_in_btn(self):
        if self.current_session:
            w_can = self.canvas.winfo_width()
            h_can = self.canvas.winfo_height()
            self.apply_zoom(1.25, w_can // 2, h_can // 2)

    def zoom_out_btn(self):
        if self.current_session:
            w_can = self.canvas.winfo_width()
            h_can = self.canvas.winfo_height()
            self.apply_zoom(0.8, w_can // 2, h_can // 2)

    def zoom_reset_btn(self):
        if self.current_session:
            s = self.current_session
            w_can = self.canvas.winfo_width()
            h_can = self.canvas.winfo_height()
            if w_can > 10 and h_can > 10:
                ratio = min(w_can / s.real_width, h_can / s.real_height)
                s.zoom_level = ratio * 0.9
                s.camera_x = 0
                s.camera_y = 0
                self.redraw()

    def _update_zoom_label(self):
        if self.current_session:
            pct = int(self.current_session.zoom_level * 100)
            self.zoom_label.config(text=f"{pct}%")

    def apply_zoom(self, factor, mx, my):
        s = self.current_session
        if not s: return
        new_zoom = s.zoom_level * factor
        if new_zoom < 0.001: return
        wx = s.camera_x + (mx / s.zoom_level)
        wy = s.camera_y + (my / s.zoom_level)
        s.zoom_level = new_zoom
        s.camera_x = wx - (mx / new_zoom)
        s.camera_y = wy - (my / new_zoom)
        self.redraw()
        self._update_zoom_label()

    def on_pan_start(self, e):
        self.last_mouse_x = e.x
        self.last_mouse_y = e.y
        
    def on_pan_move(self, e):
        if self.current_session:
            dx = e.x - self.last_mouse_x
            dy = e.y - self.last_mouse_y
            self.current_session.camera_x -= dx / self.current_session.zoom_level
            self.current_session.camera_y -= dy / self.current_session.zoom_level
            self.last_mouse_x = e.x
            self.last_mouse_y = e.y
            self.redraw()

    def _get_scroll_delta(self, event):
        if self.is_mac:
            return event.delta * 10 
        else:
            return (event.delta / 120) * 30

    def on_scroll(self, e): 
        if not self.current_session:
            return
        
        if self.is_mac:
            shift_held = (e.state & 0x1) != 0
            cmd_held = (e.state & 0x8) != 0
            option_held = (e.state & 0x10) != 0
            
            if cmd_held or option_held:
                factor = 1.05 if e.delta > 0 else 0.95
                self.apply_zoom(factor, e.x, e.y)
            elif shift_held:
                delta = self._get_scroll_delta(e)
                self.current_session.camera_x -= delta / self.current_session.zoom_level
                self.redraw()
            else:
                delta = self._get_scroll_delta(e)
                self.current_session.camera_y -= delta / self.current_session.zoom_level
                self.redraw()
        else:
            shift_held = (e.state & 0x1) != 0
            if shift_held:
                delta = self._get_scroll_delta(e)
                self.current_session.camera_x -= delta / self.current_session.zoom_level
                self.redraw()
            else:
                delta = self._get_scroll_delta(e)
                self.current_session.camera_y -= delta / self.current_session.zoom_level
                self.redraw()
            
    def on_zoom_scroll(self, e):
        if self.is_mac:
            factor = 1.05 if e.delta > 0 else 0.95
        else:
            factor = 1.2 if e.delta > 0 else 0.8
        self.apply_zoom(factor, e.x, e.y)
