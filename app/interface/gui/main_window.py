import sys
import platform
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QToolBar, QDockWidget, QListWidget, QPushButton, 
                             QLabel, QFrame, QScrollArea, QSplitter, QStackedWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QAction, QActionGroup

from app.domain.history import UndoManager
from app.application.project_service import ProjectService
from app.application.export_service import ExportService
from app.application.import_service import TileImportService
from app.application.interactive_segmentation_service import InteractiveSegmentationService
from app.infrastructure.ml_models.nuclick_adapter import NuClickAdapter
from PyQt6.QtWidgets import QComboBox, QCheckBox

# Import the new PyQt Components (to be rewritten in subsequent steps)
from .components import (
    CanvasRenderer,
    TileRenderer,
    ProjectManager,
    SlicePreviews,
    ExportHandler
)

class SlicerLabApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.is_mac = platform.system() == "Darwin"
        
        self.setWindowTitle(f"Tiles Grid Analyzer - {'macOS' if self.is_mac else 'Windows'}")
        self.resize(1400, 900)
        self.setStyleSheet("QMainWindow { background-color: #1e1e1e; color: #cccccc; }")

        self.sessions = []
        self.current_session = None
        self.current_project_path = None
        
        # Tool mode: "grid" (default) or "brush"
        self.active_tool = "grid"
        
        self.project_service = ProjectService()
        self.export_service = ExportService()
        self.tile_import_service = TileImportService()

        # ── Composition Root: wire infrastructure adapters into services ──
        ml_models = []
        try:
            nuclick_adapter = NuClickAdapter(
                model_path="app/infrastructure/ml_models/nuclick_torch/weights/nuclick.pth"
            )
            ml_models.append(nuclick_adapter)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Failed to load NuClick adapter: %s", e)

        self.segmentation_service = InteractiveSegmentationService(
            models=ml_models
        )
        self.undo_manager = UndoManager()

        self._setup_ui()

    def _setup_ui(self):
        # 1. Central Widget — QStackedWidget hosts two independent environments
        self._central_stack = QStackedWidget()
        self.canvas_renderer = CanvasRenderer(self)     # Index 0 — Macro (full image)
        self.tile_renderer   = TileRenderer(self)       # Index 1 — Micro (isolated tile)
        self._central_stack.addWidget(self.canvas_renderer)
        self._central_stack.addWidget(self.tile_renderer)
        self._central_stack.setCurrentIndex(0)
        self.setCentralWidget(self._central_stack)

        # 2. Top Toolbar
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setStyleSheet("QToolBar { background-color: #333333; spacing: 10px; padding: 5px; }")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        # Initialize sub-modules
        self.project_manager = ProjectManager(self)
        self.export_handler = ExportHandler(self)
        
        # Setup Toolbar Actions
        self.project_manager.setup_toolbar(self.toolbar)
        self.toolbar.addSeparator()

        # Tool selection mode (Exclusive Group)
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)

        self.action_grid = QAction("🟥 Grid Tool", self)
        self.action_grid.setCheckable(True)
        self.action_grid.setChecked(True)
        self.action_grid.triggered.connect(lambda: self._activate_tool("grid"))
        self.tool_group.addAction(self.action_grid)
        self.toolbar.addAction(self.action_grid)

        self.action_brush = QAction("🖌️ Brush Tool", self)
        self.action_brush.setCheckable(True)
        self.action_brush.triggered.connect(lambda: self._activate_tool("brush"))
        self.tool_group.addAction(self.action_brush)
        self.toolbar.addAction(self.action_brush)

        self.toolbar.addSeparator()

        # Tools exclusively for Tile/Slice Isolation mode
        self.action_segment = QAction("🧠 Segment Nucleus", self)
        self.action_segment.setCheckable(True)
        self.action_segment.triggered.connect(lambda: self._activate_tool("segment"))
        self.tool_group.addAction(self.action_segment)
        self.toolbar.addAction(self.action_segment)

        self.action_erase = QAction("🧽 Erase Pixels", self)
        self.action_erase.setCheckable(True)
        self.action_erase.triggered.connect(lambda: self._activate_tool("erase"))
        self.tool_group.addAction(self.action_erase)
        self.toolbar.addAction(self.action_erase)

        self.toolbar.addSeparator()

        # Model Selector Combobox in Toolbar
        self.combo_model = QComboBox()
        self.combo_model.addItems(self.segmentation_service.get_available_models())
        self.combo_model.setStyleSheet("QComboBox { background-color: #444; color: #ccc; border: 1px solid #555; padding: 2px 6px; }")
        self.toolbar.addWidget(self.combo_model)
        
        # Checkbox for Segmentation Membrane Overlay
        self.chk_show_membrane = QCheckBox("Show Membrane")
        self.chk_show_membrane.setChecked(True)
        self.chk_show_membrane.setStyleSheet("QCheckBox { color: #ccc; margin-left: 10px; }")
        self.chk_show_membrane.stateChanged.connect(lambda: self.canvas_renderer.viewport().update() if self.canvas_renderer else None)
        self.toolbar.addWidget(self.chk_show_membrane)

        self.toolbar.addSeparator()
        
        # Grid Size Inputs (Moved to ProjectManager or Toolbar)
        self.project_manager.setup_grid_inputs(self.toolbar)
        
        # Push the Export controls to the far right edge of the screen
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().Policy.Expanding, spacer.sizePolicy().Policy.Preferred)
        self.toolbar.addWidget(spacer)
        
        self.export_handler.setup_toolbar(self.toolbar)

        # 3. Left Dock (Sidebar)
        self.sidebar_dock = QDockWidget("Project Workspace", self)
        self.sidebar_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.sidebar_dock.setStyleSheet("QDockWidget { background-color: #252526; color: #ccc; }")
        
        # We use a Splitter here instead of a fixed layout so the two lists expand dynamically without gaps
        self.sidebar_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # --- Top Half: Project Files ---
        project_widget = QWidget()
        project_layout = QVBoxLayout(project_widget)
        project_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_proj = QLabel("PROJECT IMAGES")
        lbl_proj.setStyleSheet("color: #aaaaaa; font-size: 11px; font-weight: bold; margin-bottom: 5px;")
        
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget { background-color: #2a2a2a; border: none; outline: none; }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #333333; }
            QListWidget::item:hover { background-color: #3e3e42; cursor: pointer; }
            QListWidget::item:selected { background-color: #37373d; }
        """)
        self.file_list.itemClicked.connect(self.project_manager.switch_image_tab)
        
        add_btn = QPushButton("＋ Add Image")
        add_btn.setStyleSheet("background-color: #007acc; color: white; padding: 6px; font-weight: bold; border-radius: 3px;")
        add_btn.clicked.connect(self.project_manager.add_image)

        project_layout.addWidget(lbl_proj)
        project_layout.addWidget(self.file_list)
        project_layout.addWidget(add_btn)

        # --- Bottom Half: Slice Previews ---
        self.slice_previews = SlicePreviews(self)

        # "Add Tile" button sits inside the SlicePreviews widget layout
        # so it's always visible regardless of splitter sizing
        add_tile_btn = QPushButton("＋ Add Tile")
        add_tile_btn.setToolTip("Import a saved tile XML descriptor into the current session")
        add_tile_btn.setStyleSheet(
            "background-color: #2d6a4f; color: white; padding: 6px; "
            "font-weight: bold; border-radius: 3px; margin-top: 4px;"
        )
        add_tile_btn.clicked.connect(self._add_tile)
        self.slice_previews.layout.addWidget(add_tile_btn)

        self.sidebar_splitter.addWidget(project_widget)
        self.sidebar_splitter.addWidget(self.slice_previews)

        # Set default proportions (2 widgets)
        self.sidebar_splitter.setSizes([200, 500])

        self.sidebar_dock.setWidget(self.sidebar_splitter)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.sidebar_dock)
        
        # 4. Status Bar
        self.statusBar().showMessage("Ready. Add an image to start.")
        self.statusBar().setStyleSheet("background-color: #007acc; color: white;")

    def _activate_tool(self, tool_name):
        self.active_tool = tool_name
        self.statusBar().showMessage(f"Tool selected: {tool_name}")
        self.canvas_renderer.set_tool(tool_name)

    def update_tool_context(self, is_isolated: bool):
        """Enable/Disable tools based on whether the user is in global view or inside an isolated tile."""
        self.action_grid.setEnabled(not is_isolated)
        self.action_brush.setEnabled(not is_isolated)
        self.action_segment.setEnabled(is_isolated)
        self.action_erase.setEnabled(is_isolated)
        self.combo_model.setEnabled(is_isolated)

        # Auto-switch to an available tool safely to avoid undefined states
        if is_isolated and self.active_tool in ("grid", "brush"):
            self.action_segment.setChecked(True)
            self._activate_tool("segment")
        elif not is_isolated and self.active_tool in ("segment", "erase"):
            self.action_grid.setChecked(True)
            self._activate_tool("grid")

    def _add_tile(self):
        """Slot for the 'Add Tile' button — delegates to project_manager."""
        self.project_manager.add_tile()

    # ── Environment Switching (Bounded Context Transitions) ─────────────────

    def switch_to_tile(self, idx: int) -> None:
        """Transition from Macro (full image) to Micro (isolated tile editing)."""
        s = self.current_session
        if not s or idx >= len(s.tiles):
            return
        self.tile_renderer.load_tile(s, idx)
        self._central_stack.setCurrentIndex(1)
        self.update_tool_context(True)

    def switch_to_canvas(self) -> None:
        """Transition from Micro (isolated tile) back to Macro (full image)."""
        self.tile_renderer.unload()
        self._central_stack.setCurrentIndex(0)
        self.update_tool_context(False)
        self.canvas_renderer.redraw()
