import tkinter as tk
from tkinter import ttk
import platform
from app.domain.history import UndoManager
from app.interface.gui.utils import detect_dark_mode_mac
from app.interface.gui.components import (
    UIComponents, setup_ttk_styles,
    CanvasRendererMixin,
    ZoomPanMixin,
    SelectionToolsMixin,
    SliceInspectorMixin,
    SlicePreviewsMixin,
    ProjectManagerMixin,
    ExportHandlerMixin,
)
from app.application.services import ProjectService, ExportService


class SlicerLabApp(
    CanvasRendererMixin,
    ZoomPanMixin,
    SelectionToolsMixin,
    SliceInspectorMixin,
    SlicePreviewsMixin,
    ProjectManagerMixin,
    ExportHandlerMixin,
):
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

        # Tool mode: "grid" (default) or "brush"
        self.active_tool = "grid"
        self._brush_points = []   # list of (img_x, img_y) while drawing
        self._brush_btn = None    # reference to toolbar brush button
        
        # Services & Components
        self.ui = UIComponents()
        self.project_service = ProjectService()
        self.export_service = ExportService()
        self.undo_manager = UndoManager()

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
        self.slice_header = tk.Label(self.sidebar, text="TILES (0)", bg=self.colors["sidebar"], fg="#888", font=("Segoe UI", 8, "bold"), anchor="w")
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

        # Brush tool toggle button
        self._brush_btn = tk.Button(
            self.toolbar, text="🖌️ Brush",
            command=lambda: self._activate_tool("brush" if self.active_tool == "grid" else "grid"),
            bg="#444", fg="white", relief="flat",
            font=("Segoe UI", 10), padx=8, pady=4,
            activebackground="#555", activeforeground="white",
            cursor="hand2"
        )
        self._brush_btn.pack(side=tk.LEFT, padx=2, pady=4)

        tk.Frame(self.toolbar, width=1, bg="#555").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Zoom Controls
        self._setup_zoom_controls()
        tk.Frame(self.toolbar, width=1, bg="#555").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Export Format
        self._setup_format_selector()
        tk.Frame(self.toolbar, width=1, bg="#555").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Tile Buttons
        self._add_toolbar_btn("✂️ Tile", self.save_selected_cells, bg="#27ae60", tooltip="Export Selected Tiles")
        self._add_toolbar_btn("🔲 All", self.slice_all, bg="#27ae60", tooltip="Export All Grid Tiles")
        
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
        """Show a full-window welcome overlay that blocks all interaction."""
        self.welcome_frame = tk.Frame(self.root, bg="#1a1a2e")
        self.welcome_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Center container
        center = tk.Frame(self.welcome_frame, bg="#1a1a2e")
        center.place(relx=0.5, rely=0.45, anchor="center")

        # App icon/logo area
        tk.Label(center, text="✂️", font=("Segoe UI", 48), bg="#1a1a2e", fg="white").pack(pady=(0, 5))

        # Title
        tk.Label(center, text="Tiles Grid Analyzer", font=("Segoe UI", 28, "bold"),
                 bg="#1a1a2e", fg="#e0e0e0").pack(pady=(0, 5))

        # Subtitle
        tk.Label(center, text="Grid-based image tiling tool",
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

    def _setup_binds(self):
        c = self.canvas
        c.bind("<MouseWheel>", self.on_scroll)
        if not self.is_mac:
            c.bind("<Control-MouseWheel>", self.on_zoom_scroll)
        c.bind("<Configure>", self.on_resize)
        # Keyboard shortcuts
        self.root.bind("<Control-z>", lambda e: self._undo())
        self.root.bind("<Control-y>", lambda e: self._redo())
        self.root.bind("<Control-s>", lambda e: self._save_shortcut())
        self.root.bind("<Control-o>", lambda e: self.open_project())
        self.root.bind("<Control-n>", lambda e: self.new_project())
        self.root.bind("<Delete>", lambda e: self._delete_current_tile())
        self._rebind_canvas()
