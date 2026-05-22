import sys
import platform
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QToolBar, QDockWidget, QListWidget, QPushButton,
                             QLabel, QFrame, QScrollArea, QSplitter, QStackedWidget,
                             QDoubleSpinBox, QDialog, QTableWidget, QTableWidgetItem,
                             QHeaderView, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QAction, QActionGroup, QKeySequence, QShortcut, QColor, QFont

from app.domain.history import UndoManager
from app.application.project_service import ProjectService
from app.application.export_service import ExportService
from app.application.import_service import TileImportService
from app.application.interactive_segmentation_service import InteractiveSegmentationService
from app.application.batch_segmentation_service import BatchSegmentationService
from app.application.manual_adjustment_service import ManualAdjustmentService
from app.infrastructure.ml_models.nuclick_adapter import NuClickAdapter
from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
from app.infrastructure.ml_models.cellvit_adapter import CellViTAdapter
from PyQt6.QtWidgets import QComboBox, QCheckBox
from app.interface.gui.theme import PALETTE, btn_primary, btn_success, btn_add, btn_add_tile, label_section

# Import the new PyQt Components (to be rewritten in subsequent steps)
from .components import (
    CanvasRenderer,
    TileRenderer,
    ProjectManager,
    SlicePreviews,
    ExportHandler,
    PropertiesPanel,
    LayerDropdown,
    MacroPipelinePanel
)

class SlicerLabApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.is_mac = platform.system() == "Darwin"
        
        self.setWindowTitle("SERAPH")
        self.resize(1400, 900)
        self.setStyleSheet(f"QMainWindow {{ background-color: {PALETTE['bg_base']}; color: {PALETTE['text_primary']}; }}")

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

        ml_models = []
        try:
            nuclick_adapter = NuClickAdapter()
            ml_models.append(nuclick_adapter)
        except Exception as e:
            _cr_logger.error("Failed to load NuClick adapter: %s", e)

        self.segmentation_service = InteractiveSegmentationService(
            models=ml_models
        )

        # Batch models (segment entire tile)
        batch_models = []
        try:
            # Use auto-configuration (gpu=None for auto-detect)
            cellpose_adapter = CellposeAdapter(model_type="cpsam", gpu=None)
            batch_models.append(cellpose_adapter)

            # Log the configuration used
            from app.infrastructure.config.hardware_detector import get_hardware_detector
            detector = get_hardware_detector()
            _cr_logger.info(
                "CellposeAdapter initialized with auto-config: GPU=%s, profile=%s, "
                "cores=%d, memory=%.1fGB, macOS Monterey=%s",
                cellpose_adapter._gpu, detector.get_performance_profile(),
                detector.cpu_cores, detector.memory_gb, detector.is_mac_monterey
            )
        except Exception as e:
            _cr_logger.error("Failed to load Cellpose adapter: %s", e)

        try:
            cellvit_adapter = CellViTAdapter()
            batch_models.append(cellvit_adapter)
            _cr_logger.info("CellViTAdapter registered: %s", cellvit_adapter.name)
        except Exception as e:
            _cr_logger.error("Failed to load CellViT adapter: %s", e)

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
        self.toolbar.setFixedHeight(48)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
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

        self.action_grid = QAction("Grid", self)
        self.action_grid.setToolTip("Grid Tool — rubber-band rectangle selection  [G]")
        self.action_grid.setCheckable(True)
        self.action_grid.setChecked(True)
        self.action_grid.triggered.connect(lambda: self._activate_tool("grid"))
        self.tool_group.addAction(self.action_grid)
        self.toolbar.addAction(self.action_grid)

        self.action_brush = QAction("Brush", self)
        self.action_brush.setToolTip("Brush Tool — freehand polygon selection  [B]")
        self.action_brush.setCheckable(True)
        self.action_brush.triggered.connect(lambda: self._activate_tool("brush"))
        self.tool_group.addAction(self.action_brush)
        self.toolbar.addAction(self.action_brush)

        self.toolbar.addSeparator()

        # Tools exclusively for Tile/Slice Isolation mode
        self.action_segment = QAction("Segment", self)
        self.action_segment.setToolTip("Segment Nucleus — NuClick click-based inference  [S]")
        self.action_segment.setCheckable(True)
        self.action_segment.triggered.connect(lambda: self._activate_tool("segment"))
        self.tool_group.addAction(self.action_segment)
        self.toolbar.addAction(self.action_segment)

        self.action_brush_eraser = QAction("Eraser", self)
        self.action_brush_eraser.setToolTip("Eraser Brush — remove polygon regions  [E]")
        self.action_brush_eraser.setCheckable(True)
        self.action_brush_eraser.triggered.connect(lambda: self._activate_tool("brush_eraser"))
        self.tool_group.addAction(self.action_brush_eraser)
        self.toolbar.addAction(self.action_brush_eraser)

        self.action_brush_select = QAction("Select", self)
        self.action_brush_select.setToolTip("Selection Brush — select polygon regions  [A]")
        self.action_brush_select.setCheckable(True)
        self.action_brush_select.triggered.connect(lambda: self._activate_tool("brush_select"))
        self.tool_group.addAction(self.action_brush_select)
        self.toolbar.addAction(self.action_brush_select)

        # Brush size UI moved to PropertiesPanel side bar

        # Model Selector Combobox in Toolbar
        # Combines both interactive (click) and batch (whole-tile) models
        self.combo_model = QComboBox()
        all_model_names = (
            self.segmentation_service.get_available_models()
            + self.batch_segmentation_service.get_available_models()
        )
        # Add Manual Fine Tune and Nuclick All options
        all_model_names = list(all_model_names) + ["Manual Fine Tune", "Nuclick All"]
        self.combo_model.addItems(all_model_names)
        self.combo_model.setToolTip("Select inference model — batch models enable 'Segment All'  [F5]")
        self.combo_model.currentTextChanged.connect(self._on_model_changed)
        self.toolbar.addWidget(self.combo_model)

        # "Segment All" button — visible only for batch models
        self.btn_segment_all = QPushButton("Segment All")
        self.btn_segment_all.setToolTip("Run batch segmentation on the entire tile  [F5]")
        self.btn_segment_all.setStyleSheet(btn_success())
        self.btn_segment_all.clicked.connect(self._run_batch_segmentation)
        self.btn_segment_all.setVisible(False)  # hidden until a batch model is selected
        self.toolbar.addWidget(self.btn_segment_all)

        self.lbl_execution_time = QLabel("")
        self.lbl_execution_time.setStyleSheet(f"color: {PALETTE['exec_time_done']}; font-weight: bold; font-size: 9pt; margin-left: 8px;")
        self.lbl_execution_time.hide()
        self.toolbar.addWidget(self.lbl_execution_time)

        # ── Cellpose parameters — owned here, displayed in PropertiesPanel ────
        self.spin_diameter = QDoubleSpinBox()
        self.spin_diameter.setRange(0.0, 500.0)
        self.spin_diameter.setValue(30.0)
        self.spin_diameter.setSingleStep(5.0)
        self.spin_diameter.setDecimals(1)
        self.spin_diameter.setSpecialValueText("Auto")
        self.spin_diameter.setToolTip("Expected nucleus diameter in pixels. 0 = auto-detect.")
        self.spin_diameter.setFixedWidth(80)

        self.spin_flow = QDoubleSpinBox()
        self.spin_flow.setRange(0.0, 1.0)
        self.spin_flow.setValue(0.4)
        self.spin_flow.setSingleStep(0.05)
        self.spin_flow.setDecimals(2)
        self.spin_flow.setToolTip("Flow error threshold — lower = stricter (default 0.4)")
        self.spin_flow.setFixedWidth(70)

        self.spin_cellprob = QDoubleSpinBox()
        self.spin_cellprob.setRange(-6.0, 6.0)
        self.spin_cellprob.setValue(0.0)
        self.spin_cellprob.setSingleStep(0.5)
        self.spin_cellprob.setDecimals(1)
        self.spin_cellprob.setToolTip("Cell probability threshold — lower = more detections (default 0.0)")
        self.spin_cellprob.setFixedWidth(70)
        
        # Checkbox for Segmentation Membrane Overlay
        self.chk_show_membrane = QCheckBox("Show Membrane")
        self.chk_show_membrane.setChecked(True)
        self.chk_show_membrane.setToolTip("Toggle polygon/membrane overlay visibility")
        
        def _on_membrane_toggled():
            if hasattr(self, 'canvas_renderer') and self.canvas_renderer:
                self.canvas_renderer.viewport().update()
            if hasattr(self, 'tile_renderer') and self.tile_renderer:
                self.tile_renderer.viewport().update()
                
        self.chk_show_membrane.stateChanged.connect(_on_membrane_toggled)
        self.toolbar.addWidget(self.chk_show_membrane)

        # ── Layer Visibility Dropdown ──────────────────────────────────────────
        self.layer_dropdown = LayerDropdown(parent=self)
        self.layer_dropdown.layerVisibilityChanged.connect(_on_membrane_toggled)
        self.toolbar.addWidget(self.layer_dropdown)

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
        self.sidebar_dock.setMinimumWidth(220)
        
        # We use a Splitter here instead of a fixed layout so the two lists expand dynamically without gaps
        self.sidebar_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # --- Top Half: Project Files ---
        project_widget = QWidget()
        project_layout = QVBoxLayout(project_widget)
        project_layout.setContentsMargins(15, 15, 15, 15)
        project_layout.setSpacing(10)
        
        lbl_proj = QLabel("PROJECT IMAGES")
        lbl_proj.setStyleSheet(label_section())
        
        self.file_list = QListWidget()
        self.file_list.itemClicked.connect(self.project_manager.switch_image_tab)
        
        add_btn = QPushButton("＋ Add Image")
        add_btn.setStyleSheet(btn_add())
        add_btn.clicked.connect(self.project_manager.add_image)

        project_layout.addWidget(lbl_proj)
        project_layout.addWidget(self.file_list)
        project_layout.addWidget(add_btn)

        # --- Bottom Half: Slice Previews ---
        self.slice_previews = SlicePreviews(self)

        # "Add Tile" button sits inside the SlicePreviews widget layout
        # so it's always visible regardless of splitter sizing
        add_tile_btn = QPushButton("＋ Add Tile")
        add_tile_btn.setToolTip("Import a tile descriptor (XML or GeoJSON) into the current session")
        add_tile_btn.setStyleSheet(btn_add_tile())
        add_tile_btn.clicked.connect(self._add_tile)
        self.slice_previews.layout.addWidget(add_tile_btn)

        self.sidebar_splitter.addWidget(project_widget)
        self.sidebar_splitter.addWidget(self.slice_previews)

        # Set default proportions (2 widgets)
        self.sidebar_splitter.setSizes([200, 500])

        self.sidebar_dock.setWidget(self.sidebar_splitter)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.sidebar_dock)
        
        # 3.2 Left Dock Bottom (Macro Pipeline)
        self.macro_pipeline_dock = MacroPipelinePanel(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.macro_pipeline_dock)
        
        # 3.5 Right Dock (Properties)
        self.properties_dock = PropertiesPanel("Tile Properties", self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)
        self.properties_dock.hide()
        self.properties_dock.setup_cellpose_params(
            self.spin_diameter, self.spin_flow, self.spin_cellprob
        )
        
        # 4. Status Bar
        self.statusBar().showMessage("Ready. Add an image to start.")

        # ── Permanent indicators (right zone) ────────────────────────────
        self._sb_perm = QWidget()
        _sb_layout = QHBoxLayout(self._sb_perm)
        _sb_layout.setContentsMargins(0, 0, 4, 0)
        _sb_layout.setSpacing(0)

        _lbl_style = (
            f"color: {PALETTE['text_muted']}; font-size: 8pt; "
            f"background: transparent; padding: 0 8px;"
        )
        _sep_style = f"color: {PALETTE['border']}; background: transparent; padding: 0 2px;"

        self._sb_zoom = QLabel("Zoom: —")
        self._sb_zoom.setStyleSheet(_lbl_style)
        self._sb_nuclei = QLabel("Nuclei: —")
        self._sb_nuclei.setStyleSheet(_lbl_style)
        self._sb_tool = QLabel("Tool: —")
        self._sb_tool.setStyleSheet(_lbl_style)

        sep1 = QLabel("|")
        sep1.setStyleSheet(_sep_style)
        sep2 = QLabel("|")
        sep2.setStyleSheet(_sep_style)

        _sb_layout.addWidget(self._sb_zoom)
        _sb_layout.addWidget(sep1)
        _sb_layout.addWidget(self._sb_nuclei)
        _sb_layout.addWidget(sep2)
        _sb_layout.addWidget(self._sb_tool)

        self.statusBar().addPermanentWidget(self._sb_perm)
        # ─────────────────────────────────────────────────────────────────

        # Initial model button visibility
        self._on_model_changed(self.combo_model.currentText())

        # Phase 1 — menu bar and keyboard shortcuts
        self._setup_menubar()
        self._setup_shortcuts()
        self.layer_dropdown.layerVisibilityChanged.connect(self._sb_refresh)

    def _activate_tool(self, tool_name):
        self.active_tool = tool_name
        self.statusBar().showMessage(f"Tool selected: {tool_name}")
        self.canvas_renderer.set_tool(tool_name)

        is_isolated = self._central_stack.currentIndex() == 1
        self._sb_refresh()

    def _on_model_changed(self, model_name: str) -> None:
        """Show/hide the 'Segment All' button and parameter controls
        based on whether the selected model is a batch model."""
        is_batch = self.batch_segmentation_service.is_batch_model(model_name)
        if model_name == "Nuclick All":
            is_batch = True

        self.btn_segment_all.setVisible(is_batch)
        show_params = is_batch and model_name != "Nuclick All"
        if hasattr(self, "properties_dock"):
            self.properties_dock.show_cellpose_params(show_params)

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

        if model_name == "Nuclick All":
            self.statusBar().showMessage(
                "Running Nuclick on all existing segmentations... (this may take a moment)"
            )
            self.tile_renderer.run_nuclick_all(s, idx, self.segmentation_service)
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
        self.action_brush_eraser.setEnabled(is_isolated)
        self.action_brush_select.setEnabled(is_isolated)
        self.combo_model.setEnabled(is_isolated)

        # Auto-switch to an available tool safely to avoid undefined states
        if is_isolated and self.active_tool in ("grid", "brush"):
            self.action_segment.setChecked(True)
            self._activate_tool("segment")
        elif not is_isolated and self.active_tool in ("segment", "brush_eraser", "brush_select"):
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
        
        # Update layer dropdown
        self.layer_dropdown.set_tile(s.tiles[idx])
        
        self._central_stack.setCurrentIndex(1)
        self.update_tool_context(True)
        self._sb_refresh()

    def switch_to_canvas(self) -> None:
        """Transition from Micro (isolated tile) back to Macro (full image).

        Memory contract: every tile pixel buffer is released here so the
        CanvasRenderer pyramid tile loader gets the full memory budget.
        Tiles will lazily reload their pixels on next user click.
        """
        self.tile_renderer.unload()

        # Evict ALL tile pixel caches — not just the active tile.
        # Previously-visited tiles may still hold PIL Images in RAM,
        # consuming the pyramid cache budget and blocking canvas rendering.
        # evict_all_tile_caches() calls Tile.clear_cache() on every tile;
        # pixels are lazily reloaded on the next switch_to_tile() call.
        s = self.current_session
        if s:
            s.evict_all_tile_caches()

        # Hide properties pane
        self.properties_dock.clear()
        self.properties_dock.hide()

        self._central_stack.setCurrentIndex(0)
        self.update_tool_context(False)
        self.canvas_renderer.redraw()
        self._sb_refresh()

    # ── Phase 1: Menu Bar ────────────────────────────────────────────────────

    def _setup_menubar(self):
        mb = self.menuBar()

        # ── File ──────────────────────────────────────────────────────────
        file_menu = mb.addMenu("&File")

        act_new = QAction("New Project", self)
        act_new.setShortcut(QKeySequence("Ctrl+N"))
        act_new.setStatusTip("Create a new empty project")
        act_new.triggered.connect(self.project_manager.new_project)
        file_menu.addAction(act_new)

        act_open = QAction("Open Project...", self)
        act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.setStatusTip("Open an existing .lab project file")
        act_open.triggered.connect(self.project_manager.open_project)
        file_menu.addAction(act_open)

        file_menu.addSeparator()

        act_save = QAction("Save", self)
        act_save.setShortcut(QKeySequence("Ctrl+S"))
        act_save.setStatusTip("Save the current project")
        act_save.triggered.connect(self.project_manager.save_project)
        file_menu.addAction(act_save)

        act_save_as = QAction("Save As...", self)
        act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        act_save_as.setStatusTip("Save the project to a new file")
        act_save_as.triggered.connect(self.project_manager.save_project_as)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        act_add_img = QAction("Add Image...", self)
        act_add_img.setStatusTip("Add a new image to the project")
        act_add_img.triggered.connect(self.project_manager.add_image)
        file_menu.addAction(act_add_img)

        file_menu.addSeparator()

        act_exit = QAction("Exit", self)
        act_exit.setStatusTip("Exit SERAPH")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # ── Edit ──────────────────────────────────────────────────────────
        edit_menu = mb.addMenu("&Edit")

        act_undo = QAction("Undo", self)
        act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        act_undo.setStatusTip("Undo the last tile operation")
        act_undo.triggered.connect(self._undo)
        edit_menu.addAction(act_undo)

        act_redo = QAction("Redo", self)
        act_redo.setShortcut(QKeySequence("Ctrl+Y"))
        act_redo.setStatusTip("Redo the last undone operation")
        act_redo.triggered.connect(self._redo)
        edit_menu.addAction(act_redo)

        edit_menu.addSeparator()

        act_clear = QAction("Clear Polygons  [C]", self)
        act_clear.setStatusTip("Clear all polygons in the current tile")
        act_clear.triggered.connect(self._clear_polygons)
        edit_menu.addAction(act_clear)

        # ── View ──────────────────────────────────────────────────────────
        view_menu = mb.addMenu("&View")

        act_zoom_in = QAction("Zoom In  [=]", self)
        act_zoom_in.setStatusTip("Zoom in")
        act_zoom_in.triggered.connect(self._zoom_in)
        view_menu.addAction(act_zoom_in)

        act_zoom_out = QAction("Zoom Out  [-]", self)
        act_zoom_out.setStatusTip("Zoom out")
        act_zoom_out.triggered.connect(self._zoom_out)
        view_menu.addAction(act_zoom_out)

        act_zoom_reset = QAction("Zoom to Fit", self)
        act_zoom_reset.setShortcut(QKeySequence("Ctrl+0"))
        act_zoom_reset.setStatusTip("Reset zoom to fit the image in the viewport")
        act_zoom_reset.triggered.connect(self._zoom_reset)
        view_menu.addAction(act_zoom_reset)

        view_menu.addSeparator()

        act_sidebar = QAction("Toggle Sidebar", self)
        act_sidebar.setShortcut(QKeySequence("Ctrl+B"))
        act_sidebar.setStatusTip("Show or hide the project sidebar")
        act_sidebar.triggered.connect(
            lambda: self.sidebar_dock.setVisible(not self.sidebar_dock.isVisible())
        )
        view_menu.addAction(act_sidebar)

        act_props = QAction("Toggle Properties", self)
        act_props.setShortcut(QKeySequence("Ctrl+P"))
        act_props.setStatusTip("Show or hide the tile properties panel")
        act_props.triggered.connect(
            lambda: self.properties_dock.setVisible(not self.properties_dock.isVisible())
        )
        view_menu.addAction(act_props)

        act_pipeline = QAction("Toggle Pipeline Panel", self)
        act_pipeline.setShortcut(QKeySequence("Ctrl+M"))
        act_pipeline.setStatusTip("Show or hide the macro pipeline panel")
        act_pipeline.triggered.connect(
            lambda: self.macro_pipeline_dock.setVisible(not self.macro_pipeline_dock.isVisible())
        )
        view_menu.addAction(act_pipeline)

        view_menu.addSeparator()

        act_back = QAction("Back to Canvas  [Esc]", self)
        act_back.setStatusTip("Return from tile view to the full image canvas")
        act_back.triggered.connect(self._back_to_canvas)
        view_menu.addAction(act_back)

        # ── Tools ─────────────────────────────────────────────────────────
        tools_menu = mb.addMenu("&Tools")

        act_tool_grid = QAction("Grid Tool  [G]", self)
        act_tool_grid.setStatusTip("Rubber-band rectangle selection for grid tiles")
        act_tool_grid.triggered.connect(
            lambda: (self.action_grid.setChecked(True), self._activate_tool("grid"))
        )
        tools_menu.addAction(act_tool_grid)

        act_tool_brush = QAction("Brush Tool  [B]", self)
        act_tool_brush.setStatusTip("Freehand brush for creating polygon tiles")
        act_tool_brush.triggered.connect(
            lambda: (self.action_brush.setChecked(True), self._activate_tool("brush"))
        )
        tools_menu.addAction(act_tool_brush)

        tools_menu.addSeparator()

        act_tool_seg = QAction("Segment Nucleus  [S]", self)
        act_tool_seg.setStatusTip("Click-based NuClick segmentation (tile view only)")
        act_tool_seg.triggered.connect(
            lambda: (self.action_segment.setChecked(True), self._activate_tool("segment"))
        )
        tools_menu.addAction(act_tool_seg)

        act_tool_eraser = QAction("Eraser Brush  [E]", self)
        act_tool_eraser.setStatusTip("Brush eraser for removing polygon areas (tile view only)")
        act_tool_eraser.triggered.connect(
            lambda: (self.action_brush_eraser.setChecked(True), self._activate_tool("brush_eraser"))
        )
        tools_menu.addAction(act_tool_eraser)

        act_tool_select = QAction("Selection Brush  [A]", self)
        act_tool_select.setStatusTip("Brush-based selection for polygon editing (tile view only)")
        act_tool_select.triggered.connect(
            lambda: (self.action_brush_select.setChecked(True), self._activate_tool("brush_select"))
        )
        tools_menu.addAction(act_tool_select)

        tools_menu.addSeparator()

        act_run_seg = QAction("Run Segmentation", self)
        act_run_seg.setShortcut(QKeySequence("F5"))
        act_run_seg.setStatusTip("Run batch segmentation on the current tile")
        act_run_seg.triggered.connect(self._run_batch_segmentation)
        tools_menu.addAction(act_run_seg)

        act_export_h5 = QAction("Export to HDF5...", self)
        act_export_h5.setShortcut(QKeySequence("Ctrl+E"))
        act_export_h5.setStatusTip("Export all segmented nuclei to an HDF5 ML dataset")
        act_export_h5.triggered.connect(self.export_handler.export_nuclei_h5)
        tools_menu.addAction(act_export_h5)

        # ── Help ──────────────────────────────────────────────────────────
        help_menu = mb.addMenu("&Help")

        act_shortcuts = QAction("Keyboard Shortcuts", self)
        act_shortcuts.setShortcut(QKeySequence("F1"))
        act_shortcuts.setStatusTip("Show all keyboard shortcuts")
        act_shortcuts.triggered.connect(self._show_shortcuts_dialog)
        help_menu.addAction(act_shortcuts)

        help_menu.addSeparator()

        act_about = QAction("About SERAPH", self)
        act_about.setStatusTip("About SERAPH")
        act_about.triggered.connect(self._show_about_dialog)
        help_menu.addAction(act_about)

    # ── Phase 1: Keyboard Shortcuts ──────────────────────────────────────────

    def _setup_shortcuts(self):
        """Bind single-character shortcuts to the central stack.

        WidgetWithChildrenShortcut ensures shortcuts only fire when the
        canvas or tile renderer has focus — text input fields are unaffected.
        Ctrl+ combinations are bound globally (WindowShortcut) since they
        cannot conflict with typing.
        """
        def _canvas_sc(key, slot):
            sc = QShortcut(QKeySequence(key), self._central_stack)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

        def _window_sc(key, slot):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(slot)

        # Canvas-mode tools
        _canvas_sc("G", lambda: (self.action_grid.setChecked(True),    self._activate_tool("grid")))
        _canvas_sc("B", lambda: (self.action_brush.setChecked(True),   self._activate_tool("brush")))

        # Tile-mode tools
        _canvas_sc("S", lambda: (self.action_segment.setChecked(True),      self._activate_tool("segment")))
        _canvas_sc("E", lambda: (self.action_brush_eraser.setChecked(True), self._activate_tool("brush_eraser")))
        _canvas_sc("A", lambda: (self.action_brush_select.setChecked(True), self._activate_tool("brush_select")))

        # Edit
        _canvas_sc("C", self._clear_polygons)

        # Zoom (canvas context — fine for =, -)
        _canvas_sc("=", self._zoom_in)
        _canvas_sc("+", self._zoom_in)
        _canvas_sc("-", self._zoom_out)

        # Navigation (window-wide — Escape and F1 are safe globally)
        _window_sc("Escape", self._back_to_canvas)
        _window_sc("F1",     self._show_shortcuts_dialog)

    # ── Action Implementations ───────────────────────────────────────────────

    def _undo(self):
        session = self.undo_manager.undo()
        if session:
            self.slice_previews.update_previews()
            if self._central_stack.currentIndex() == 1:
                self.tile_renderer.viewport().update()
            else:
                self.canvas_renderer.redraw()
            self.statusBar().showMessage("Undo")
        else:
            self.statusBar().showMessage("Nothing to undo")

    def _redo(self):
        session = self.undo_manager.redo()
        if session:
            self.slice_previews.update_previews()
            if self._central_stack.currentIndex() == 1:
                self.tile_renderer.viewport().update()
            else:
                self.canvas_renderer.redraw()
            self.statusBar().showMessage("Redo")
        else:
            self.statusBar().showMessage("Nothing to redo")

    def _clear_polygons(self):
        s = self.current_session
        if not s:
            return
        if self._central_stack.currentIndex() == 1:
            idx = self.tile_renderer.slice_idx
            if idx is not None and idx < len(s.tiles):
                self.undo_manager.push(s, "clear")
                s.tiles[idx].segmentation_layers.clear()
                self.tile_renderer.viewport().update()
                self.statusBar().showMessage("Polygons cleared")
        else:
            self.statusBar().showMessage("Enter a tile to clear its polygons")

    def _active_renderer(self):
        return self.canvas_renderer if self._central_stack.currentIndex() == 0 else self.tile_renderer

    def _sb_refresh(self) -> None:
        """Refresh permanent status bar indicators from current app state."""
        zoom = getattr(self._active_renderer(), "viewport_zoom", None)
        self._sb_zoom.setText(f"Zoom: {zoom * 100:.0f}%" if zoom is not None else "Zoom: —")

        tool = getattr(self, "active_tool", None)
        self._sb_tool.setText(f"Tool: {tool}" if tool else "Tool: —")

        if self._central_stack.currentIndex() == 1 and self.current_session:
            idx = getattr(self.tile_renderer, "slice_idx", None)
            if idx is not None and idx < len(self.current_session.tiles):
                tile = self.current_session.tiles[idx]
                count = sum(
                    len(layer.get("polygons", []))
                    for layer in tile.segmentation_layers
                    if layer.get("visible", True)
                )
                self._sb_nuclei.setText(f"Nuclei: {count:,}")
                return
        self._sb_nuclei.setText("Nuclei: —")

    def _zoom_in(self):
        r = self._active_renderer()
        if hasattr(r, "viewport_zoom"):
            r.viewport_zoom = min(r.viewport_zoom * 1.25, 200.0)
            r.resetTransform()
            r.scale(r.viewport_zoom, r.viewport_zoom)
            r.redraw() if hasattr(r, "redraw") else r.viewport().update()
        self._sb_refresh()

    def _zoom_out(self):
        r = self._active_renderer()
        if hasattr(r, "viewport_zoom"):
            r.viewport_zoom = max(r.viewport_zoom * 0.8, 0.01)
            r.resetTransform()
            r.scale(r.viewport_zoom, r.viewport_zoom)
            r.redraw() if hasattr(r, "redraw") else r.viewport().update()
        self._sb_refresh()

    def _zoom_reset(self):
        s = self.current_session
        r = self._active_renderer()
        if not s or not hasattr(r, "viewport_zoom") or s.real_width <= 0:
            return
        ratio = min(r.width() / s.real_width, r.height() / s.real_height)
        r.viewport_zoom = ratio * 0.95
        r.resetTransform()
        r.scale(r.viewport_zoom, r.viewport_zoom)
        r.centerOn(s.real_width / 2, s.real_height / 2)
        r.redraw() if hasattr(r, "redraw") else r.viewport().update()
        self._sb_refresh()

    def _back_to_canvas(self):
        if self._central_stack.currentIndex() == 1:
            self.switch_to_canvas()

    # ── Help Dialogs ─────────────────────────────────────────────────────────

    def _show_shortcuts_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard Shortcuts — SERAPH")
        dlg.resize(480, 500)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)

        table = QTableWidget(dlg)
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Action", "Shortcut"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        rows = [
            ("── File", ""),
            ("New Project",        "Ctrl+N"),
            ("Open Project",       "Ctrl+O"),
            ("Save",               "Ctrl+S"),
            ("Save As",            "Ctrl+Shift+S"),
            ("── Edit", ""),
            ("Undo",               "Ctrl+Z"),
            ("Redo",               "Ctrl+Y"),
            ("Clear Polygons",     "C"),
            ("── Canvas Tools", ""),
            ("Grid Tool",          "G"),
            ("Brush Tool",         "B"),
            ("── Tile Tools", ""),
            ("Segment Nucleus",    "S"),
            ("Eraser Brush",       "E"),
            ("Selection Brush",    "A"),
            ("Run Segmentation",   "F5"),
            ("Export HDF5",        "Ctrl+E"),
            ("── View", ""),
            ("Zoom In",            "="),
            ("Zoom Out",           "-"),
            ("Zoom to Fit",        "Ctrl+0"),
            ("Toggle Sidebar",     "Ctrl+B"),
            ("Toggle Properties",  "Ctrl+P"),
            ("Toggle Pipeline",    "Ctrl+M"),
            ("Back to Canvas",     "Escape"),
            ("Keyboard Shortcuts", "F1"),
            ("── Mouse", ""),
            ("Pan",                "Left-click drag"),
            ("Zoom",               "Ctrl + Scroll"),
            ("NuClick Segment",    "Right-click (tile view)"),
        ]

        table.setRowCount(len(rows))
        muted = QColor(PALETTE["text_muted"])
        accent = QColor(PALETTE["accent"])
        bold_font = QFont()
        bold_font.setBold(True)

        for i, (label, key) in enumerate(rows):
            item_l = QTableWidgetItem(label)
            item_k = QTableWidgetItem(key)
            if label.startswith("──"):
                item_l.setFont(bold_font)
                item_l.setForeground(muted)
                item_k.setForeground(muted)
            else:
                item_k.setForeground(accent)
            table.setItem(i, 0, item_l)
            table.setItem(i, 1, item_k)

        layout.addWidget(table)
        dlg.exec()

    def _show_about_dialog(self):
        QMessageBox.about(
            self,
            "About SERAPH",
            "<b>SERAPH</b><br>"
            "<i>Segmentation Engine for Research in<br>Anatomical Pathology and Histology</i>"
            "<br><br>"
            "IMSCIENCE — Image and Multimedia Data Science Laboratory<br>"
            "Developed by <b>Matheus Fagundes</b>"
            "<br><br>"
            "PyQt6 &nbsp;·&nbsp; Cellpose &nbsp;·&nbsp; NuClick"
            " &nbsp;·&nbsp; OpenSlide &nbsp;·&nbsp; pyvips"
        )
