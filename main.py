import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser, ttk
from PIL import Image, ImageTk, ImageDraw
import os
import json
import platform
import subprocess

Image.MAX_IMAGE_PIXELS = None 

def detect_dark_mode_mac():
    """Detects if macOS is in dark mode"""
    if platform.system() != "Darwin":
        return False
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True
        )
        return result.stdout.strip().lower() == "dark"
    except:
        return False 

# --- DATA MODEL (SESSION) ---
class ImageSession:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        
        self.original_image = Image.open(path)
        self.real_width, self.real_height = self.original_image.size
        
        self.preview_image = None
        self.preview_scale = 1.0
        self._generate_cache()
        
        self.zoom_level = 1.0
        self.camera_x = 0
        self.camera_y = 0
        
        self.grid_w = 1000
        self.grid_h = 1000
        self.grid_color = "#FFFF00"
        self.selected_cells = set()

    def _generate_cache(self):
        try:
            max_size = 2048
            if self.real_width > max_size or self.real_height > max_size:
                ratio = min(max_size / self.real_width, max_size / self.real_height)
                new_w = int(self.real_width * ratio)
                new_h = int(self.real_height * ratio)
                self.preview_image = self.original_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
                self.preview_scale = self.real_width / new_w
            else:
                self.preview_image = self.original_image.copy()
                self.preview_scale = 1.0
        except:
            self.preview_image = self.original_image.copy()
            self.preview_scale = 1.0

# --- MAIN APPLICATION ---
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
        self.export_format = ".png"  # Default export format
        
        self.tk_image = None
        self.last_mouse_x = 0
        self.last_mouse_y = 0

        self._setup_ui()

    def _setup_ttk_styles(self):
        """Configure ttk styles that work correctly on macOS"""
        style = ttk.Style()
        
        # Default button (gray)
        style.configure("Dark.TButton",
                        background="#444444",
                        foreground="#ffffff",
                        padding=(10, 5),
                        font=("Segoe UI", 10))
        style.map("Dark.TButton",
                  background=[("active", "#555555"), ("pressed", "#333333")],
                  foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])
        
        # Accent button (blue)
        style.configure("Accent.TButton",
                        background="#007acc",
                        foreground="#ffffff",
                        padding=(10, 5),
                        font=("Segoe UI", 9, "bold"))
        style.map("Accent.TButton",
                  background=[("active", "#005a9e"), ("pressed", "#004080")],
                  foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])
        
        # Green button
        style.configure("Green.TButton",
                        background="#27ae60",
                        foreground="#ffffff",
                        padding=(10, 5),
                        font=("Segoe UI", 10))
        style.map("Green.TButton",
                  background=[("active", "#2ecc71"), ("pressed", "#1e8449")],
                  foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])
        
        # Zoom button (smaller)
        style.configure("Zoom.TButton",
                        background="#444444",
                        foreground="#ffffff",
                        padding=(5, 2),
                        font=("Segoe UI", 12, "bold"))
        style.map("Zoom.TButton",
                  background=[("active", "#555555"), ("pressed", "#333333")],
                  foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])

    def _create_button(self, parent, text, command, style_type="default", width=None, side=tk.LEFT, padx=2, pady=8, fill=None):
        """Create a button that works correctly on both macOS and Windows"""
        if self.is_mac:
            # Use ttk.Button on macOS (works well)
            if style_type == "accent":
                style = "Accent.TButton"
            elif style_type == "green":
                style = "Green.TButton"
            elif style_type == "zoom":
                style = "Zoom.TButton"
            else:
                style = "Dark.TButton"
            
            btn = ttk.Button(parent, text=text, command=command, style=style)
            if width:
                btn.configure(width=width)
        else:
            # Use tk.Button on Windows (ttk has styling issues)
            if style_type == "accent":
                bg = "#007acc"
                active_bg = "#005a9e"
                font = ("Segoe UI", 9, "bold")
            elif style_type == "green":
                bg = "#27ae60"
                active_bg = "#2ecc71"
                font = ("Segoe UI", 10)
            elif style_type == "zoom":
                bg = "#444444"
                active_bg = "#555555"
                font = ("Segoe UI", 12, "bold")
            else:
                bg = "#444444"
                active_bg = "#555555"
                font = ("Segoe UI", 10)
            
            btn = tk.Button(parent, text=text, command=command,
                           bg=bg, fg="white",
                           activebackground=active_bg, activeforeground="white",
                           relief="flat", font=font,
                           padx=10, pady=5,
                           cursor="hand2")
            if width:
                btn.configure(width=width)
        
        if fill:
            btn.pack(side=side, padx=padx, pady=pady, fill=fill)
        else:
            btn.pack(side=side, padx=padx, pady=pady)
        return btn

    def _setup_ui(self):
        self.colors = {"bg": "#1e1e1e", "sidebar": "#252526", "toolbar": "#333333", "accent": "#007acc", "text": "#cccccc"}
        
        # Configure ttk styles for macOS
        self._setup_ttk_styles()
        
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
        
        self._create_button(self.sidebar, "+ Add Image", self.add_image_btn, style_type="accent", padx=10, pady=10, fill=tk.X)

        # Main Area
        content = tk.Frame(main, bg=self.colors["bg"])
        content.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.toolbar = tk.Frame(content, bg=self.colors["toolbar"], height=50)
        self.toolbar.pack(fill=tk.X)
        
        # Project Menu (dropdown)
        self._setup_project_menu()
        tk.Frame(self.toolbar, width=1, bg="#555").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        self._setup_grid_inputs()
        self._add_toolbar_btn("🎨", self.choose_color, tooltip="Grid Color")
        tk.Frame(self.toolbar, width=1, bg="#555").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Zoom Controls
        self._setup_zoom_controls()
        tk.Frame(self.toolbar, width=1, bg="#555").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Export Format Selector
        self._setup_format_selector()
        tk.Frame(self.toolbar, width=1, bg="#555").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Slice Buttons
        self._add_toolbar_btn("✂️ Slice", self.save_selected_cells, bg="#27ae60", tooltip="Slice Selected Cells")
        self._add_toolbar_btn("🔲 All", self.slice_all, bg="#27ae60", tooltip="Slice All Grid")
        
        # Status label on the right
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
        self._create_button(self.toolbar, text, command, style_type=style_type)

    def _setup_project_menu(self):
        """Create project dropdown menu"""
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
        """Create visual zoom controls: + / - buttons and percentage label"""
        f = tk.Frame(self.toolbar, bg=self.colors["toolbar"])
        f.pack(side=tk.LEFT, padx=3)
        
        self._create_button(f, "−", self.zoom_out_btn, style_type="zoom", width=2, pady=2)
        
        self.zoom_label = tk.Label(f, text="100%", bg=self.colors["toolbar"], fg="white", 
                                   font=("Segoe UI", 9), width=5)
        self.zoom_label.pack(side=tk.LEFT, padx=2)
        
        self._create_button(f, "+", self.zoom_in_btn, style_type="zoom", width=2, pady=2)
        
        self._create_button(f, "⟲", self.zoom_reset_btn, style_type="zoom", width=2, padx=(3,0), pady=2)

    def _setup_format_selector(self):
        """Create export format dropdown selector"""
        f = tk.Frame(self.toolbar, bg=self.colors["toolbar"])
        f.pack(side=tk.LEFT, padx=3)
        
        self.format_var = tk.StringVar(value="PNG")
        format_names = [fmt[0] for fmt in self.EXPORT_FORMATS]
        
        self.format_dropdown = ttk.Combobox(f, textvariable=self.format_var, values=format_names, 
                                            state="readonly", width=5, font=("Segoe UI", 9))
        self.format_dropdown.pack(side=tk.LEFT, padx=2)
        self.format_dropdown.bind("<<ComboboxSelected>>", self._on_format_change)

    def _on_format_change(self, event=None):
        """Handle format dropdown selection change"""
        selected = self.format_var.get()
        for name, ext in self.EXPORT_FORMATS:
            if name == selected:
                self.export_format = ext
                break

    def zoom_in_btn(self):
        """Zoom in via button"""
        if self.current_session:
            w_can = self.canvas.winfo_width()
            h_can = self.canvas.winfo_height()
            self.apply_zoom(1.25, w_can // 2, h_can // 2)

    def zoom_out_btn(self):
        """Zoom out via button"""
        if self.current_session:
            w_can = self.canvas.winfo_width()
            h_can = self.canvas.winfo_height()
            self.apply_zoom(0.8, w_can // 2, h_can // 2)

    def zoom_reset_btn(self):
        """Reset zoom to fit screen"""
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
        """Update zoom percentage label"""
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
        c.bind("<Shift-MouseWheel>", self.on_shift_scroll)
        
        # Zoom: Command on macOS, Control on Windows
        if self.is_mac:
            c.bind("<Command-MouseWheel>", self.on_zoom_scroll)
            c.bind("<Option-MouseWheel>", self.on_zoom_scroll)
        else:
            c.bind("<Control-MouseWheel>", self.on_zoom_scroll)
        
        c.bind("<Configure>", self.on_resize)
        self.root.bind("<c>", self.clear_selection)

    def _get_scroll_delta(self, event):
        """Normalize scroll speed between systems"""
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

        project_data = {
            "version": "2.2",
            "platform": platform.system(),
            "active_index": self.sessions.index(self.current_session) if self.current_session in self.sessions else 0,
            "export_format": self.export_format,
            "images": []
        }

        for session in self.sessions:
            session_data = {
                "path": session.path,
                "grid_w": session.grid_w,
                "grid_h": session.grid_h,
                "grid_color": session.grid_color,
                "zoom_level": session.zoom_level,
                "camera_x": session.camera_x,
                "camera_y": session.camera_y,
                "selection": list(session.selected_cells)
            }
            project_data["images"].append(session_data)

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(project_data, f, indent=4)

    def new_project(self):
        """Create a new empty project"""
        if self.sessions:
            if not messagebox.askyesno("New Project", "This will close the current project.\nUnsaved changes will be lost.\n\nContinue?"):
                return
        
        # Clear everything
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
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)

            self.sessions.clear()
            self.file_list.delete(0, tk.END)
            self.current_session = None
            self.canvas.delete("all")
            
            self.entry_w.delete(0, tk.END)
            self.entry_h.delete(0, tk.END)

            # Load export format
            saved_format = data.get("export_format", ".png")
            self.export_format = saved_format
            for name, ext in self.EXPORT_FORMATS:
                if ext == saved_format:
                    self.format_var.set(name)
                    break

            image_list = data.get("images", data.get("imagens", []))
            if isinstance(data, list): image_list = data

            for img_data in image_list:
                path = img_data.get("path", img_data.get("caminho"))
                
                if not os.path.exists(path):
                    filename = os.path.basename(path)
                    project_folder = os.path.dirname(f)
                    alternative = os.path.join(project_folder, filename)
                    if os.path.exists(alternative):
                        path = alternative
                
                if path and os.path.exists(path):
                    new_session = ImageSession(path)
                    
                    new_session.grid_w = img_data.get("grid_w", img_data.get("gw", 1000))
                    new_session.grid_h = img_data.get("grid_h", img_data.get("gh", 1000))
                    new_session.grid_color = img_data.get("grid_color", img_data.get("color", "#FFFF00"))
                    new_session.zoom_level = img_data.get("zoom_level", 1.0)
                    new_session.camera_x = img_data.get("camera_x", 0)
                    new_session.camera_y = img_data.get("camera_y", 0)
                    
                    sel_raw = img_data.get("selection", img_data.get("selecao", img_data.get("sel", [])))
                    new_session.selected_cells = set(tuple(x) for x in sel_raw)
                    
                    self.sessions.append(new_session)
                    self.file_list.insert(tk.END, f" {new_session.name}")

            active_idx = data.get("active_index", data.get("indice_ativo", 0))
            
            if not self.sessions:
                messagebox.showwarning("Warning", "Images not found. Place the images in the same folder as the .lab file.")
                return

            if active_idx >= len(self.sessions): active_idx = 0
                
            self.file_list.selection_clear(0, tk.END)
            self.file_list.selection_set(active_idx)
            self._activate_session(self.sessions[active_idx])
            
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

    def _draw_selection_overlay(self, x1, y1, x2, y2):
        """Draw a semi-transparent selection overlay that works on all platforms"""
        # Create multiple thin lines to simulate transparency effect
        # Cyan color with visual transparency simulation
        
        # Draw filled area with alternating lines pattern (simulates 50% transparency)
        line_spacing = 2
        
        # Horizontal lines
        y = y1
        while y < y2:
            self.canvas.create_line(x1, y, x2, y, fill="#00FFFF", width=1)
            y += line_spacing * 2
        
        # Vertical lines for crosshatch effect (more visible)
        x = x1
        while x < x2:
            self.canvas.create_line(x, y1, x, y2, fill="#00FFFF", width=1)
            x += line_spacing * 2
        
        # Strong border
        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#00FFFF", width=3)
        
        # Inner glow effect
        self.canvas.create_rectangle(x1+2, y1+2, x2-2, y2-2, outline="#FFFFFF", width=1)

    def redraw(self):
        s = self.current_session
        if not s: return

        try:
            s.grid_w = max(10, int(self.entry_w.get()))
            s.grid_h = max(10, int(self.entry_h.get()))
        except: pass

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
                
                for (c, ro) in s.selected_cells:
                    if sc <= c <= ec and sr <= ro <= er:
                        x1 = (c*s.grid_w - l)*s.zoom_level
                        y1 = (ro*s.grid_h - t)*s.zoom_level
                        x2 = x1 + (s.grid_w*s.zoom_level)
                        y2 = y1 + (s.grid_h*s.zoom_level)
                        
                        # Semi-transparent selection overlay (works on all platforms)
                        self._draw_selection_overlay(x1, y1, x2, y2)
                
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
            k = (col, row)
            if k in s.selected_cells: s.selected_cells.remove(k)
            else: s.selected_cells.add(k)
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
        if self.current_session: 
            delta = self._get_scroll_delta(e)
            self.current_session.camera_y -= delta / self.current_session.zoom_level
            self.redraw()
            
    def on_shift_scroll(self, e):
        if self.current_session: 
            delta = self._get_scroll_delta(e)
            self.current_session.camera_x -= delta / self.current_session.zoom_level
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

    def _get_export_filename(self, base_name, row, col):
        """Generate export filename with correct extension"""
        name_without_ext = os.path.splitext(base_name)[0]
        return f"{name_without_ext}_R{row:03d}_C{col:03d}{self.export_format}"

    def _save_image_tile(self, image, path):
        """Save image tile with format-specific options"""
        if self.export_format == ".jpg":
            # Convert to RGB for JPEG (no alpha channel)
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGB')
            image.save(path, quality=95)
        elif self.export_format == ".webp":
            image.save(path, quality=95)
        else:
            image.save(path)

    def save_selected_cells(self):
        s = self.current_session
        if not s or not s.selected_cells: 
            messagebox.showwarning("Warning", "No cells selected.")
            return
        
        msg = f"Save {len(s.selected_cells)} slices as {self.export_format.upper()[1:]}?"
        if not messagebox.askyesno("Confirm", msg): return
        
        out = filedialog.askdirectory(title="Select output folder")
        if out:
            count = 0
            for (c, r) in s.selected_cells:
                x1 = c * s.grid_w
                y1 = r * s.grid_h
                x2 = min(x1 + s.grid_w, s.real_width)
                y2 = min(y1 + s.grid_h, s.real_height)
                
                filename = self._get_export_filename(s.name, r, c)
                full_path = os.path.join(out, filename)
                
                tile = s.original_image.crop((x1, y1, x2, y2))
                self._save_image_tile(tile, full_path)
                count += 1
            messagebox.showinfo("Done", f"{count} slices saved as {self.export_format.upper()[1:]}.")

    def slice_all(self):
        """Slice the entire image into all grid tiles"""
        s = self.current_session
        if not s: 
            messagebox.showwarning("Warning", "No image loaded.")
            return
        
        # Calculate total tiles
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
            
        count = 0
        
        for row in range(rows):
            for col in range(cols):
                x1 = col * s.grid_w
                y1 = row * s.grid_h
                x2 = min(x1 + s.grid_w, s.real_width)
                y2 = min(y1 + s.grid_h, s.real_height)
                
                filename = self._get_export_filename(s.name, row, col)
                full_path = os.path.join(out, filename)
                
                tile = s.original_image.crop((x1, y1, x2, y2))
                self._save_image_tile(tile, full_path)
                count += 1
        
        messagebox.showinfo("Done", f"{count} tiles saved to:\n{out}")

if __name__ == "__main__":
    root = tk.Tk()
    app = SlicerLabApp(root)
    root.mainloop()