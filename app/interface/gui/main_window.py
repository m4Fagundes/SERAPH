import sys
import platform
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QToolBar, QDockWidget, QListWidget, QPushButton, 
                             QLabel, QFrame, QScrollArea, QSplitter)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QAction, QActionGroup

from app.domain.history import UndoManager
from app.application.services import ProjectService, ExportService

# Import the new PyQt Components (to be rewritten in subsequent steps)
from .components import (
    CanvasRenderer,
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
        self.undo_manager = UndoManager()

        self._setup_ui()

    def _setup_ui(self):
        # 1. Central Widget (Canvas)
        self.canvas_renderer = CanvasRenderer(self)
        self.setCentralWidget(self.canvas_renderer)

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

        self.sidebar_splitter.addWidget(project_widget)
        self.sidebar_splitter.addWidget(self.slice_previews)
        
        # Set default proportions
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
