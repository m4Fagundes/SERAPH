import sys
import platform
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QDockWidget, QPushButton,
                             QLabel, QStackedWidget,
                             QDoubleSpinBox, QDialog, QFormLayout, QDialogButtonBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
                             QInputDialog, QMenu, QSpinBox)
from PyQt6.QtCore import Qt, QPoint, QSize
from PyQt6.QtGui import QIcon, QAction, QKeySequence, QShortcut, QColor, QFont

from app.domain.history import UndoManager
from app.application.project_service import ProjectService
from app.application.export_service import ExportService
from app.application.import_service import TileImportService
from app.application.interactive_segmentation_service import InteractiveSegmentationService
from app.application.batch_segmentation_service import BatchSegmentationService
from app.application.manual_adjustment_service import ManualAdjustmentService
from app.infrastructure.ml_models.nuclick_adapter import NuClickAdapter
from app.infrastructure.ml_models.idisf_adapter import IDISFAdapter
from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
from app.infrastructure.ml_models.cellvit_adapter import CellViTAdapter
from app.infrastructure.ml_models.patho_sam_adapter import PathoSAMAdapter
from app.infrastructure.ml_models.dinosim_adapter import DINOSimAdapter
from PyQt6.QtWidgets import QComboBox, QCheckBox
from app.interface.gui.theme import (
    PALETTE,
    create_layout_sidebar_right_icon,
    create_seraph_icon,
    tool_pill,
)
from app.interface.gui.widgets import PrimaryButton, SecondaryButton, SuccessButton

# Import the new PyQt Components (to be rewritten in subsequent steps)
from .components import (
    CanvasRenderer,
    TileRenderer,
    ProjectManager,
    SlicePreviews,
    ExportHandler,
    PropertiesPanel,
    LayerDropdown,
    MacroPipelinePanel,
    ImageTabStrip,
    CollapsibleSidebar,
    ContextBar,
    WelcomePage,
)

class SlicerLabApp(QMainWindow):
    PAGE_WELCOME = 0
    PAGE_CANVAS = 1
    PAGE_TILE = 2

    def __init__(self):
        super().__init__()
        self.is_mac = platform.system() == "Darwin"
        
        self.setWindowTitle("SERAPH")
        self.resize(1400, 900)
        from PyQt6.QtGui import QIcon
        self.setWindowIcon(QIcon(create_seraph_icon(64)))
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
        self.idisf_adapter = None
        try:
            nuclick_adapter = NuClickAdapter()
            ml_models.append(nuclick_adapter)
        except Exception as e:
            _cr_logger.error("Failed to load NuClick adapter: %s", e)

        try:
            idisf_adapter = IDISFAdapter()
            self.idisf_adapter = idisf_adapter
            ml_models.append(idisf_adapter)
            _cr_logger.info("IDISFAdapter registered: %s", idisf_adapter.name)
        except Exception as e:
            _cr_logger.error("Failed to load iDISF adapter: %s", e)

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

        try:
            patho_sam_adapter = PathoSAMAdapter()
            batch_models.append(patho_sam_adapter)
            _cr_logger.info("PathoSAMAdapter registered: %s", patho_sam_adapter.name)
        except Exception as e:
            _cr_logger.error("Failed to load PathoSAM adapter: %s", e)

        try:
            dinosim_adapter = DINOSimAdapter(model_size="small")
            batch_models.append(dinosim_adapter)
            _cr_logger.info("DINOSimAdapter registered: %s", dinosim_adapter.name)
        except Exception as e:
            _cr_logger.error("Failed to load DINOSim adapter: %s", e)

        self.batch_segmentation_service = BatchSegmentationService(
            models=batch_models
        )
        self.manual_adjustment_service = ManualAdjustmentService()
        self.undo_manager = UndoManager()

        self._setup_ui()

    def _setup_ui(self):
        # Sub-modules must be initialized first — referenced throughout this method
        self.project_manager = ProjectManager(self)
        self.export_handler = ExportHandler(self)
        self.export_format = ".png"

        # 1. Central Widget — tab bar (session switcher) + QStackedWidget
        self._central_stack = QStackedWidget()
        self.welcome_page = WelcomePage(self)
        self.canvas_renderer = CanvasRenderer(self)
        self.tile_renderer   = TileRenderer(self)
        self._central_stack.addWidget(self.welcome_page)
        self._central_stack.addWidget(self.canvas_renderer)
        self._central_stack.addWidget(self.tile_renderer)
        self._central_stack.setCurrentIndex(self.PAGE_WELCOME)

        # Browser-style image tab strip.
        self.image_tabs = ImageTabStrip(self)
        self.image_tabs.currentChanged.connect(self._on_tab_changed)
        self.image_tabs.tabClicked.connect(self._on_image_tab_clicked)
        self.image_tabs.closeRequested.connect(self._on_tab_close_requested)
        self.image_tabs.addRequested.connect(self.project_manager.add_image)

        self.context_bar = ContextBar(self)
        self.context_bar.mpp_edit_requested.connect(self._on_mpp_edit_requested)
        self.welcome_page.btn_open_project.clicked.connect(self.project_manager.open_project)
        self.welcome_page.btn_open_image.clicked.connect(self.project_manager.add_image)

        _central_container = QWidget()
        _central_layout = QVBoxLayout(_central_container)
        _central_layout.setContentsMargins(0, 0, 0, 0)
        _central_layout.setSpacing(0)
        _central_layout.addWidget(self.image_tabs)
        _central_layout.addWidget(self.context_bar)
        _central_layout.addWidget(self._central_stack)
        self.setCentralWidget(_central_container)

        # 2. Compact editor-header controls — same row as image tabs.
        self.btn_tool_pill = QPushButton("Grid  ▾")
        self.btn_tool_pill.setToolTip("Active tool — click to switch  [G / B / S / E / A]")
        self.btn_tool_pill.setFixedHeight(28)
        self.btn_tool_pill.setStyleSheet(tool_pill())
        self.btn_tool_pill.clicked.connect(self._show_tool_menu)
        self.context_bar.add_action_widget(self.btn_tool_pill)

        self.combo_model = QComboBox()
        interactive_model_names = list(self.segmentation_service.get_available_models())
        if "NuClick (PyTorch)" not in interactive_model_names:
            interactive_model_names.insert(0, "NuClick (PyTorch)")
        self.combo_model.addItems(interactive_model_names + ["Manual Fine Tune"])
        self.combo_model.setToolTip("Choose the click/manual segmentation mode for the active slice")
        self.combo_model.setFixedHeight(28)
        self.combo_model.setMinimumWidth(150)
        self.combo_model.currentTextChanged.connect(self._on_model_changed)
        self.combo_model.setVisible(False)
        self.context_bar.add_action_widget(self.combo_model)

        # Kept as state text target for _update_breadcrumb(), but intentionally
        # not rendered in the chrome. Open image tabs carry this context.
        self.lbl_breadcrumb = QLabel("No project open")

        # ── Cellpose parameters — owned here, displayed in PropertiesPanel ──
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

        # ── iDISF parameters — used by click-based iDISF segmentation ───────
        self.spin_idisf_crop = QSpinBox()
        self.spin_idisf_crop.setRange(64, 768)
        self.spin_idisf_crop.setValue(256)
        self.spin_idisf_crop.setSingleStep(32)
        self.spin_idisf_crop.setSuffix(" px")
        self.spin_idisf_crop.setToolTip("Local crop around the click. Larger = more context, slower and less local.")
        self.spin_idisf_crop.setFixedWidth(82)

        self.spin_idisf_n0 = QSpinBox()
        self.spin_idisf_n0.setRange(10, 2000)
        self.spin_idisf_n0.setValue(160)
        self.spin_idisf_n0.setSingleStep(25)
        self.spin_idisf_n0.setToolTip("Initial number of GRID seeds. Higher = finer segmentation.")
        self.spin_idisf_n0.setFixedWidth(82)

        self.spin_idisf_iterations = QSpinBox()
        self.spin_idisf_iterations.setRange(1, 20)
        self.spin_idisf_iterations.setValue(4)
        self.spin_idisf_iterations.setSingleStep(1)
        self.spin_idisf_iterations.setToolTip("Number of iDISF seed-removal iterations.")
        self.spin_idisf_iterations.setFixedWidth(82)

        self.spin_idisf_path_cost = QSpinBox()
        self.spin_idisf_path_cost.setRange(1, 6)
        self.spin_idisf_path_cost.setValue(4)
        self.spin_idisf_path_cost.setSingleStep(1)
        self.spin_idisf_path_cost.setToolTip("Path-cost function ID: 1=color, 2=gradient, 3=beta norm, 4=CV tree norm, 5=sum gradient, 6=sum beta.")
        self.spin_idisf_path_cost.setFixedWidth(82)

        self.spin_idisf_c1 = QDoubleSpinBox()
        self.spin_idisf_c1.setRange(0.1, 1.0)
        self.spin_idisf_c1.setValue(0.7)
        self.spin_idisf_c1.setSingleStep(0.05)
        self.spin_idisf_c1.setDecimals(2)
        self.spin_idisf_c1.setToolTip("iDISF c1 constant for path-cost functions.")
        self.spin_idisf_c1.setFixedWidth(82)

        self.spin_idisf_c2 = QDoubleSpinBox()
        self.spin_idisf_c2.setRange(0.1, 1.0)
        self.spin_idisf_c2.setValue(0.8)
        self.spin_idisf_c2.setSingleStep(0.05)
        self.spin_idisf_c2.setDecimals(2)
        self.spin_idisf_c2.setToolTip("iDISF c2 constant for path-cost functions.")
        self.spin_idisf_c2.setFixedWidth(82)

        for widget in (
            self.spin_idisf_crop,
            self.spin_idisf_n0,
            self.spin_idisf_iterations,
            self.spin_idisf_path_cost,
            self.spin_idisf_c1,
            self.spin_idisf_c2,
        ):
            widget.valueChanged.connect(self._sync_idisf_params)

        # ── Membrane toggle + layer dropdown (injected into PropertiesPanel) ─
        self.chk_show_membrane = QCheckBox("Show Membrane")
        self.chk_show_membrane.setChecked(True)
        self.chk_show_membrane.setToolTip("Toggle polygon/membrane overlay visibility")

        def _on_membrane_toggled():
            if hasattr(self, 'canvas_renderer') and self.canvas_renderer:
                self.canvas_renderer.viewport().update()
            if hasattr(self, 'tile_renderer') and self.tile_renderer:
                self.tile_renderer.viewport().update()

        self.chk_show_membrane.stateChanged.connect(_on_membrane_toggled)

        self.layer_dropdown = LayerDropdown(parent=self)
        self.layer_dropdown.layerVisibilityChanged.connect(_on_membrane_toggled)

        # ── Execution time label — lives in status bar, updated by tile_renderer
        self.lbl_execution_time = QLabel("")
        self.lbl_execution_time.setStyleSheet(
            f"color: {PALETTE['exec_time_done']}; font-weight: bold; font-size: 8pt; "
            f"background: transparent; padding: 0 8px;"
        )
        self.lbl_execution_time.hide()

        # 3. Left Dock (Sidebar) — Slices only; images live in the tab bar
        self.sidebar_dock = QDockWidget("Slices", self)
        self.sidebar_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.sidebar_dock.setMinimumWidth(220)
        _sidebar_titlebar = QWidget()
        _sidebar_titlebar.setFixedHeight(0)
        self.sidebar_dock.setTitleBarWidget(_sidebar_titlebar)

        self.slice_previews = SlicePreviews(self, show_header=False)
        self.slice_previews.batchSelectionChanged.connect(self._on_batch_selection_changed)

        self.sidebar_shell = CollapsibleSidebar("Slices", self.slice_previews, self)
        self.slice_previews.countChanged.connect(self._on_slice_count_changed)
        self.sidebar_shell.collapsedChanged.connect(self._set_sidebar_collapsed)
        self.sidebar_dock.setWidget(self.sidebar_shell)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.sidebar_dock)
        
        # 3.2 Left Dock Bottom (Macro Pipeline)
        self.macro_pipeline_dock = MacroPipelinePanel(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.macro_pipeline_dock)
        self.macro_pipeline_dock.hide()
        
        # 3.5 Right Dock (Properties)
        self.properties_dock = PropertiesPanel("Tile Properties", self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)
        self.properties_dock.hide()
        self.properties_dock.setup_cellpose_params(
            self.spin_diameter, self.spin_flow, self.spin_cellprob
        )
        self.properties_dock.setup_idisf_params(
            self.spin_idisf_crop,
            self.spin_idisf_n0,
            self.spin_idisf_iterations,
            self.spin_idisf_path_cost,
            self.spin_idisf_c1,
            self.spin_idisf_c2,
        )
        self.properties_dock.setup_overlay_controls(
            self.chk_show_membrane, self.layer_dropdown
        )
        self.properties_dock.visibilityChanged.connect(self._sync_panel_toggles)

        self.btn_toggle_properties = QPushButton()
        self.btn_toggle_properties.setObjectName("panel_toggle")
        self.btn_toggle_properties.setCheckable(True)
        self.btn_toggle_properties.setFixedSize(28, 28)
        self.btn_toggle_properties.setIconSize(QSize(16, 16))
        self.btn_toggle_properties.setIcon(QIcon(create_layout_sidebar_right_icon(16, False)))
        self.btn_toggle_properties.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_properties.setToolTip("Toggle tile properties panel")
        self.btn_toggle_properties.clicked.connect(
            lambda checked: self.properties_dock.setVisible(checked)
        )

        self._menu_panel_controls = QWidget()
        self._menu_panel_controls.setObjectName("menu_panel_controls")
        self._menu_panel_controls.setStyleSheet(
            "QWidget#menu_panel_controls { background: transparent; border: none; }"
        )
        _panel_controls_layout = QHBoxLayout(self._menu_panel_controls)
        _panel_controls_layout.setContentsMargins(0, 0, 8, 0)
        _panel_controls_layout.setSpacing(4)
        _panel_controls_layout.addWidget(self.btn_toggle_properties)

        # ── Context actions — shown according to overview/tile state ─────────
        self.btn_ctx_grid = SecondaryButton("Grid", size="xs")
        self.btn_ctx_grid.setToolTip("Grid settings for overview mode")
        self.btn_ctx_grid.clicked.connect(self._show_grid_settings_dialog)
        self.context_bar.add_action_widget(self.btn_ctx_grid)
        
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
        self.statusBar().addPermanentWidget(self.lbl_execution_time)
        # ─────────────────────────────────────────────────────────────────

        # Initial state
        self._on_model_changed(self.combo_model.currentText())
        self._refresh_sidebar_state()
        self._show_welcome_page()

        # Phase 1 — menu bar and keyboard shortcuts
        self._setup_menubar()
        self.menuBar().setCornerWidget(self._menu_panel_controls, Qt.Corner.TopRightCorner)
        self._setup_shortcuts()
        self.layer_dropdown.layerVisibilityChanged.connect(self._sb_refresh)

    # ── Image tab bar handlers ───────────────────────────────────────────────────

    def _on_tab_changed(self, index: int) -> None:
        if 0 <= index < len(self.sessions):
            self.project_manager._activate_session(self.sessions[index])

    def _on_image_tab_clicked(self, index: int) -> None:
        if 0 <= index < len(self.sessions):
            if self.current_session is not self.sessions[index]:
                self.project_manager._activate_session(self.sessions[index])
            elif self._central_stack.currentIndex() == self.PAGE_TILE:
                self.switch_to_canvas()

    def _on_tab_close_requested(self, index: int) -> None:
        if not (0 <= index < len(self.sessions)):
            return
        self.sessions.pop(index)
        self.image_tabs.tab_bar.blockSignals(True)
        self.image_tabs.remove_tab(index)
        self.image_tabs.tab_bar.blockSignals(False)
        if self.sessions:
            new_idx = min(index, len(self.sessions) - 1)
            self.image_tabs.set_current_index(new_idx)
            self.project_manager._activate_session(self.sessions[new_idx])
        else:
            self.current_session = None
            self.canvas_renderer.scene.clear()
            self.canvas_renderer.on_session_closed()
            self.slice_previews.update_previews()
            self._show_welcome_page()
            self._update_breadcrumb()
            self._update_context_bar()

    # ── Sidebar shell ───────────────────────────────────────────────────────────

    def _toggle_sidebar(self) -> None:
        self.sidebar_shell.toggle_collapsed()

    def _set_sidebar_collapsed(self, collapsed: bool) -> None:
        if collapsed:
            self.sidebar_dock.setFixedHeight(36)
        else:
            self.sidebar_dock.setMinimumHeight(0)
            self.sidebar_dock.setMaximumHeight(16777215)

    def _on_slice_count_changed(self, count: int) -> None:
        self.sidebar_shell.set_badge_count(count)
        self._refresh_sidebar_state(count)

    def _refresh_sidebar_state(self, slice_count: int | None = None) -> None:
        s = self.current_session
        if slice_count is None:
            slice_count = len(s.tiles) if s else 0

        has_image = s is not None
        has_slices = has_image and slice_count > 0

        self.macro_pipeline_dock.setVisible(has_slices)
        self._update_context_bar()

    def _update_context_bar(self) -> None:
        s = self.current_session
        if s is None:
            self.context_bar.set_overview(None)
            self._update_context_actions("empty")
            return

        if self._central_stack.currentIndex() != self.PAGE_TILE:
            self.context_bar.set_overview(s, len(s.tiles))
            self._update_context_actions("overview")
            return

        idx = getattr(self.tile_renderer, "slice_idx", None)
        if idx is None or idx >= len(s.tiles):
            self.context_bar.set_overview(s, len(s.tiles))
            self._update_context_actions("overview")
            return

        tile = s.tiles[idx]
        custom = tile.metadata.get("name", "")
        slice_label = custom if custom else f"Slice {idx + 1}"
        nuclei_count = sum(
            len(layer.get("polygons", []))
            for layer in tile.segmentation_layers
            if layer.get("visible", True)
        )
        self.context_bar.set_slice(s, slice_label, nuclei_count)
        self._update_context_actions("slice")

    def _update_context_actions(self, mode: str) -> None:
        if not hasattr(self, "btn_ctx_grid"):
            return

        s = self.current_session
        has_slices = bool(s and s.tiles)
        is_overview = mode == "overview"
        is_slice = mode == "slice"

        self.btn_tool_pill.setVisible(s is not None)
        self.btn_ctx_grid.setVisible(is_overview and s is not None)
        self.btn_toggle_properties.setVisible(is_slice)
        self._sync_panel_toggles()

    def _sync_panel_toggles(self) -> None:
        if not hasattr(self, "btn_toggle_properties"):
            return
        self.btn_toggle_properties.blockSignals(True)
        is_open = self.properties_dock.isVisible()
        self.btn_toggle_properties.setChecked(is_open)
        self.btn_toggle_properties.setIcon(QIcon(create_layout_sidebar_right_icon(16, is_open)))
        self.btn_toggle_properties.blockSignals(False)

    def _activate_tool(self, tool_name):
        self.active_tool = tool_name
        self.canvas_renderer.set_tool(tool_name)
        self._update_tool_pill()
        self._sb_refresh()

    def _sync_idisf_params(self, *_args) -> None:
        adapter = getattr(self, "idisf_adapter", None)
        if adapter is None:
            return
        adapter.set_parameters(
            crop_size=self.spin_idisf_crop.value(),
            n0=self.spin_idisf_n0.value(),
            iterations=self.spin_idisf_iterations.value(),
            path_cost_function=self.spin_idisf_path_cost.value(),
            c1=self.spin_idisf_c1.value(),
            c2=self.spin_idisf_c2.value(),
        )

    def _on_model_changed(self, model_name: str) -> None:
        if hasattr(self, "properties_dock"):
            self.properties_dock.show_cellpose_params(False)
            self.properties_dock.show_idisf_params(model_name == "iDISF")
        if model_name == "iDISF":
            self._sync_idisf_params()

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
        """Switch toolbar to the tool set that is valid for the current environment."""
        if is_isolated and self.active_tool in ("grid", "brush"):
            self._activate_tool("segment")
        elif not is_isolated and self.active_tool in ("segment", "brush_eraser", "brush_select"):
            self._activate_tool("grid")

        self.combo_model.setVisible(is_isolated)
        self._update_tool_pill()
        self._update_breadcrumb()

    def _on_batch_selection_changed(self, _count: int) -> None:
        panel = getattr(self, "macro_pipeline_dock", None)
        if panel is not None and hasattr(panel, "refresh_selection_state"):
            panel.refresh_selection_state()

    def _run_selected_slices(self) -> None:
        panel = getattr(self, "macro_pipeline_dock", None)
        if panel is not None and hasattr(panel, "_on_run_clicked"):
            panel._on_run_clicked()

    def _add_tile(self):
        """Slot for the 'Add Tile' button — delegates to project_manager."""
        self.project_manager.add_tile()

    # ── Environment Switching (Bounded Context Transitions) ─────────────────

    def switch_to_tile(self, idx: int) -> None:
        """Transition from Macro (full image) to Micro (isolated tile editing)."""
        s = self.current_session
        if not s or idx >= len(s.tiles):
            return
        self.sidebar_dock.show()
        self.image_tabs.show()
        self.context_bar.show()
        self.tile_renderer.load_tile(s, idx)
        
        # Show and populate properties pane
        self.properties_dock.load_tile(s.tiles[idx])
        self.properties_dock.show()
        
        # Update layer dropdown
        self.layer_dropdown.set_tile(s.tiles[idx])
        
        self._central_stack.setCurrentIndex(self.PAGE_TILE)
        self.slice_previews.select_slice(idx)
        self.update_tool_context(True)
        self._update_context_bar()
        self._update_breadcrumb()
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
        else:
            self._show_welcome_page()
            return

        # Hide properties pane
        self.properties_dock.clear()
        self.properties_dock.hide()

        self._central_stack.setCurrentIndex(self.PAGE_CANVAS)
        self.sidebar_dock.show()
        self.image_tabs.show()
        self.context_bar.show()
        self.slice_previews.select_slice(None)
        self.update_tool_context(False)
        self._update_context_bar()
        self._update_breadcrumb()
        self.canvas_renderer.redraw()
        self._sb_refresh()

    def _show_welcome_page(self) -> None:
        self._central_stack.setCurrentIndex(self.PAGE_WELCOME)
        self.sidebar_dock.hide()
        self.image_tabs.hide()
        self.context_bar.hide()
        self.context_bar.set_overview(None)
        self.macro_pipeline_dock.hide()
        self.properties_dock.hide()
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

        act_import_slice_images = QAction("Import Slice Images Folder...", self)
        act_import_slice_images.setStatusTip("Create one slice per image from a folder of small images")
        act_import_slice_images.triggered.connect(self.project_manager.import_slice_images_folder)
        file_menu.addAction(act_import_slice_images)

        act_import_tile = QAction("Import Tile...", self)
        act_import_tile.setStatusTip("Import a tile descriptor into the current image")
        act_import_tile.triggered.connect(self._add_tile)
        file_menu.addAction(act_import_tile)

        file_menu.addSeparator()

        export_menu = file_menu.addMenu("Export")

        act_export_slices = QAction("Export Slices...", self)
        act_export_slices.setStatusTip("Export slices from the current image")
        act_export_slices.triggered.connect(self.export_handler.export_slices)
        export_menu.addAction(act_export_slices)

        act_export_nuclei = QAction("Export Nuclei...", self)
        act_export_nuclei.setStatusTip("Export nuclei from the current image or tile")
        act_export_nuclei.triggered.connect(self.export_handler.export_nuclei)
        export_menu.addAction(act_export_nuclei)

        act_export_probability_map = QAction("Export Probability Map...", self)
        act_export_probability_map.setStatusTip("Export TIFF probability maps from existing segmentation layers")
        act_export_probability_map.triggered.connect(self.export_handler.export_probability_maps)
        export_menu.addAction(act_export_probability_map)

        act_export_h5_file = QAction("Export Nuclei (HDF5)...", self)
        act_export_h5_file.setShortcut(QKeySequence("Ctrl+E"))
        act_export_h5_file.setStatusTip("Export all segmented nuclei to an HDF5 ML dataset")
        act_export_h5_file.triggered.connect(self.export_handler.export_nuclei_h5)
        export_menu.addAction(act_export_h5_file)

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

        act_sidebar = QAction("Collapse/Expand Slices", self)
        act_sidebar.setShortcut(QKeySequence("Ctrl+B"))
        act_sidebar.setStatusTip("Collapse or expand the slices sidebar")
        act_sidebar.triggered.connect(self._toggle_sidebar)
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
        act_tool_grid.triggered.connect(lambda: self._activate_tool("grid"))
        tools_menu.addAction(act_tool_grid)

        act_tool_brush = QAction("Brush Tool  [B]", self)
        act_tool_brush.setStatusTip("Freehand brush for creating polygon tiles")
        act_tool_brush.triggered.connect(lambda: self._activate_tool("brush"))
        tools_menu.addAction(act_tool_brush)

        tools_menu.addSeparator()

        act_tool_seg = QAction("Segment Nucleus  [S]", self)
        act_tool_seg.setStatusTip("Click-based segmentation (tile view only)")
        act_tool_seg.triggered.connect(lambda: self._activate_tool("segment"))
        tools_menu.addAction(act_tool_seg)

        act_tool_eraser = QAction("Eraser Brush  [E]", self)
        act_tool_eraser.setStatusTip("Brush eraser for removing polygon areas (tile view only)")
        act_tool_eraser.triggered.connect(lambda: self._activate_tool("brush_eraser"))
        tools_menu.addAction(act_tool_eraser)

        act_tool_select = QAction("Selection Brush  [A]", self)
        act_tool_select.setStatusTip("Brush-based selection for polygon editing (tile view only)")
        act_tool_select.triggered.connect(lambda: self._activate_tool("brush_select"))
        tools_menu.addAction(act_tool_select)

        tools_menu.addSeparator()

        act_run_seg = QAction("Run Selected Slices", self)
        act_run_seg.setShortcut(QKeySequence("F5"))
        act_run_seg.setStatusTip("Run the selected batch model on checked slices")
        act_run_seg.triggered.connect(self._run_selected_slices)
        tools_menu.addAction(act_run_seg)

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
        _canvas_sc("G", lambda: self._activate_tool("grid"))
        _canvas_sc("B", lambda: self._activate_tool("brush"))

        # Tile-mode tools
        _canvas_sc("S", lambda: self._activate_tool("segment"))
        _canvas_sc("E", lambda: self._activate_tool("brush_eraser"))
        _canvas_sc("A", lambda: self._activate_tool("brush_select"))

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
            if self._central_stack.currentIndex() == self.PAGE_TILE:
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
            if self._central_stack.currentIndex() == self.PAGE_TILE:
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
        if self._central_stack.currentIndex() == self.PAGE_TILE:
            idx = self.tile_renderer.slice_idx
            if idx is not None and idx < len(s.tiles):
                self.undo_manager.push(s, "clear")
                s.tiles[idx].segmentation_layers.clear()
                self.tile_renderer.viewport().update()
                self.statusBar().showMessage("Polygons cleared")
        else:
            self.statusBar().showMessage("Enter a tile to clear its polygons")

    def _active_renderer(self):
        return self.tile_renderer if self._central_stack.currentIndex() == self.PAGE_TILE else self.canvas_renderer

    def _sb_refresh(self) -> None:
        """Refresh permanent status bar indicators from current app state."""
        zoom = getattr(self._active_renderer(), "viewport_zoom", None)
        self._sb_zoom.setText(f"Zoom: {zoom * 100:.0f}%" if zoom is not None else "Zoom: —")

        tool = getattr(self, "active_tool", None)
        self._sb_tool.setText(f"Tool: {tool}" if tool else "Tool: —")

        if self._central_stack.currentIndex() == self.PAGE_TILE and self.current_session:
            idx = getattr(self.tile_renderer, "slice_idx", None)
            if idx is not None and idx < len(self.current_session.tiles):
                tile = self.current_session.tiles[idx]
                count = sum(
                    len(layer.get("polygons", []))
                    for layer in tile.segmentation_layers
                    if layer.get("visible", True)
                )
                self._sb_nuclei.setText(f"Nuclei: {count:,}")
                self._update_context_bar()
                return
        self._sb_nuclei.setText("Nuclei: —")
        self._update_context_bar()

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
        if self._central_stack.currentIndex() == self.PAGE_TILE:
            self.switch_to_canvas()

    # ── Topbar: tool pill, breadcrumb, overflow ──────────────────────────────

    _TOOL_LABELS = {
        "grid":         "Grid  ▾",
        "brush":        "Brush  ▾",
        "segment":      "Segment  ▾",
        "brush_eraser": "Eraser  ▾",
        "brush_select": "Select  ▾",
    }

    def _update_tool_pill(self):
        self.btn_tool_pill.setText(self._TOOL_LABELS.get(self.active_tool, "Tool  ▾"))

    def _update_breadcrumb(self):
        s = self.current_session
        if not s:
            self.lbl_breadcrumb.setText("No project open")
            return
        if self._central_stack.currentIndex() == self.PAGE_TILE:
            idx = getattr(self.tile_renderer, "slice_idx", None)
            if idx is not None and s and idx < len(s.tiles):
                custom = s.tiles[idx].metadata.get("name", "")
                tile_label = custom if custom else f"Tile {idx + 1}"
            else:
                tile_label = "Tile"
            self.lbl_breadcrumb.setText(f"{s.name}  ›  {tile_label}")
        else:
            self.lbl_breadcrumb.setText(s.name)

    def _on_mpp_edit_requested(self) -> None:
        """Handle click on the µm/px badge in the context bar."""
        s = self.current_session
        if not s:
            return

        current = getattr(s, "microns_per_pixel", "") or ""
        text, ok = QInputDialog.getText(
            self,
            "Physical Resolution",
            "Enter the pixel size in microns (µm/px).\n\n"
            "This is a property of the whole slide image — it is\n"
            "stored in the HDF5 file (pixel_size_um) and enables\n"
            "the nucleus area quality filter (min 5 µm²).\n\n"
            "Example: 0.2420 for a 40× Aperio scanner.",
            text=current,
        )
        if not ok or not text.strip():
            return

        try:
            v = float(text.strip())
            if v <= 0:
                raise ValueError
        except (ValueError, TypeError):
            QMessageBox.warning(
                self, "Invalid Value",
                f'"{text.strip()}" is not a valid positive number.'
            )
            return

        s.set_microns_per_pixel(str(v))
        self.context_bar.refresh_mpp(s)
        self.statusBar().showMessage(f"Resolution set: {v:g} µm/px", 3000)

    def _show_tool_menu(self):
        """Drop-down showing only the tools valid in the current mode."""
        menu = QMenu(self)
        is_isolated = self._central_stack.currentIndex() == self.PAGE_TILE

        if not is_isolated:
            tools = [("Grid  [G]", "grid"), ("Brush  [B]", "brush")]
        else:
            tools = [
                ("Segment  [S]", "segment"),
                ("Eraser  [E]",  "brush_eraser"),
                ("Select  [A]",  "brush_select"),
            ]

        for label, tool_name in tools:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.active_tool == tool_name)
            act.triggered.connect(lambda _checked, t=tool_name: self._activate_tool(t))

        menu.exec(self.btn_tool_pill.mapToGlobal(
            QPoint(0, self.btn_tool_pill.height())
        ))

    def _show_grid_settings_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Grid Settings")
        dlg.setFixedWidth(220)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        form = QFormLayout()
        spin_w = QSpinBox()
        spin_w.setRange(32, 8192)
        spin_w.setValue(self.project_manager.get_grid_w())
        spin_w.setSuffix(" px")

        spin_h = QSpinBox()
        spin_h.setRange(32, 8192)
        spin_h.setValue(self.project_manager.get_grid_h())
        spin_h.setSuffix(" px")

        form.addRow("Width:", spin_w)
        form.addRow("Height:", spin_h)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec():
            self.project_manager.set_grid(spin_w.value(), spin_h.value())

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
            ("Run Selected Slices","F5"),
            ("Export HDF5",        "Ctrl+E"),
            ("── View", ""),
            ("Zoom In",            "="),
            ("Zoom Out",           "-"),
            ("Zoom to Fit",        "Ctrl+0"),
            ("Collapse/Expand Slices", "Ctrl+B"),
            ("Toggle Properties",  "Ctrl+P"),
            ("Toggle Pipeline",    "Ctrl+M"),
            ("Back to Canvas",     "Escape"),
            ("Keyboard Shortcuts", "F1"),
            ("── Mouse", ""),
            ("Pan",                "Left-click drag"),
            ("Zoom",               "Ctrl + Scroll"),
            ("Click Segment",      "Right-click (tile view)"),
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
            "PyQt6 &nbsp;·&nbsp; Cellpose &nbsp;·&nbsp; NuClick &nbsp;·&nbsp; iDISF"
            " &nbsp;·&nbsp; OpenSlide &nbsp;·&nbsp; pyvips"
        )
