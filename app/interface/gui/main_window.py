import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser, ttk
from PIL import Image, ImageTk
import os
import platform
import threading
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
        
        self.root.title(f"Tiles Grid Analyzer - {'macOS' if self.is_mac else 'Windows'}")
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

        # Slice preview state
        self._slice_thumbs = []  # keep refs to prevent GC
        self._collapsed_sessions = set()  # session names that are collapsed

        self._setup_ui()

    def _setup_ui(self):
        self.colors = {"bg": "#1e1e1e", "sidebar": "#252526", "toolbar": "#333333", "accent": "#007acc", "text": "#cccccc"}
        
        setup_ttk_styles()
        
        main = tk.Frame(self.root, bg=self.colors["bg"])
        main.pack(fill=tk.BOTH, expand=True)

        # Sidebar
        self.sidebar = tk.Frame(main, width=260, bg=self.colors["sidebar"])
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        
        # --- Top section: project images ---
        top_section = tk.Frame(self.sidebar, bg=self.colors["sidebar"])
        top_section.pack(fill=tk.X)

        tk.Label(top_section, text="PROJECT / IMAGES", bg=self.colors["sidebar"], fg="#888", font=("Segoe UI", 8, "bold"), anchor="w").pack(fill=tk.X, padx=12, pady=(10,4))
        self.file_list = tk.Listbox(top_section, bg="#2a2a2a", fg=self.colors["text"], selectbackground="#37373d", selectforeground="white", bd=0, highlightthickness=0, font=("Segoe UI", 10), activestyle="none", height=4, relief="flat")
        self.file_list.pack(fill=tk.X, padx=8, pady=(0,6))
        self.file_list.bind("<<ListboxSelect>>", self.switch_image_tab)
        
        self.ui.create_button(top_section, "＋ Add Image", self.add_image_btn, style_type="accent", padx=8, pady=(0,8), fill=tk.X)

        # --- Separator ---
        tk.Frame(self.sidebar, height=1, bg="#3a3a3a").pack(fill=tk.X, padx=8)

        # --- Bottom section: slice previews ---
        self.slice_header = tk.Label(self.sidebar, text="SLICES (0)", bg=self.colors["sidebar"], fg="#888", font=("Segoe UI", 8, "bold"), anchor="w")
        self.slice_header.pack(fill=tk.X, padx=12, pady=(8,4))

        # Scrollable container for slices
        slice_container = tk.Frame(self.sidebar, bg=self.colors["sidebar"])
        slice_container.pack(fill=tk.BOTH, expand=True)

        self._slice_canvas = tk.Canvas(slice_container, bg=self.colors["sidebar"], highlightthickness=0, bd=0)
        self._slice_scrollbar = tk.Scrollbar(slice_container, orient="vertical", command=self._slice_canvas.yview)
        self._slice_inner = tk.Frame(self._slice_canvas, bg=self.colors["sidebar"])

        self._slice_canvas_window = self._slice_canvas.create_window((0, 0), window=self._slice_inner, anchor="nw")
        self._slice_canvas.configure(yscrollcommand=self._slice_scrollbar.set)

        # Resize inner frame width to match canvas
        def _on_slice_canvas_configure(e):
            self._slice_canvas.itemconfig(self._slice_canvas_window, width=e.width)
        self._slice_canvas.bind("<Configure>", _on_slice_canvas_configure)
        self._slice_inner.bind("<Configure>", lambda e: self._slice_canvas.configure(scrollregion=self._slice_canvas.bbox("all")))

        self._slice_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._slice_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Mouse wheel scrolling
        def _on_slice_mousewheel(e):
            self._slice_canvas.yview_scroll(-1 * (e.delta // 120), "units")
        self._slice_canvas.bind("<MouseWheel>", _on_slice_mousewheel)
        self._slice_inner.bind("<MouseWheel>", _on_slice_mousewheel)

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
        self._show_welcome_screen()

    def _show_welcome_screen(self):
        """Show a welcome overlay on the canvas area."""
        self.welcome_frame = tk.Frame(self.canvas_area, bg="#1a1a2e")
        self.welcome_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Center container
        center = tk.Frame(self.welcome_frame, bg="#1a1a2e")
        center.place(relx=0.5, rely=0.45, anchor="center")

        # App icon/logo area
        tk.Label(center, text="✂️", font=("Segoe UI", 48), bg="#1a1a2e", fg="white").pack(pady=(0, 5))

        # Title
        tk.Label(center, text="Slicer Lab Pro", font=("Segoe UI", 28, "bold"),
                 bg="#1a1a2e", fg="#e0e0e0").pack(pady=(0, 5))

        # Subtitle
        tk.Label(center, text="Grid-based image slicing tool",
                 font=("Segoe UI", 11), bg="#1a1a2e", fg="#888").pack(pady=(0, 30))

        # Buttons container
        btn_frame = tk.Frame(center, bg="#1a1a2e")
        btn_frame.pack()

        # New Project button
        new_btn = tk.Button(btn_frame, text="📄  New Project",
                           command=self.new_project,
                           bg="#007acc", fg="white",
                           activebackground="#005a9e", activeforeground="white",
                           relief="flat", font=("Segoe UI", 13, "bold"),
                           padx=30, pady=12, cursor="hand2", width=20)
        new_btn.pack(pady=5)

        # Open Project button
        open_btn = tk.Button(btn_frame, text="📂  Open Project",
                            command=self.open_project,
                            bg="#333", fg="white",
                            activebackground="#444", activeforeground="white",
                            relief="flat", font=("Segoe UI", 13),
                            padx=30, pady=12, cursor="hand2", width=20)
        open_btn.pack(pady=5)

        # Version / footer
        tk.Label(self.welcome_frame, text="v1.0",
                 font=("Segoe UI", 8), bg="#1a1a2e", fg="#555").place(relx=0.5, rely=0.95, anchor="center")

    def _dismiss_welcome(self):
        """Remove the welcome screen overlay."""
        if hasattr(self, 'welcome_frame') and self.welcome_frame:
            self.welcome_frame.destroy()
            self.welcome_frame = None

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
        
        self._dismiss_welcome()
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
        self._update_slice_previews()

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

            self._dismiss_welcome()
            self.file_list.delete(0, tk.END)
            self.current_session = None
            self.canvas.delete("all")
            
            for s in self.sessions:
                self.file_list.insert(tk.END, f" {s.name}")

            # All sessions are immediately ready (on-demand)
            if self.sessions:
                self._activate_session(self.sessions[0])
            
            self.current_project_path = f
            self.root.title(f"Slicer Lab Pro - {os.path.basename(f)}")
            self.save_status_label.config(text="Project Loaded")
            self._update_slice_previews()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error opening project: {e}")
            print(e)

    def add_image_btn(self):
        path = filedialog.askopenfilename(filetypes=[("All Supported", "*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.bmp;*.webp;*.ndpi;*.svs;*.mrxs;*.scn;*.vms;*.vmu;*.bif"), ("Images", "*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.bmp;*.webp"), ("Whole-Slide Images", "*.ndpi;*.svs;*.mrxs;*.scn;*.vms;*.vmu;*.bif")])
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
            self.status_bar.config(text=f"Loaded: {new_session.name} | {new_session.real_width:,}×{new_session.real_height:,} px")
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

        except Exception as e:
            print(f"Redraw error: {e}")
            import traceback; traceback.print_exc()

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

            s.sync_metadata()
            self.redraw()
            self._update_slice_previews()
            self.trigger_modification()
            self._auto_reexport(s)

    def _toggle_session_collapse(self, session_name):
        """Toggle collapsed state of a session group in slice previews."""
        if session_name in self._collapsed_sessions:
            self._collapsed_sessions.discard(session_name)
        else:
            self._collapsed_sessions.add(session_name)
        self._update_slice_previews()

    def _update_slice_previews(self):
        """Rebuild the slice preview panel with full-width vertical thumbnail cards."""
        # Clear existing
        for w in self._slice_inner.winfo_children():
            w.destroy()
        self._slice_thumbs.clear()

        total_slices = sum(len(s.selected_cells) for s in self.sessions)
        self.slice_header.config(text=f"SLICES ({total_slices})")

        if total_slices == 0:
            empty = tk.Label(self._slice_inner, text="Right-click cells to\ncreate slices",
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
            lbl.pack(fill=tk.X, padx=6, pady=4)
            name = session.name
            for widget in (lbl, header):
                widget.bind("<Button-1>", lambda e, n=name: self._toggle_session_collapse(n))
                widget.bind("<MouseWheel>", lambda e: self._slice_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

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

                    tk_thumb = ImageTk.PhotoImage(crop)
                    self._slice_thumbs.append(tk_thumb)

                    # Card frame
                    card = tk.Frame(self._slice_inner, bg="#2a2a2a", padx=0, pady=0)
                    card.pack(fill=tk.X, padx=8, pady=3)

                    # Image
                    img_lbl = tk.Label(card, image=tk_thumb, bg="#222", anchor="center")
                    img_lbl.pack(fill=tk.X, padx=4, pady=(4, 0))

                    # Info row
                    info = tk.Label(card, text=f"  Slice {idx+1}   •   {orig_w}×{orig_h}px",
                                   bg="#2a2a2a", fg="#999", anchor="w",
                                   font=("Segoe UI", 8))
                    info.pack(fill=tk.X, padx=4, pady=(2, 4))

                    # Propagate mousewheel from all card children
                    for w in (card, img_lbl, info):
                        w.bind("<MouseWheel>", lambda e: self._slice_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

                    # Click to open inspector
                    sess_ref = session
                    slice_idx = idx
                    for w in (card, img_lbl, info):
                        w.configure(cursor="hand2")
                        w.bind("<Button-1>", lambda e, sr=sess_ref, si=slice_idx: self._open_slice_inspector(sr, si))

                except Exception as ex:
                    print(f"Slice preview error: {ex}")

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

        tk.Label(header, text=f"Slice {slice_idx+1}  \u2014  {session.name}",
                 bg="#2d2d2d", fg="#ccc", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT, padx=8, pady=6)

        self._insp_zoom_label = tk.Label(header, text="100%", bg="#2d2d2d", fg="#888",
                                          font=("Segoe UI", 9))
        self._insp_zoom_label.pack(side=tk.RIGHT, padx=10, pady=6)

        tk.Label(header, text=f"{orig_w}\u00d7{orig_h} px", bg="#2d2d2d", fg="#888",
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT, padx=5, pady=6)

        # --- Content: Canvas (left) + Properties (right) ---
        content = tk.Frame(self._inspector_frame, bg="#1e1e1e")
        content.pack(fill=tk.BOTH, expand=True)

        # Full-res navigable canvas
        self._insp_canvas = tk.Canvas(content, bg="#111", highlightthickness=0)
        self._insp_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Binds for pan + zoom on inspector canvas
        self._insp_canvas.bind("<ButtonPress-1>", self._insp_pan_start)
        self._insp_canvas.bind("<B1-Motion>", self._insp_pan_move)
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

        self._insp_tk_img = ImageTk.PhotoImage(img)
        c.create_image(0, 0, anchor="nw", image=self._insp_tk_img)

        # Draw tile boundary border (shows where the tile ends)
        tile_left   = (0    - cx) * z
        tile_top    = (0    - cy) * z
        tile_right  = (self._insp_slice_w - cx) * z
        tile_bottom = (self._insp_slice_h - cy) * z
        c.create_rectangle(tile_left, tile_top, tile_right, tile_bottom,
                           outline="#00AAFF", width=2, dash=(6, 4))

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

    def _save_inspector_metadata(self):
        """Save current inspector field values to metadata."""
        if hasattr(self, '_insp_session') and self._insp_session:
            session = self._insp_session
            idx = self._insp_slice_idx
            session.sync_metadata()
            if idx < len(session.slice_metadata):
                try:
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
            # Track export path for auto-reexport
            s.export_dir = out
            s.export_format = self.export_format
            self.trigger_modification()
            messagebox.showinfo("Done", f"{count} slice(s) saved as {self.export_format.upper()[1:]}.")

    def _auto_reexport(self, session):
        """Re-export slices if session was previously exported."""
        if session.export_dir and session.export_format and session.selected_cells:
            try:
                if os.path.isdir(session.export_dir):
                    self.export_service.save_selected_cells(
                        session, session.export_dir, session.export_format)
                    self.status_bar.config(text=f"Auto-exported {len(session.selected_cells)} slice(s)")
            except Exception as e:
                print(f"Auto-reexport error: {e}")

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
