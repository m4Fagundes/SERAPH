import logging
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QFormLayout, QLineEdit, QTextEdit, QLabel,
    QVBoxLayout, QHBoxLayout, QScrollArea, QSlider, QGroupBox,
    QDoubleSpinBox, QSpinBox
)
from PyQt6.QtCore import Qt
from app.interface.gui.theme import PALETTE
from app.interface.gui.design_system import COLORS, SPACE, SIZE
from app.interface.gui.widgets.section_header import SectionHeader

logger = logging.getLogger(__name__)


class PropertiesPanel(QDockWidget):
    """
    Persistent sidebar for viewing and editing Tile metadata.
    Automatically syncs changes back to the underlying Tile domain entity.
    """
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self._main_window = parent
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures | QDockWidget.DockWidgetFeature.DockWidgetMovable)

        self._current_tile = None

        # Create a scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Inner container for the scroll area
        self.container = QWidget()
        self.container.setObjectName("ScrollContent")
        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setContentsMargins(SPACE[4], SPACE[4], SPACE[4], SPACE[4])
        self.main_layout.setSpacing(SPACE[3])

        # Title section header
        self.lbl_title = SectionHeader("Tile Metadata")
        self.main_layout.addWidget(self.lbl_title)

        # ── Empty state placeholder ────────────────────────────────────────────
        self._empty_lbl = QLabel("Select a slice from the\nleft panel to view properties.")
        self._empty_lbl.setStyleSheet(
            f"color: {COLORS['text_disabled']}; font-size: 11px; font-style: italic;"
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setVisible(True)
        self.main_layout.addWidget(self._empty_lbl)

        # Form Layout for inputs
        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(10)

        # Inputs
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Enter tile name...")

        self.input_desc = QTextEdit()
        self.input_desc.setMaximumHeight(80)
        self.input_desc.setPlaceholderText("Detailed description of this slice...")

        self.input_comment = QTextEdit()
        self.input_comment.setMaximumHeight(80)
        self.input_comment.setPlaceholderText("Any additional comments...")

        self.form_layout.addRow("Name:", self.input_name)
        self.form_layout.addRow("Description:", self.input_desc)
        self.form_layout.addRow("Comment:", self.input_comment)

        self.main_layout.addLayout(self.form_layout)

        # ── Brush Settings Section ─────────────────────────────────────────────
        self.lbl_brush_title = SectionHeader("Brush Settings")
        self.main_layout.addWidget(self.lbl_brush_title)

        self.brush_layout = QVBoxLayout()
        self.brush_layout.setContentsMargins(0, 0, 0, 0)
        self.brush_layout.setSpacing(5)

        # Horizontal row: slider (stretch) + spinbox (fixed 60px)
        self._brush_row = QHBoxLayout()
        self._brush_row.setSpacing(8)

        self.slider_brush_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_brush_size.setRange(1, 500)
        self.slider_brush_size.setValue(10)
        self.slider_brush_size.setCursor(Qt.CursorShape.PointingHandCursor)

        self.spin_brush_size = QSpinBox()
        self.spin_brush_size.setRange(1, 500)
        self.spin_brush_size.setValue(10)
        self.spin_brush_size.setSuffix(" px")
        self.spin_brush_size.setFixedWidth(60)
        self.spin_brush_size.setFixedHeight(SIZE["md"])
        self.spin_brush_size.setCursor(Qt.CursorShape.PointingHandCursor)

        # Bidirectional sync
        self.slider_brush_size.valueChanged.connect(self.spin_brush_size.setValue)
        self.spin_brush_size.valueChanged.connect(self.slider_brush_size.setValue)

        self._brush_row.addWidget(self.slider_brush_size, stretch=1)
        self._brush_row.addWidget(self.spin_brush_size)

        self.brush_layout.addLayout(self._brush_row)
        self.main_layout.addLayout(self.brush_layout)

        # Stretch spacer at the bottom to force everything to align to the TOP
        self.main_layout.addStretch(1)

        self.scroll_area.setWidget(self.container)
        self.setWidget(self.scroll_area)

        # Connect signals for auto-save
        self.input_name.textChanged.connect(self._save_metadata)
        self.input_desc.textChanged.connect(self._save_metadata)
        self.input_comment.textChanged.connect(self._save_metadata)

        self.clear()  # Start disabled and clear

    @property
    def brush_size(self) -> int:
        return self.slider_brush_size.value()

    def setup_cellpose_params(self, spin_diameter, spin_flow, spin_cellprob):
        """Inject the Cellpose parameter spinboxes from main_window into a panel section.

        Called once after PropertiesPanel is created. The spinboxes are owned by
        main_window so their values are accessible from batch segmentation flows.
        """
        self._cellpose_group = QGroupBox("SEGMENTATION PARAMETERS")

        form = QFormLayout(self._cellpose_group)
        form.setContentsMargins(8, 12, 8, 8)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        lbl_d = QLabel("⌀ Diameter")
        lbl_d.setToolTip("Expected nucleus diameter in pixels. 0 = auto-detect (shows 'Auto').")
        form.addRow(lbl_d, spin_diameter)

        lbl_f = QLabel("Flow Thr.")
        lbl_f.setToolTip("Flow error threshold: lower = stricter mask quality (0.0–1.0)")
        form.addRow(lbl_f, spin_flow)

        lbl_c = QLabel("Cell Prob.")
        lbl_c.setToolTip("Cell probability threshold: lower = more detections (−6 to +6)")
        form.addRow(lbl_c, spin_cellprob)

        # Insert before the stretch at the bottom
        self._cellpose_group.setVisible(False)
        # Remove the trailing stretch, insert group, re-add stretch
        count = self.main_layout.count()
        stretch_item = self.main_layout.takeAt(count - 1)
        self.main_layout.addWidget(self._cellpose_group)
        self.main_layout.addStretch(1)

    def show_cellpose_params(self, visible: bool):
        """Show or hide the Cellpose parameter section."""
        if hasattr(self, "_cellpose_group"):
            self._cellpose_group.setVisible(visible)

    def setup_overlay_controls(self, chk_show_membrane, layer_dropdown):
        """Inject the membrane toggle and layer dropdown into a panel section."""
        from PyQt6.QtWidgets import QGroupBox, QVBoxLayout
        self._overlay_group = QGroupBox("OVERLAY & LAYERS")
        layout = QVBoxLayout(self._overlay_group)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(chk_show_membrane)
        layout.addWidget(layer_dropdown)

        hint = QLabel("Run a segmentation model to create layers.")
        hint.setStyleSheet(
            f"color: {COLORS['text_disabled']}; font-size: 11px; font-style: italic;"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        count = self.main_layout.count()
        stretch_item = self.main_layout.takeAt(count - 1)
        self.main_layout.addWidget(self._overlay_group)
        self.main_layout.addStretch(1)

    def load_tile(self, tile):
        """Populate the panel with a specific Tile's metadata block and enable edits."""
        self._current_tile = None  # unbind temporarily to prevent auto-save triggering on load

        meta = tile.metadata
        self.input_name.setText(meta.get("name", ""))

        self.input_desc.setPlainText(meta.get("description", ""))
        self.input_comment.setPlainText(meta.get("comment", ""))

        self._empty_lbl.setVisible(False)
        self.container.setEnabled(True)
        self._current_tile = tile

    def clear(self):
        """Clear fields and disable panel when no tile is selected."""
        self._current_tile = None
        self.input_name.clear()
        self.input_desc.clear()
        self.input_comment.clear()
        self._empty_lbl.setVisible(True)
        self.container.setEnabled(False)

    def _save_metadata(self):
        """Auto-save changes to the currently bound Tile entity."""
        if self._current_tile is None:
            return

        m = self._current_tile.metadata
        m["name"] = self.input_name.text()
        m["description"] = self.input_desc.toPlainText()
        m["comment"] = self.input_comment.toPlainText()
