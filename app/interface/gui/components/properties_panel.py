import logging
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QFormLayout, QLineEdit, QLabel,
    QVBoxLayout, QHBoxLayout, QScrollArea, QSlider, QGroupBox, QFrame,
    QDoubleSpinBox, QSpinBox, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
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
        self.container.setMinimumWidth(0)
        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setContentsMargins(SPACE[3], SPACE[3], SPACE[3], SPACE[3])
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
        self.form_layout.setSpacing(SPACE[2])
        self.form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Inputs
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Enter tile name...")
        self.input_name.setMinimumWidth(0)
        self.input_name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.form_layout.addRow("Name:", self.input_name)

        self.main_layout.addLayout(self.form_layout)

        # ── Segmentation Summary Section ─────────────────────────────────────
        self.lbl_seg_summary = SectionHeader("Segmentation Dashboard")
        self.main_layout.addWidget(self.lbl_seg_summary)

        self._seg_summary_body = QWidget()
        self._seg_summary_layout = QVBoxLayout(self._seg_summary_body)
        self._seg_summary_layout.setContentsMargins(0, 0, 0, 0)
        self._seg_summary_layout.setSpacing(SPACE[2])
        self.main_layout.addWidget(self._seg_summary_body)

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
        self.slider_brush_size.setMinimumWidth(40)

        self.spin_brush_size = QSpinBox()
        self.spin_brush_size.setRange(1, 500)
        self.spin_brush_size.setValue(10)
        self.spin_brush_size.setSuffix(" px")
        self.spin_brush_size.setFixedWidth(48)
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
        layer_dropdown.setMinimumWidth(0)
        layer_dropdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(layer_dropdown)

        hint = QLabel("Run a segmentation model to create layers.")
        hint.setStyleSheet(
            f"color: {COLORS['text_disabled']}; font-size: 11px; font-style: italic;"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.main_layout.insertWidget(3, self._overlay_group)

    def load_tile(self, tile):
        """Populate the panel with a specific Tile's metadata block and enable edits."""
        self._current_tile = None  # unbind temporarily to prevent auto-save triggering on load

        meta = tile.metadata
        self.input_name.setText(meta.get("name") or self._fallback_tile_name(tile))

        self._empty_lbl.setVisible(False)
        self.container.setEnabled(True)
        self._current_tile = tile
        self.refresh_segmentation_summary()

    def clear(self):
        """Clear fields and disable panel when no tile is selected."""
        self._current_tile = None
        self.input_name.clear()
        self._clear_segmentation_summary()
        self._empty_lbl.setVisible(True)
        self.container.setEnabled(False)

    def refresh_segmentation_summary(self) -> None:
        self._clear_segmentation_summary()
        tile = self._current_tile
        if tile is None:
            return

        layers = tile.segmentation_layers
        if not layers:
            empty = QLabel("No segmentation layers yet.")
            empty.setStyleSheet(
                f"color: {COLORS['text_disabled']}; font-size: 11px; font-style: italic;"
                " background: transparent;"
            )
            self._seg_summary_layout.addWidget(empty)
            return

        for layer in layers:
            self._seg_summary_layout.addWidget(self._make_segmentation_row(layer))

    def _clear_segmentation_summary(self) -> None:
        while self._seg_summary_layout.count():
            item = self._seg_summary_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _make_segmentation_row(self, layer: dict) -> QWidget:
        row = QFrame()
        row.setObjectName("seg_summary_row")
        row.setStyleSheet(
            f"QFrame#seg_summary_row {{ background: {COLORS['bg_surface']};"
            f" border: 1px solid {COLORS['border_default']}; border-radius: 6px; }}"
        )

        layout = QHBoxLayout(row)
        layout.setContentsMargins(SPACE[2], SPACE[2], SPACE[2], SPACE[2])
        layout.setSpacing(SPACE[2])

        marker = QLabel()
        color = layer.get("color", COLORS["brand"])
        marker.setFixedSize(9, 9)
        marker.setStyleSheet(
            f"background: {color}; border-radius: 3px;"
            " border: 1px solid rgba(255,255,255,0.25);"
        )
        layout.addWidget(marker, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        name = QLabel(layer.get("name") or layer.get("model") or "Segmentation")
        name.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        name.setToolTip(name.text())
        name.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 12px; font-weight: 600;"
            " background: transparent;"
        )
        text_col.addWidget(name)

        model = layer.get("model_name") or layer.get("model")
        model_text = f"model: {model}" if model else "model: unknown"
        model_lbl = QLabel(model_text)
        model_lbl.setToolTip(model_text)
        model_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; background: transparent;"
        )
        text_col.addWidget(model_lbl)
        layout.addLayout(text_col, stretch=1)

        stats_col = QVBoxLayout()
        stats_col.setContentsMargins(0, 0, 0, 0)
        stats_col.setSpacing(1)

        count = len(layer.get("polygons", []))
        cells = QLabel(f"{count:,} cells")
        cells.setToolTip(cells.text())
        cells.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 11px; background: transparent;"
        )
        cells.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        stats_col.addWidget(cells)

        elapsed = layer.get("execution_time_s")
        time_text = "—" if elapsed is None else f"{float(elapsed):.2f}s"
        timing = QLabel(time_text)
        timing.setToolTip(time_text)
        timing.setMinimumWidth(0)
        timing.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        timing.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; background: transparent;"
        )
        stats_col.addWidget(timing)

        vram_free = layer.get("vram_free_gb_start")
        device_id = layer.get("vram_device_id")
        if vram_free is None:
            vram_text = "VRAM —"
        else:
            gpu_prefix = f"GPU {device_id} · " if device_id is not None else ""
            vram_text = f"{gpu_prefix}{float(vram_free):.2f} GB free"
        vram = QLabel(vram_text)
        vram.setToolTip(vram_text)
        vram.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        vram.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; background: transparent;"
        )
        stats_col.addWidget(vram)
        layout.addLayout(stats_col)
        row.resizeEvent = lambda event, row=row, name=name, model_lbl=model_lbl, cells=cells, timing=timing, vram=vram: self._fit_segmentation_row_text(
            row, name, model_lbl, cells, timing, vram
        )
        return row

    def _fit_segmentation_row_text(self, row, name_lbl, model_lbl, cells_lbl, timing_lbl, vram_lbl) -> None:
        width = max(row.width(), 1)
        compact = width < 230
        name_width = max(44, width - (86 if compact else 128))
        stats_width = 42 if compact else 78

        name_full = name_lbl.toolTip() or name_lbl.text()
        model_full = model_lbl.toolTip() or model_lbl.text()
        cells_full = cells_lbl.toolTip() or cells_lbl.text()
        timing_full = timing_lbl.toolTip() or timing_lbl.text()
        vram_full = vram_lbl.toolTip() or vram_lbl.text()

        fm_name = QFontMetrics(name_lbl.font())
        fm_small = QFontMetrics(model_lbl.font())
        name_lbl.setText(fm_name.elidedText(name_full, Qt.TextElideMode.ElideRight, name_width))
        model_lbl.setText(fm_small.elidedText(model_full, Qt.TextElideMode.ElideRight, name_width))
        cells_lbl.setToolTip(cells_full)
        timing_lbl.setToolTip(timing_full)
        vram_lbl.setToolTip(vram_full)
        cells_lbl.setText(fm_small.elidedText(cells_full, Qt.TextElideMode.ElideRight, stats_width))
        timing_lbl.setText(fm_small.elidedText(timing_full, Qt.TextElideMode.ElideRight, stats_width))
        vram_lbl.setText(fm_small.elidedText(vram_full, Qt.TextElideMode.ElideRight, stats_width))

    def _save_metadata(self):
        """Auto-save changes to the currently bound Tile entity."""
        if self._current_tile is None:
            return

        m = self._current_tile.metadata
        m["name"] = self.input_name.text()

    def _fallback_tile_name(self, tile) -> str:
        session = getattr(self._main_window, "current_session", None)
        if session is not None:
            try:
                return f"Slice {session.tiles.index(tile) + 1}"
            except ValueError:
                pass
        return "Slice"
