import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser, ttk
from PIL import Image, ImageTk
import os
import platform
from app.domain.session import ImageSession
from app.interface.gui.utils import detect_dark_mode_mac
from app.interface.gui.components import UIComponents, setup_ttk_styles
from app.application.services import ProjectService, ExportService
from app.domain.selection import subtract_from_slice, rect_to_cells

class SlicerLabApp:
    # Supported export formats
    EXPORT_FORMATS = [
        ("PNG", ".png"),
        ("JPEG", ".jpg"),
        ("TIFF", ".tiff"),
        ("BMP", ".bmp"),
        ("WebP", ".webp")
    ]

    def __init__(self, root):
        self.root = root
        self.is_mac = platform.system() == "Darwin"
        self.is_dark_mode = detect_dark_mode_mac()
        
        self.root.title(f"Slicer Lab Pro - {'macOS' if self.is_mac else 'Windows'}")
        self.root.geometry("1400x900")
        self.root.configure(bg="#1e1e1e")

        self.sessions = []
        self.current_session = None
        self.current_project_path = None
        self.autosave_timer = None
        self.export_format = ".png"
        
        self.tk_image = None
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        
        # Services & Components
        self.ui = UIComponents()
        self.project_service = ProjectService()
        self.export_service = ExportService()

        self._setup_ui()

    def _setup_ui(self):
        self.colors = {"bg": "#1e1e1e", "sidebar": "#252526", "toolbar": "#333333", "accent": "#007acc", "text": "#cccccc"}
        
        setup_ttk_styles()
        
        main = tk.Frame(self.root, bg=self.colors["bg"])
        main.pack(fill=tk.BOTH, expand=True)

        # Sidebar
        self.sidebar = tk.Frame(main, width=250, bg=self.colors["sidebar"])
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        
        tk.Label(self.sidebar, text="PROJECT / IMAGES", bg=self.colors["sidebar"], fg="#888", font=("Segoe UI", 8, "bold"), anchor="w").pack(fill=tk.X, padx=10, pady=(10,5))
        self.file_list = tk.Listbox(self.sidebar, bg=self.colors["sidebar"], fg=self.colors["text"], selectbackground="#37373d", selectforeground="white", bd=0, highlightthickness=0, font=("Segoe UI", 10), activestyle="none")
        self.file_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.file_list.bind("<<ListboxSelect>>", self.switch_image_tab)
        
        self.ui.create_button(self.sidebar, "+ Add Image", self.add_image_btn, style_type="accent", padx=10, pady=10, fill=tk.X)

        # Main Area
        content = tk.Frame(main, bg=self.colors["bg"])
        content.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.toolbar = tk.Frame(content, bg=self.colors["toolbar"], height=50)
        self.toolbar.pack(fill=tk.X)
        
        # Project Menu
        self._setup_project_menu()
        tk.Frame(self.toolbar, width=1, bg="#555").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        self._setup_grid_inputs()
        self._add_toolbar_btn("🎨", self.choose_color, tooltip="Grid Color")
        tk.Frame(self.toolbar, width=1, bg="#555").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Zoom Controls
        self._setup_zoom_controls()
        tk.Frame(self.toolbar, width=1, bg="#555").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Export Format
        self._setup_format_selector()
        tk.Frame(self.toolbar, width=1, bg="#555").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Slice Buttons
        self._add_toolbar_btn("✂️ Slice", self.save_selected_cells, bg="#27ae60", tooltip="Slice Selected Cells")
        self._add_toolbar_btn("🔲 All", self.slice_all, bg="#27ae60", tooltip="Slice All Grid")
        
        # Status label
        self.save_status_label = tk.Label(self.toolbar, text="", bg=self.colors["toolbar"], fg="#aaa", font=("Segoe UI", 8, "italic"))
        self.save_status_label.pack(side=tk.RIGHT, padx=10)

        # Canvas
        self.canvas_area = tk.Frame(content, bg="black")
        self.canvas_area.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(self.canvas_area, bg="#111", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.status_bar = tk.Label(content, text="Ready. Add an image to start.", bg=self.colors["accent"], fg="white", anchor="w", font=("Segoe UI", 8))
        self.status_bar.pack(fill=tk.X)

        self._setup_binds()

    def _setup_grid_inputs(self):
        f = tk.Frame(self.toolbar, bg=self.colors["toolbar"])
        f.pack(side=tk.LEFT, padx=5)
        tk.Label(f, text="W:", bg=self.colors["toolbar"], fg="white", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.entry_w = tk.Entry(f, width=4, justify="center", bg="#444", fg="white", relief="flat", font=("Segoe UI", 9))
        self.entry_w.insert(0, "1000")
        self.entry_w.pack(side=tk.LEFT, padx=1)
        tk.Label(f, text="H:", bg=self.colors["toolbar"], fg="white", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(3,0))
        self.entry_h = tk.Entry(f, width=4, justify="center", bg="#444", fg="white", relief="flat", font=("Segoe UI", 9))
        self.entry_h.insert(0, "1000")
        self.entry_h.pack(side=tk.LEFT, padx=1)
        
        self.entry_w.bind("<KeyRelease>", lambda e: self.trigger_modification())
        self.entry_h.bind("<KeyRelease>", lambda e: self.trigger_modification())
        self.entry_w.bind("<FocusOut>", lambda e: self.redraw())
        self.entry_h.bind("<FocusOut>", lambda e: self.redraw())

    def _add_toolbar_btn(self, text, command, bg=None, tooltip=None):
        if bg == "#27ae60":
            style_type = "green"
        else:
            style_type = "default"
        self.ui.create_button(self.toolbar, text, command, style_type=style_type)

    def _setup_project_menu(self):
        f = tk.Frame(self.toolbar, bg=self.colors["toolbar"])
        f.pack(side=tk.LEFT, padx=5)
        
        self.project_menubutton = tk.Menubutton(f, text="📁 Project ▾", 
                                                 bg="#444", fg="white", 
                                                 relief="flat", 
                                                 font=("Segoe UI", 10),
                                                 activebackground="#555",
                                                 activeforeground="white",
                                                 padx=10, pady=5)
        self.project_menubutton.pack(side=tk.LEFT)
        
        self.project_menu = tk.Menu(self.project_menubutton, tearoff=0,
                                    bg="#333", fg="white",
                                    activebackground="#007acc",
                                    activeforeground="white",
                                    font=("Segoe UI", 10))
        self.project_menubutton["menu"] = self.project_menu
        
        self.project_menu.add_command(label="📄 New Project", command=self.new_project)
        self.project_menu.add_command(label="📂 Open Project...", command=self.open_project)
        self.project_menu.add_separator()
        self.project_menu.add_command(label="💾 Save As...", command=self.save_project_as)

    def _setup_zoom_controls(self):
        f = tk.Frame(self.toolbar, bg=self.colors["toolbar"])
        f.pack(side=tk.LEFT, padx=3)
        
        self.ui.create_button(f, "−", self.zoom_out_btn, style_type="zoom", width=2, pady=2)
        
        self.zoom_label = tk.Label(f, text="100%", bg=self.colors["toolbar"], fg="white", 
                                   font=("Segoe UI", 9), width=5)
        self.zoom_label.pack(side=tk.LEFT, padx=2)
        
        self.ui.create_button(f, "+", self.zoom_in_btn, style_type="zoom", width=2, pady=2)
        
        self.ui.create_button(f, "⟲", self.zoom_reset_btn, style_type="zoom", width=2, padx=(3,0), pady=2)

    def _setup_format_selector(self):
        f = tk.Frame(self.toolbar, bg=self.colors["toolbar"])
        f.pack(side=tk.LEFT, padx=3)
        
        self.format_var = tk.StringVar(value="PNG")
        format_names = [fmt[0] for fmt in self.EXPORT_FORMATS]
        
        self.format_dropdown = ttk.Combobox(f, textvariable=self.format_var, values=format_names, 
                                            state="readonly", width=5, font=("Segoe UI", 9))
        self.format_dropdown.pack(side=tk.LEFT, padx=2)
        self.format_dropdown.bind("<<ComboboxSelected>>", self._on_format_change)

    def _on_format_change(self, event=None):
        selected = self.format_var.get()
        for name, ext in self.EXPORT_FORMATS:
            if name == selected:
                self.export_format = ext
                break

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

    def _setup_binds(self):
        c = self.canvas
        c.bind("<ButtonPress-1>", self.on_pan_start)
        c.bind("<B1-Motion>", self.on_pan_move)
        
        c.bind("<Button-3>", self.on_right_click) 
        if self.is_mac:
            c.bind("<Button-2>", self.on_right_click)
            c.bind("<Control-Button-1>", self.on_right_click)
        
        c.bind("<MouseWheel>", self.on_scroll)
        
        if not self.is_mac:
            c.bind("<Control-MouseWheel>", self.on_zoom_scroll)
        
        c.bind("<Configure>", self.on_resize)
        self.root.bind("<c>", self.clear_selection)

    def _get_scroll_delta(self, event):
        if self.is_mac:
            return event.delta * 10 
        else:
            return (event.delta / 120) * 30

    def trigger_modification(self, event=None):
        if not self.current_project_path:
            self.save_status_label.config(text="* Unsaved")
            return

        self.save_status_label.config(text="Modified...")
        if self.autosave_timer:
            self.root.after_cancel(self.autosave_timer)
        self.autosave_timer = self.root.after(2000, self._execute_autosave)

    def _execute_autosave(self):
        if self.current_project_path:
            try:
                self._write_project_file(self.current_project_path)
                self.save_status_label.config(text="Auto-saved")
            except Exception as e:
                self.save_status_label.config(text="AutoSave Error")
                print(f"AutoSave Error: {e}")

    def _write_project_file(self, path):
        if self.current_session:
            try:
                self.current_session.grid_w = int(self.entry_w.get())
                self.current_session.grid_h = int(self.entry_h.get())
            except: pass

        self.project_service.save_project(path, self.sessions)

    def new_project(self):
        if self.sessions:
            if not messagebox.askyesno("New Project", "This will close the current project.\nUnsaved changes will be lost.\n\nContinue?"):
                return
        
        self.sessions.clear()
        self.file_list.delete(0, tk.END)
        self.current_session = None
        self.current_project_path = None
        self.canvas.delete("all")
        
        self.entry_w.delete(0, tk.END)
        self.entry_w.insert(0, "1000")
        self.entry_h.delete(0, tk.END)
        self.entry_h.insert(0, "1000")
        
        self.format_var.set("PNG")
        self.export_format = ".png"
        
        self.root.title("Slicer Lab Pro - New Project")
        self.save_status_label.config(text="")
        self.status_bar.config(text="New project created. Add an image to start.")
        self.zoom_label.config(text="100%")

    def save_project_as(self):
        if not self.sessions:
            messagebox.showwarning("Warning", "No images to save.")
            return
            
        f = filedialog.asksaveasfilename(defaultextension=".lab", filetypes=[("Lab Project", "*.lab")])
        if f:
            self.current_project_path = f
            self._write_project_file(f)
            self.root.title(f"Slicer Lab Pro - {os.path.basename(f)}")
            messagebox.showinfo("Success", "Project saved! AutoSave enabled.")

    def open_project(self):
        f = filedialog.askopenfilename(filetypes=[("Lab Project", "*.lab")])
        if not f: return
        
        try:
            sessions = self.project_service.load_project(f)
            self.sessions = sessions

            self.file_list.delete(0, tk.END)
            self.current_session = None
            self.canvas.delete("all")
            
            for s in self.sessions:
                self.file_list.insert(tk.END, f" {s.name}")

            if self.sessions:
                self._activate_session(self.sessions[0])
            
            self.current_project_path = f
            self.root.title(f"Slicer Lab Pro - {os.path.basename(f)}")
            self.save_status_label.config(text="Project Loaded")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error opening project: {e}")
            print(e)

    def add_image_btn(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.bmp;*.webp")])
        if path:
            self._add_session(path)
            self.trigger_modification()

    def _add_session(self, path):
        if self.current_session:
            try:
                self.current_session.grid_w = int(self.entry_w.get())
                self.current_session.grid_h = int(self.entry_h.get())
            except: pass

        try:
            new_session = ImageSession(path)
            self.sessions.append(new_session)
            self.file_list.insert(tk.END, f" {new_session.name}")
            self.file_list.selection_clear(0, tk.END)
            self.file_list.selection_set(tk.END)
            self._activate_session(new_session)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def switch_image_tab(self, event):
        sel = self.file_list.curselection()
        if not sel: return
        idx = sel[0]
        if 0 <= idx < len(self.sessions):
            if self.current_session:
                try:
                    self.current_session.grid_w = int(self.entry_w.get())
                    self.current_session.grid_h = int(self.entry_h.get())
                except: pass
            
            self._activate_session(self.sessions[idx])

    def _activate_session(self, session):
        self.current_session = session
        
        self.entry_w.delete(0, tk.END)
        self.entry_w.insert(0, str(session.grid_w))
        self.entry_h.delete(0, tk.END)
        self.entry_h.insert(0, str(session.grid_h))
        
        if session.zoom_level == 1.0 and session.camera_x == 0:
            w_can = self.canvas.winfo_width()
            if w_can > 10:
                ratio = min(w_can/session.real_width, self.canvas.winfo_height()/session.real_height)
                session.zoom_level = ratio * 0.9

        self.status_bar.config(text=f"Image: {session.name} | Size: {session.real_width}x{session.real_height}px")
        self.redraw()
        self._update_zoom_label()

    def on_resize(self, event):
        if self.current_session: self.redraw()

    def _draw_selection_fill(self, x1, y1, x2, y2):
        """Draw hatching fill only (no border)."""
        line_spacing = 2
        y = y1
        while y < y2:
            self.canvas.create_line(x1, y, x2, y, fill="#00FFFF", width=1)
            y += line_spacing * 2
        x = x1
        while x < x2:
            self.canvas.create_line(x, y1, x, y2, fill="#00FFFF", width=1)
            x += line_spacing * 2

    def redraw(self):
        s = self.current_session
        if not s: return

        try:
            s.grid_w = max(10, int(self.entry_w.get()))
            s.grid_h = max(10, int(self.entry_h.get()))
        except Exception:
            pass

        w_can = self.canvas.winfo_width()
        h_can = self.canvas.winfo_height()
        
        l = s.camera_x
        t = s.camera_y
        r = l + (w_can / s.zoom_level)
        b = t + (h_can / s.zoom_level)

        self.canvas.delete("all")

        use_preview = (s.zoom_level < 0.5 and s.preview_scale > 1.0)
        
        try:
            if use_preview:
                pl = int(l / s.preview_scale)
                pt = int(t / s.preview_scale)
                pr = int(r / s.preview_scale)
                pb = int(b / s.preview_scale)
                img = s.preview_image.crop((pl, pt, pr, pb))
                img = img.resize((w_can, h_can), Image.Resampling.NEAREST)
            else:
                cl = max(0, int(l))
                ct = max(0, int(t))
                cr = min(s.real_width, int(r))
                cb = min(s.real_height, int(b))
                if cr > cl and cb > ct:
                    crop = s.original_image.crop((cl, ct, cr, cb))
                    img = Image.new("RGB", (w_can, h_can), (20,20,20))
                    px = int((cl - l) * s.zoom_level)
                    py = int((ct - t) * s.zoom_level)
                    pw = int((cr - cl) * s.zoom_level)
                    ph = int((cb - ct) * s.zoom_level)
                    if pw>0 and ph>0:
                        crop = crop.resize((pw, ph), Image.Resampling.NEAREST)
                        img.paste(crop, (px, py))
                else: img = Image.new("RGB", (w_can, h_can), (20,20,20))

            self.tk_image = ImageTk.PhotoImage(img)
            self.canvas.create_image(0, 0, image=self.tk_image, anchor="nw")
            
            if (r-l)/s.grid_w < 400: 
                sc, ec = int(l//s.grid_w), int(r//s.grid_w)+1
                sr, er = int(t//s.grid_h), int(b//s.grid_h)+1
                
                for slice_rects in s.selected_cells:
                    for (sx1, sy1, sx2, sy2) in slice_rects:
                        if sx2 >= l and sx1 <= r and sy2 >= t and sy1 <= b:
                            cx1 = (sx1 - l) * s.zoom_level
                            cy1 = (sy1 - t) * s.zoom_level
                            cx2 = (sx2 - l) * s.zoom_level
                            cy2 = (sy2 - t) * s.zoom_level
                            self._draw_selection_fill(cx1, cy1, cx2, cy2)

                # Draw external outlines per slice group
                for slice_rects in s.selected_cells:
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
                            self.canvas.create_line(ex1, ey1, ex1, ey2, fill="#00FFFF", width=3)
                        if (c + 1, ro) not in slice_cells:
                            self.canvas.create_line(ex2, ey1, ex2, ey2, fill="#00FFFF", width=3)
                        if (c, ro - 1) not in slice_cells:
                            self.canvas.create_line(ex1, ey1, ex2, ey1, fill="#00FFFF", width=3)
                        if (c, ro + 1) not in slice_cells:
                            self.canvas.create_line(ex1, ey2, ex2, ey2, fill="#00FFFF", width=3)
                
                cx = (sc * s.grid_w)
                if cx < l: cx += s.grid_w
                while cx < r:
                    sx = (cx - l) * s.zoom_level
                    self.canvas.create_line(sx, 0, sx, h_can, fill=s.grid_color, dash=(2, 4))
                    cx += s.grid_w
                cy = (sr * s.grid_h)
                if cy < t: cy += s.grid_h
                while cy < b:
                    sy = (cy - t) * s.zoom_level
                    self.canvas.create_line(0, sy, w_can, sy, fill=s.grid_color, dash=(2, 4))
                    cy += s.grid_h

        except Exception as e: pass

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

            self.redraw()
            self.trigger_modification()

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

    def choose_color(self):
        if self.current_session:
            c = colorchooser.askcolor()[1]
            if c: 
                self.current_session.grid_color = c
                self.redraw()
                self.trigger_modification()

    def clear_selection(self, e=None):
        if self.current_session:
            self.current_session.selected_cells.clear()
            self.redraw()
            self.trigger_modification()

    def save_selected_cells(self):
        s = self.current_session
        if not s or not s.selected_cells: 
            messagebox.showwarning("Warning", "No cells selected.")
            return
        
        n = len(s.selected_cells)
        msg = f"Save {n} slice(s) as {self.export_format.upper()[1:]}?"
        if not messagebox.askyesno("Confirm", msg): return
        
        out = filedialog.askdirectory(title="Select output folder")
        if out:
            count = self.export_service.save_selected_cells(s, out, self.export_format)
            messagebox.showinfo("Done", f"{count} slice(s) saved as {self.export_format.upper()[1:]}.")

    def slice_all(self):
        s = self.current_session
        if not s: 
            messagebox.showwarning("Warning", "No image loaded.")
            return
        
        cols = (s.real_width + s.grid_w - 1) // s.grid_w
        rows = (s.real_height + s.grid_h - 1) // s.grid_h
        total = cols * rows
        
        msg = f"Split entire image into {total} tiles ({cols} cols x {rows} rows)?\n\n"
        msg += f"Grid: {s.grid_w}x{s.grid_h}px\n"
        msg += f"Image: {s.real_width}x{s.real_height}px\n"
        msg += f"Format: {self.export_format.upper()[1:]}"
        
        if not messagebox.askyesno("Confirm Slice All", msg): 
            return
        
        out = filedialog.askdirectory(title="Select output folder")
        if not out:
            return
            
        count = self.export_service.slice_all(s, out, self.export_format)
        messagebox.showinfo("Done", f"{count} tiles saved to:\n{out}")
