import sys
import platform
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QToolBar, QDockWidget, QListWidget, QPushButton, 
                             QLabel, QFrame, QScrollArea, QSplitter, QStackedWidget,
                             QDoubleSpinBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QAction, QActionGroup

from app.domain.history import UndoManager
from app.application.project_service import ProjectService
from app.application.export_service import ExportService
from app.application.import_service import TileImportService
from app.application.interactive_segmentation_service import InteractiveSegmentationService
from app.application.batch_segmentation_service import BatchSegmentationService
from app.application.manual_adjustment_service import ManualAdjustmentService
from app.infrastructure.ml_models.nuclick_adapter import NuClickAdapter
from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
from PyQt6.QtWidgets import QComboBox, QCheckBox

# Import the new PyQt Components (to be rewritten in subsequent steps)
from .components import (
    CanvasRenderer,
    TileRenderer,
    ProjectManager,
    SlicePreviews,
    ExportHandler,
    PropertiesPanel
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
        import logging as _logging
        _cr_logger = _logging.getLogger(__name__)

        # Interactive models (click-based)
        from pathlib import Path
        _project_root = Path(__file__).resolve().parents[3]  # main_window.py → gui → interface → app → project root

        ml_models = []
        try:
            nuclick_adapter = NuClickAdapter(
                model_path=str(_project_root / "app" / "infrastructure" / "ml_models" / "nuclick_torch" / "weights" / "nuclick.pth")
            )
            ml_models.append(nuclick_adapter)
        except Exception as e:
            _cr_logger.error("Failed to load NuClick adapter: %s", e)

        self.segmentation_service = InteractiveSegmentationService(
            models=ml_models
        )

        # Batch models (segment entire tile)
        batch_models = []
        try:
            cellpose_adapter = CellposeAdapter(model_type="nuclei", gpu=True)
            batch_models.append(cellpose_adapter)
        except Exception as e:
            _cr_logger.error("Failed to load Cellpose adapter: %s", e)

        self.batch_segmentation_service = BatchSegmentationService(
            models=batch_models
        )
        self.manual_adjustment_service = ManualAdjustmentService()
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
        self.toolbar.setStyleSheet("""
            QToolBar {
                background-color: #252526;
                border-bottom: 1px solid #333333;
                spacing: 8px;
                padding: 6px;
            }
            QToolButton {
                background-color: transparent;
                color: #cccccc;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 6px 10px;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                font-size: 8pt;
                font-weight: 500;
            }
            QToolButton:hover {
                background-color: #3e3e42;
                border: 1px solid #454545;
                color: #ffffff;
            }
            QToolButton:checked {
                background-color: #0e639c;
                color: #ffffff;
                border: 1px solid #1177bb;
            }
            QToolButton:pressed {
                background-color: #094771;
            }
        """)
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


        self.toolbar.addSeparator()

        # Model Selector Combobox in Toolbar
        # Combines both interactive (click) and batch (whole-tile) models
        self.combo_model = QComboBox()
        all_model_names = (
            self.segmentation_service.get_available_models()
            + self.batch_segmentation_service.get_available_models()
        )
        # Add Manual Fine Tune option
        all_model_names = list(all_model_names) + ["🖌️ Manual Fine Tune"]
        self.combo_model.addItems(all_model_names)
        self.combo_model.setStyleSheet("""
            QComboBox { 
                background-color: #3c3c3c; 
                color: #ffffff; 
                border: 1px solid #555555; 
                border-radius: 4px; 
                padding: 4px 8px; 
                font-family: 'Segoe UI', Tahoma, sans-serif;
            }
            QComboBox:focus { border: 1px solid #007acc; background-color: #444444; }
            QComboBox::drop-down { border: none; }
        """)
        self.combo_model.currentTextChanged.connect(self._on_model_changed)
        self.toolbar.addWidget(self.combo_model)

        # "Segment All" button — visible only for batch models
        self.btn_segment_all = QPushButton("🔬 Segment All")
        self.btn_segment_all.setToolTip(
            "Run batch segmentation on the entire tile (Cellpose)"
        )
        self.btn_segment_all.setStyleSheet(
            "QPushButton { background-color: #2d6a4f; color: white; padding: 6px 12px; "
            "font-weight: bold; border-radius: 4px; border: none; "
            "font-family: 'Segoe UI', Tahoma, sans-serif; } "
            "QPushButton:hover { background-color: #40916c; } "
            "QPushButton:pressed { background-color: #1b4332; }"
        )
        self.btn_segment_all.clicked.connect(self._run_batch_segmentation)
        self.btn_segment_all.setVisible(False)  # hidden until a batch model is selected
        self.toolbar.addWidget(self.btn_segment_all)

        # ── Cellpose parameter controls (visible only for batch models) ────
        _param_style = (
            "QDoubleSpinBox { background-color: #3c3c3c; color: #ffffff; "
            "border: 1px solid #555; border-radius: 3px; padding: 2px 4px; "
            "font-family: 'Segoe UI', Tahoma, sans-serif; } "
            "QDoubleSpinBox:focus { border: 1px solid #007acc; }"
        )
        _lbl_style = (
            "QLabel { color: #aaaaaa; font-size: 7pt; font-family: 'Segoe UI', "
            "Tahoma, sans-serif; margin-left: 6px; }"
        )

        self.lbl_diameter = QLabel("⌀ Diameter")
        self.lbl_diameter.setStyleSheet(_lbl_style)
        self.lbl_diameter.setToolTip(
            "Expected nucleus diameter in pixels. 0 = auto-detect."
        )
        self.spin_diameter = QDoubleSpinBox()
        self.spin_diameter.setRange(0.0, 500.0)
        self.spin_diameter.setValue(30.0)   # ~30px for 40x H&E, 0 = auto
        self.spin_diameter.setSingleStep(5.0)
        self.spin_diameter.setDecimals(1)
        self.spin_diameter.setSpecialValueText("Auto")
        self.spin_diameter.setToolTip("0 = Cellpose auto-estimates the diameter")
        self.spin_diameter.setStyleSheet(_param_style)
        self.spin_diameter.setFixedWidth(70)

        self.lbl_flow = QLabel("Flow")
        self.lbl_flow.setStyleSheet(_lbl_style)
        self.lbl_flow.setToolTip(
            "Flow threshold: lower = stricter mask quality (0.0–1.0)"
        )
        self.spin_flow = QDoubleSpinBox()
        self.spin_flow.setRange(0.0, 1.0)
        self.spin_flow.setValue(0.4)
        self.spin_flow.setSingleStep(0.05)
        self.spin_flow.setDecimals(2)
        self.spin_flow.setToolTip("Flow error threshold (default 0.4)")
        self.spin_flow.setStyleSheet(_param_style)
        self.spin_flow.setFixedWidth(60)

        self.lbl_cellprob = QLabel("CellProb")
        self.lbl_cellprob.setStyleSheet(_lbl_style)
        self.lbl_cellprob.setToolTip(
            "Cell probability threshold: lower = more detections (−6 to +6)"
        )
        self.spin_cellprob = QDoubleSpinBox()
        self.spin_cellprob.setRange(-6.0, 6.0)
        self.spin_cellprob.setValue(0.0)
        self.spin_cellprob.setSingleStep(0.5)
        self.spin_cellprob.setDecimals(1)
        self.spin_cellprob.setToolTip("Cell probability threshold (default 0.0)")
        self.spin_cellprob.setStyleSheet(_param_style)
        self.spin_cellprob.setFixedWidth(60)

        # Group all batch param widgets for show/hide
        self._batch_param_widgets = [
            self.lbl_diameter, self.spin_diameter,
            self.lbl_flow, self.spin_flow,
            self.lbl_cellprob, self.spin_cellprob,
        ]
        for w in self._batch_param_widgets:
            w.setVisible(False)
            self.toolbar.addWidget(w)
        
        # Checkbox for Segmentation Membrane Overlay
        self.chk_show_membrane = QCheckBox("Show Membrane")
        self.chk_show_membrane.setChecked(True)
        self.chk_show_membrane.setStyleSheet("""
            QCheckBox { color: #cccccc; margin-left: 10px; font-family: 'Segoe UI', Tahoma, sans-serif; }
            QCheckBox::indicator { width: 14px; height: 14px; background-color: #3c3c3c; border: 1px solid #555; border-radius: 3px; }
            QCheckBox::indicator:checked { background-color: #0e639c; border: 1px solid #0e639c; }
        """)
        
        def _on_membrane_toggled():
            if hasattr(self, 'canvas_renderer') and self.canvas_renderer:
                self.canvas_renderer.viewport().update()
            if hasattr(self, 'tile_renderer') and self.tile_renderer:
                self.tile_renderer.viewport().update()
                
        self.chk_show_membrane.stateChanged.connect(_on_membrane_toggled)
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
        self.sidebar_dock.setStyleSheet("""
            QDockWidget { 
                background-color: #252526; 
                color: #ccc; 
                font-family: 'Segoe UI', Tahoma, sans-serif;
            }
        """)
        
        # We use a Splitter here instead of a fixed layout so the two lists expand dynamically without gaps
        self.sidebar_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # --- Top Half: Project Files ---
        project_widget = QWidget()
        project_layout = QVBoxLayout(project_widget)
        project_layout.setContentsMargins(15, 15, 15, 15)
        project_layout.setSpacing(10)
        
        lbl_proj = QLabel("PROJECT IMAGES")
        lbl_proj.setStyleSheet("color: #aaaaaa; font-size: 8pt; font-weight: bold; letter-spacing: 1px;")
        
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget { background-color: transparent; border: none; outline: none; }
            QListWidget::item { padding: 8px; border-radius: 4px; color: #cccccc; margin-bottom: 2px; }
            QListWidget::item:hover { background-color: #3e3e42; color: #ffffff; }
            QListWidget::item:selected { background-color: #0e639c; color: #ffffff; font-weight: bold; }
        """)
        self.file_list.itemClicked.connect(self.project_manager.switch_image_tab)
        
        add_btn = QPushButton("＋ Add Image")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc; color: white; padding: 8px; font-weight: bold; border-radius: 4px; border: none; font-family: 'Segoe UI', Tahoma, sans-serif;
            }
            QPushButton:hover { background-color: #0098ff; }
            QPushButton:pressed { background-color: #005a9e; }
        """)
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
        
        # 3.5 Right Dock (Properties)
        self.properties_dock = PropertiesPanel("Tile Properties", self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)
        self.properties_dock.hide() # Hidden by default on canvas view
        
        # 4. Status Bar
        self.statusBar().showMessage("Ready. Add an image to start.")

        # Initial model button visibility
        self._on_model_changed(self.combo_model.currentText())
        self.statusBar().setStyleSheet("background-color: #007acc; color: white;")

    def _activate_tool(self, tool_name):
        self.active_tool = tool_name
        self.statusBar().showMessage(f"Tool selected: {tool_name}")
        self.canvas_renderer.set_tool(tool_name)

    def _on_model_changed(self, model_name: str) -> None:
        """Show/hide the 'Segment All' button and parameter controls
        based on whether the selected model is a batch model."""
        is_batch = self.batch_segmentation_service.is_batch_model(model_name)
        self.btn_segment_all.setVisible(is_batch)
        for w in self._batch_param_widgets:
            w.setVisible(is_batch)

    def _run_batch_segmentation(self) -> None:
        """Trigger batch segmentation on the current isolated tile."""
        s = self.current_session
        idx = self.tile_renderer.slice_idx
        if s is None or idx is None:
            self.statusBar().showMessage("No tile is currently isolated.")
            return

        model_name = self.combo_model.currentText()
        if not model_name:
            return

        # Read parameters from UI spinboxes
        diameter = self.spin_diameter.value()
        if diameter == 0.0:
            diameter = None  # auto-detect
        flow_threshold = self.spin_flow.value()
        cellprob_threshold = self.spin_cellprob.value()

        self.statusBar().showMessage(
            f"Running batch segmentation with {model_name}... (this may take a moment)"
        )
        self.tile_renderer.run_batch_segmentation(
            model_name, s, idx, self.batch_segmentation_service,
            diameter=diameter,
            flow_threshold=flow_threshold,
            cellprob_threshold=cellprob_threshold,
        )

    def update_tool_context(self, is_isolated: bool):
        """Enable/Disable tools based on whether the user is in global view or inside an isolated tile."""
        self.action_grid.setEnabled(not is_isolated)
        self.action_brush.setEnabled(not is_isolated)
        self.action_segment.setEnabled(is_isolated)
        self.combo_model.setEnabled(is_isolated)

        # Auto-switch to an available tool safely to avoid undefined states
        if is_isolated and self.active_tool in ("grid", "brush"):
            self.action_segment.setChecked(True)
            self._activate_tool("segment")
        elif not is_isolated and self.active_tool == "segment":
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
        
        # Show and populate properties pane
        self.properties_dock.load_tile(s.tiles[idx])
        self.properties_dock.show()
        
        self._central_stack.setCurrentIndex(1)
        self.update_tool_context(True)

    def switch_to_canvas(self) -> None:
        """Transition from Micro (isolated tile) back to Macro (full image)."""
        self.tile_renderer.unload()
        
        # Hide properties pane
        self.properties_dock.clear()
        self.properties_dock.hide()
        
        self._central_stack.setCurrentIndex(0)
        self.update_tool_context(False)
        self.canvas_renderer.redraw()
