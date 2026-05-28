import logging
import time
from typing import List, Optional, Tuple
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QCheckBox, QDialog,
    QDialogButtonBox, QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QBrush, QColor, QCursor

from app.domain.geometry import get_polygon_centroid
from app.interface.gui.theme import PALETTE, label_timer
from app.interface.gui.design_system import COLORS, SPACE, SIZE, RADIUS
from app.interface.gui.widgets.buttons import ActionButton, SecondaryButton

logger = logging.getLogger(__name__)

# ── Model registry ────────────────────────────────────────────────────────────

_KNOWN_MODELS = [
    ("Cellpose (cpsam)",   "#FF00FF"),
    ("NuClick (PyTorch)",  "#00E5FF"),
    ("CellViT-SAM",        "#00E5FF"),
    ("PathoSAM (ViT-B)",   "#50C878"),
    ("DINOSim (small)",    "#FFD700"),
]

def _layer_name(model_name: str) -> str:
    short = model_name.split(" ")[0]
    return f"Macro {short}"


# ── DINOSim reference-point dialog ───────────────────────────────────────────

def _pil_to_pixmap(pil_img) -> QPixmap:
    """Convert a PIL Image (RGB) to a QPixmap without external dependencies."""
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    data = pil_img.tobytes("raw", "RGB")
    qimg = QImage(data, pil_img.width, pil_img.height,
                  pil_img.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


class _ClickableImageLabel(QLabel):
    """QLabel that emits (x, y) in display coords on left-click."""
    clicked = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(int(event.position().x()), int(event.position().y()))
        super().mousePressEvent(event)


class DINOSimReferenceDialog(QDialog):
    """
    Dialog for picking reference nuclei on the current tile.

    The user clicks on representative nuclei; each click is recorded as a
    reference point. Accepts and returns the selected coordinates in original
    tile pixel space.

    Usage:
        dlg = DINOSimReferenceDialog(tile_pil_image, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            coords = dlg.reference_coords   # List[Tuple[int, int]] in tile pixels
    """

    # Max display dimension (longest side) — keeps the dialog manageable
    _MAX_DISPLAY_PX = 640

    def __init__(self, tile_image, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DINOSim — Set Reference Points")
        self.setModal(True)
        self.setMinimumWidth(500)

        self._tile_image = tile_image
        self._display_scale: float = 1.0
        self._base_pixmap: Optional[QPixmap] = None
        self._coords: List[Tuple[int, int]] = []  # in original tile space

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACE[3])

        # ── Instruction text ──────────────────────────────────────────────────
        instr = QLabel(
            "Click on representative nuclei below.\n"
            "DINOSim will find visually similar cells across all tiles."
        )
        instr.setWordWrap(True)
        instr.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        layout.addWidget(instr)

        # ── Point counter ─────────────────────────────────────────────────────
        self._lbl_count = QLabel("0 points selected")
        self._lbl_count.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 12px; font-weight: 600;"
        )
        layout.addWidget(self._lbl_count)

        # ── Tile image ────────────────────────────────────────────────────────
        self._img_label = _ClickableImageLabel()
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.clicked.connect(self._on_image_click)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setWidget(self._img_label)
        scroll.setMinimumHeight(300)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(scroll, stretch=1)

        self._load_tile_image()

        # ── Clear button ──────────────────────────────────────────────────────
        btn_clear = SecondaryButton("Clear All Points")
        btn_clear.clicked.connect(self._clear_points)
        layout.addWidget(btn_clear)

        # ── OK / Cancel ───────────────────────────────────────────────────────
        self._btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._btn_box.accepted.connect(self.accept)
        self._btn_box.rejected.connect(self.reject)
        self._btn_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout.addWidget(self._btn_box)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def reference_coords(self) -> List[Tuple[int, int]]:
        """Selected (x, y) coordinates in original tile pixel space."""
        return list(self._coords)

    # ── Image loading ─────────────────────────────────────────────────────────

    def _load_tile_image(self) -> None:
        try:
            w, h = self._tile_image.size
            scale = min(self._MAX_DISPLAY_PX / w, self._MAX_DISPLAY_PX / h, 1.0)
            self._display_scale = scale
            disp_w, disp_h = int(w * scale), int(h * scale)

            resized = self._tile_image.resize((disp_w, disp_h))
            self._base_pixmap = _pil_to_pixmap(resized)
            self._img_label.setFixedSize(disp_w, disp_h)
            self._img_label.setPixmap(self._base_pixmap.copy())
        except Exception as exc:
            logger.error("DINOSimReferenceDialog: failed to load tile image: %s", exc)
            self._img_label.setText("(failed to load tile image)")

    # ── Point management ─────────────────────────────────────────────────────

    def _on_image_click(self, disp_x: int, disp_y: int) -> None:
        orig_x = int(disp_x / self._display_scale)
        orig_y = int(disp_y / self._display_scale)
        self._coords.append((orig_x, orig_y))
        self._redraw_points()
        self._update_count()

    def _clear_points(self) -> None:
        self._coords.clear()
        if self._base_pixmap:
            self._img_label.setPixmap(self._base_pixmap.copy())
        self._update_count()

    def _update_count(self) -> None:
        n = len(self._coords)
        self._lbl_count.setText(f"{n} point{'s' if n != 1 else ''} selected")
        ok_btn = self._btn_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setEnabled(n > 0)

    def _redraw_points(self) -> None:
        if self._base_pixmap is None:
            return
        pixmap = self._base_pixmap.copy()
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dot_r = max(5, int(8 * self._display_scale))
        for i, (ox, oy) in enumerate(self._coords):
            dx = int(ox * self._display_scale)
            dy = int(oy * self._display_scale)
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.setBrush(QBrush(QColor(255, 220, 0, 200)))
            painter.drawEllipse(QPoint(dx, dy), dot_r, dot_r)
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(QPoint(dx + dot_r + 2, dy + 4), str(i + 1))
        painter.end()
        self._img_label.setPixmap(pixmap)


# ── Workers ───────────────────────────────────────────────────────────────────

class MacroPipelineWorker(QThread):
    progress = pyqtSignal(int, int, str)   # current, total, status_text
    time_update = pyqtSignal(str, float)   # phase, elapsed_time
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, session, batch_service, interactive_service,
                 cellpose_model, nuclick_model, cellpose_params, run_nuclick=True,
                 slice_indices: Optional[list[int]] = None):
        super().__init__()
        self.session = session
        self.batch_service = batch_service
        self.interactive_service = interactive_service
        self.cellpose_model = cellpose_model
        self.nuclick_model = nuclick_model
        self.cellpose_params = cellpose_params
        self.run_nuclick = run_nuclick
        self.slice_indices = list(slice_indices) if slice_indices is not None else list(range(len(session.tiles)))

        self.is_paused = False
        self.is_cancelled = False

        self.current_phase = 1
        self.current_slice_pos = 0

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            total_slices = len(self.slice_indices)
            if total_slices == 0:
                self.finished.emit()
                return

            # PHASE 1: Cellpose
            if self.current_phase == 1:
                start_time = time.monotonic()
                for pos in range(self.current_slice_pos, total_slices):
                    while self.is_paused and not self.is_cancelled:
                        time.sleep(0.1)
                    if self.is_cancelled:
                        return

                    i = self.slice_indices[pos]
                    self.progress.emit(pos + 1, total_slices, f"Cellpose: Slice {i+1} ({pos+1}/{total_slices})…")

                    polys = self.batch_service.segment_tile(
                        self.cellpose_model, self.session, i,
                        **self.cellpose_params
                    )

                    if polys:
                        layer_idx = self.session.tiles[i].add_layer("Macro Cellpose", self.cellpose_model, polys, "#FF00FF")
                        prob = self.batch_service.probability_map()
                        if prob is not None:
                            self.session.tiles[i].segmentation_layers[layer_idx]["probability_map"] = prob

                    self.current_slice_pos = pos + 1

                elapsed = time.monotonic() - start_time
                self.time_update.emit("Cellpose", elapsed)
                self.current_slice_pos = 0

                if self.run_nuclick:
                    self.current_phase = 2
                else:
                    self.finished.emit()
                    return

            # PHASE 2: NuClick — seeds from Cellpose centroids
            if self.current_phase == 2 and self.run_nuclick:
                start_time = time.monotonic()
                for pos in range(self.current_slice_pos, total_slices):
                    while self.is_paused and not self.is_cancelled:
                        time.sleep(0.1)
                    if self.is_cancelled:
                        return

                    i = self.slice_indices[pos]
                    self.progress.emit(pos + 1, total_slices, f"NuClick: Slice {i+1} ({pos+1}/{total_slices})…")

                    tile = self.session.tiles[i]
                    centroids = []
                    for layer in tile.segmentation_layers:
                        if layer.get("name") == "Macro Cellpose":
                            for poly in layer.get("polygons", []):
                                centroids.append(get_polygon_centroid(poly))

                    if centroids:
                        nuclick_polys = self.interactive_service.segment_at_points(
                            self.nuclick_model, self.session, i, centroids
                        )
                        if nuclick_polys:
                            tile.add_layer("Macro NuClick", self.nuclick_model, nuclick_polys, "#00E5FF")

                    self.current_slice_pos = pos + 1

                elapsed = time.monotonic() - start_time
                self.time_update.emit("NuClick", elapsed)

            self.finished.emit()

        except Exception as e:
            logger.exception("Error in MacroPipelineWorker: %s", e)
            self.error.emit(str(e))


class SingleModelWorker(QThread):
    """Runs a single batch model across selected tiles."""
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(float)           # elapsed seconds
    error = pyqtSignal(str)

    def __init__(self, session, batch_service, model_name: str, params: dict,
                 layer_name: str, layer_color: str, slice_indices: Optional[list[int]] = None):
        super().__init__()
        self.session = session
        self.batch_service = batch_service
        self.model_name = model_name
        self.params = params
        self.layer_name = layer_name
        self.layer_color = layer_color
        self.slice_indices = list(slice_indices) if slice_indices is not None else list(range(len(session.tiles)))
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            total_slices = len(self.slice_indices)
            if total_slices == 0:
                self.finished.emit(0.0)
                return

            start_time = time.monotonic()
            for pos, i in enumerate(self.slice_indices):
                if self.is_cancelled:
                    return

                self.progress.emit(
                    pos + 1, total_slices,
                    f"{self.model_name}: Slice {i+1} ({pos+1}/{total_slices})…"
                )

                polys = self.batch_service.segment_tile(
                    self.model_name, self.session, i, **self.params
                )

                if polys:
                    layer_idx = self.session.tiles[i].add_layer(
                        self.layer_name, self.model_name, polys, self.layer_color
                    )
                    prob = self.batch_service.probability_map()
                    if prob is not None:
                        self.session.tiles[i].segmentation_layers[layer_idx]["probability_map"] = prob

            elapsed = time.monotonic() - start_time
            self.finished.emit(elapsed)

        except Exception as e:
            logger.exception("Error in SingleModelWorker (%s): %s", self.model_name, e)
            self.error.emit(str(e))


class DINOSimCellposeReferenceWorker(QThread):
    """Build DINOSim reference points from Cellpose centroids on one tile."""
    reference_ready = pyqtSignal(int, int, float)  # point_count, cellpose_polygon_count, elapsed seconds
    error = pyqtSignal(str)
    MAX_REFERENCE_POINTS = 48

    def __init__(self, batch_service, dinosim_model: str, cellpose_model: str,
                 tile_image, params: dict):
        super().__init__()
        self.batch_service = batch_service
        self.dinosim_model = dinosim_model
        self.cellpose_model = cellpose_model
        self.tile_image = tile_image
        self.params = params

    def run(self):
        try:
            start_time = time.monotonic()
            cellpose_polys = self.batch_service.segment(
                self.cellpose_model,
                self.tile_image,
                **self.params,
            )
            selected_polys = self._select_reference_polygons(cellpose_polys)
            coords = [get_polygon_centroid(poly) for poly in selected_polys]
            if not coords:
                self.error.emit("Cellpose did not detect nuclei to use as DINOSim reference points.")
                return

            adapter = self.batch_service.get_model(self.dinosim_model)
            if adapter is None:
                self.error.emit("DINOSim adapter not registered.")
                return

            adapter.set_reference_points(coords, reference_image=self.tile_image)
            elapsed = time.monotonic() - start_time
            self.reference_ready.emit(len(coords), len(cellpose_polys), elapsed)
        except Exception as exc:
            logger.exception("DINOSim Cellpose reference failed: %s", exc)
            self.error.emit(str(exc))

    def _select_reference_polygons(self, polygons):
        """Keep representative Cellpose nuclei and drop tiny/huge artifacts."""
        from app.domain.geometry import polygon_area

        candidates = []
        for poly in polygons:
            if not poly or len(poly) < 3:
                continue
            area = float(polygon_area(poly))
            if area <= 0:
                continue
            candidates.append((area, poly))

        if not candidates:
            return []

        areas = sorted(area for area, _ in candidates)
        lo = areas[max(0, int(len(areas) * 0.10) - 1)]
        hi = areas[min(len(areas) - 1, int(len(areas) * 0.90))]
        filtered = [(area, poly) for area, poly in candidates if lo <= area <= hi]
        if not filtered:
            filtered = candidates

        median_area = areas[len(areas) // 2]
        filtered.sort(key=lambda item: abs(item[0] - median_area))
        return [poly for _, poly in filtered[: self.MAX_REFERENCE_POINTS]]


# ── Model card widget ──────────────────────────────────────────────────────────

class _ModelCard(QWidget):
    """
    Selectable radio card for a segmentation model.

    Visual state:
      - Unselected: bg_panel background, default border
      - Selected: bg_elevated background, 2px accent_action left border
    """

    def __init__(self, model_name: str, description: str, parent=None):
        super().__init__(parent)
        self.model_name = model_name
        self._selected = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(SIZE["lg"])  # 44px

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE[3], 0, SPACE[3], 0)
        layout.setSpacing(SPACE[2])

        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)

        self._name_lbl = QLabel(model_name)
        self._name_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600;"
            f" color: {COLORS['text_primary']}; background: transparent;"
        )

        self._desc_lbl = QLabel(description)
        self._desc_lbl.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']}; background: transparent;"
        )

        col.addStretch()
        col.addWidget(self._name_lbl)
        col.addWidget(self._desc_lbl)
        col.addStretch()
        layout.addLayout(col, stretch=1)

        self._refresh_style()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._refresh_style()

    def is_selected(self) -> bool:
        return self._selected

    def mousePressEvent(self, event) -> None:
        self.set_selected(True)
        super().mousePressEvent(event)

    def _refresh_style(self) -> None:
        if self._selected:
            self.setStyleSheet(
                f"background: {COLORS['bg_elevated']};"
                f" border-radius: {RADIUS['md']}px;"
                f" border-left: 2px solid {COLORS['accent_action']};"
            )
        else:
            self.setStyleSheet(
                f"background: {COLORS['bg_panel']};"
                f" border-radius: {RADIUS['md']}px;"
                f" border: 1px solid {COLORS['border_default']};"
            )


# ── Panel ─────────────────────────────────────────────────────────────────────

class MacroPipelinePanel(QDockWidget):
    """
    Unified segmentation dock.

    Model cards let the user pick which model to run.
    When Cellpose is selected, a checkbox appears offering to chain NuClick
    refinement after Cellpose (using Cellpose centroids as NuClick seed points).
    When DINOSim is selected, a reference-point section appears — the user must
    pick reference nuclei before running.
    All other models run as single independent passes.
    """

    _MODEL_DESCRIPTIONS = {
        "Cellpose (cpsam)":  "cpsam · CUDA",
        "NuClick (PyTorch)": "PyTorch",
        "CellViT-SAM":       "ViT-SAM",
        "PathoSAM (ViT-B)":  "SAM · histopathology",
        "DINOSim (small)":   "DINOv2 · zero-shot similarity",
    }

    _DINOSIM_NAME = "DINOSim (small)"

    def __init__(self, parent=None):
        super().__init__("Segmentation", parent)
        self.main_window = parent
        self.setFeatures(
            QDockWidget.DockWidgetFeature.NoDockWidgetFeatures |
            QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.worker: Optional[QThread] = None
        self._reference_worker: Optional[QThread] = None
        self._running = False

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(SPACE[3], SPACE[3], SPACE[3], SPACE[3])
        layout.setSpacing(SPACE[2])

        # ── Model cards ───────────────────────────────────────────────────────
        self._model_cards: list[_ModelCard] = []
        for model_name, color in _KNOWN_MODELS:
            desc = self._MODEL_DESCRIPTIONS.get(model_name, "")
            card = _ModelCard(model_name, desc)
            card.mousePressEvent = self._make_card_click(card)
            self._model_cards.append(card)
            layout.addWidget(card)

        layout.addSpacing(SPACE[1])

        # ── Chain option — only shown when Cellpose is selected ───────────────
        self.chk_chain = QCheckBox("Refine with NuClick after Cellpose")
        self.chk_chain.setChecked(True)
        self.chk_chain.setVisible(False)
        layout.addWidget(self.chk_chain)

        # ── DINOSim reference row — only shown when DINOSim is selected ───────
        self._dinosim_row = QWidget()
        self._dinosim_row.setStyleSheet(
            f"background: {COLORS['bg_panel']}; border-radius: {RADIUS['sm']}px;"
            f" border: 1px solid {COLORS['border_default']};"
        )
        dinosim_layout = QHBoxLayout(self._dinosim_row)
        dinosim_layout.setContentsMargins(SPACE[2], SPACE[2], SPACE[2], SPACE[2])
        dinosim_layout.setSpacing(SPACE[2])

        self._lbl_dinosim_ref = QLabel("○  No reference set")
        self._lbl_dinosim_ref.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; background: transparent; border: none;"
        )
        dinosim_layout.addWidget(self._lbl_dinosim_ref, stretch=1)

        self._btn_pick_ref = SecondaryButton("Pick Points")
        self._btn_pick_ref.setToolTip(
            "Click on representative nuclei in the current tile to define the reference."
        )
        self._btn_pick_ref.clicked.connect(self._pick_dinosim_reference)
        dinosim_layout.addWidget(self._btn_pick_ref)

        self._btn_cellpose_ref = SecondaryButton("Cellpose Points")
        self._btn_cellpose_ref.setToolTip(
            "Run Cellpose on the current tile and use one centroid per detected nucleus as DINOSim reference points."
        )
        self._btn_cellpose_ref.clicked.connect(self._pick_dinosim_reference_from_cellpose)
        dinosim_layout.addWidget(self._btn_cellpose_ref)

        self._dinosim_row.setVisible(False)
        layout.addWidget(self._dinosim_row)

        layout.addSpacing(SPACE[1])

        # ── Progress ──────────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Select slices and a model to run.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; background: transparent;"
        )
        layout.addWidget(self.lbl_status)

        # ── Timing labels (hidden until a phase completes) ────────────────────
        self.lbl_time_cellpose = QLabel("")
        self.lbl_time_cellpose.setStyleSheet(label_timer())
        self.lbl_time_cellpose.setVisible(False)
        layout.addWidget(self.lbl_time_cellpose)

        self.lbl_time_nuclick = QLabel("")
        self.lbl_time_nuclick.setStyleSheet(label_timer())
        self.lbl_time_nuclick.setVisible(False)
        layout.addWidget(self.lbl_time_nuclick)

        layout.addSpacing(SPACE[1])

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(SPACE[2])

        self.btn_run = ActionButton("Run selected", size="lg")
        self.btn_run.setEnabled(False)
        self.btn_run.setToolTip("Run selected model on checked slices")
        self.btn_run.clicked.connect(self._on_run_clicked)

        self.btn_cancel = SecondaryButton("Cancel")
        self.btn_cancel.setToolTip("Stop after current slice finishes")
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_cancel.setEnabled(False)

        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        layout.addStretch()
        self.setWidget(container)

    # ── Card interaction ──────────────────────────────────────────────────────

    def _make_card_click(self, clicked_card: "_ModelCard"):
        def handler(event):
            for card in self._model_cards:
                card.set_selected(card is clicked_card)

            is_cellpose = clicked_card.model_name == "Cellpose (cpsam)"
            is_dinosim  = clicked_card.model_name == self._DINOSIM_NAME

            self.chk_chain.setVisible(is_cellpose)
            self._dinosim_row.setVisible(is_dinosim)
            self._set_properties_params_visible(is_cellpose)

            if is_dinosim:
                self._refresh_dinosim_ref_status()
            self.refresh_selection_state()

            _ModelCard.mousePressEvent(clicked_card, event)
        return handler

    def _selected_model(self):
        """Return (model_name, color) of the selected card, or (None, None)."""
        for card, (name, color) in zip(self._model_cards, _KNOWN_MODELS):
            if card.is_selected():
                return name, color
        return None, None

    def _selected_slice_indices(self) -> list[int]:
        slice_previews = getattr(self.main_window, "slice_previews", None)
        if slice_previews is None or not hasattr(slice_previews, "selected_batch_indices"):
            return []
        return slice_previews.selected_batch_indices()

    def _set_properties_params_visible(self, visible: bool) -> None:
        panel = getattr(self.main_window, "properties_dock", None)
        if panel is not None and hasattr(panel, "show_cellpose_params"):
            panel.show_cellpose_params(visible)

    def refresh_selection_state(self) -> None:
        if self._running:
            return

        model_name, _ = self._selected_model()
        selected_count = len(self._selected_slice_indices())
        has_model = model_name is not None
        can_run = has_model and selected_count > 0

        if model_name == self._DINOSIM_NAME:
            can_run = can_run and self._dinosim_has_reference()

        self.btn_run.setEnabled(can_run)

        if selected_count == 0:
            self.lbl_status.setText("Check one or more slices to run batch segmentation.")
        elif not has_model:
            self.lbl_status.setText(f"{selected_count} slice{'s' if selected_count != 1 else ''} selected. Choose a model.")
        elif model_name == self._DINOSIM_NAME and not self._dinosim_has_reference():
            self.lbl_status.setText("Pick DINOSim reference points before running selected slices.")
        else:
            self.lbl_status.setText(
                f"Ready to run <b>{model_name}</b> on {selected_count} selected slice"
                f"{'s' if selected_count != 1 else ''}."
            )

    # ── DINOSim reference management ─────────────────────────────────────────

    def _dinosim_has_reference(self) -> bool:
        """True if the DINOSimAdapter already has reference vectors loaded."""
        svc = getattr(self.main_window, "batch_segmentation_service", None)
        if svc is None:
            return False
        adapter = svc.get_model(self._DINOSIM_NAME)
        return adapter is not None and getattr(adapter, "has_reference", False)

    def _refresh_dinosim_ref_status(self) -> None:
        if self._dinosim_has_reference():
            self._lbl_dinosim_ref.setText("●  Reference ready")
            self._lbl_dinosim_ref.setStyleSheet(
                f"color: {COLORS.get('accent_success', '#50C878')};"
                f" font-size: 11px; font-weight: 600; background: transparent; border: none;"
            )
            self._btn_pick_ref.setText("Change Points")
            self._btn_cellpose_ref.setText("Cellpose Points")
        else:
            self._lbl_dinosim_ref.setText("○  No reference set")
            self._lbl_dinosim_ref.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 11px; background: transparent; border: none;"
            )
            self._btn_pick_ref.setText("Pick Points")
            self._btn_cellpose_ref.setText("Cellpose Points")

    def _reference_tile_index(self) -> int:
        mw = self.main_window
        s = getattr(mw, "current_session", None)
        if s is None or not s.tiles:
            return 0

        idx = getattr(mw.canvas_renderer, "isolated_slice_idx", None)
        if idx is not None and 0 <= idx < len(s.tiles):
            return idx

        selected = self._selected_slice_indices()
        if selected:
            return selected[0]

        return 0

    def _load_reference_tile_image(self):
        mw = self.main_window
        s = getattr(mw, "current_session", None)
        if s is None or not s.tiles:
            raise RuntimeError("Open an image with slices first.")

        idx = self._reference_tile_index()
        tile = s.tiles[idx]
        bx1, by1, bx2, by2 = tile.bounding_box
        tile_pil = s.pyramid.get_region_fullres(bx1, by1, bx2 - bx1, by2 - by1)
        tile_pil = tile.get_ml_ready_image(tile_pil)
        return idx, tile_pil

    def _pick_dinosim_reference(self) -> None:
        """Open the reference-point dialog, then apply coords to the DINOSimAdapter."""
        mw = self.main_window
        s = getattr(mw, "current_session", None)
        if s is None or not s.tiles:
            self.lbl_status.setText("Open an image with slices first.")
            return

        try:
            idx, tile_pil = self._load_reference_tile_image()
        except Exception as exc:
            self.lbl_status.setText(f"Could not load tile image: {exc}")
            logger.error("DINOSim pick: failed to get tile image: %s", exc)
            return

        dlg = DINOSimReferenceDialog(tile_pil, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        coords = dlg.reference_coords
        if not coords:
            return

        svc = getattr(mw, "batch_segmentation_service", None)
        if svc is None:
            return
        adapter = svc.get_model(self._DINOSIM_NAME)
        if adapter is None:
            self.lbl_status.setText("DINOSim adapter not registered.")
            return

        self.lbl_status.setText("Computing DINOSim reference embeddings…")
        try:
            adapter.set_reference_points(coords, reference_image=tile_pil)
        except Exception as exc:
            self.lbl_status.setText(f"Reference failed: {exc}")
            logger.error("DINOSim set_reference_points error: %s", exc)
            return

        self._refresh_dinosim_ref_status()
        self.refresh_selection_state()
        n = len(coords)
        self.lbl_status.setText(
            f"DINOSim reference set from {n} point{'s' if n != 1 else ''} on tile {idx + 1}."
        )

    def _pick_dinosim_reference_from_cellpose(self) -> None:
        """Run Cellpose on the reference tile and use centroids as DINOSim prompts."""
        if self._reference_worker is not None:
            return

        mw = self.main_window
        svc = getattr(mw, "batch_segmentation_service", None)
        if svc is None:
            self.lbl_status.setText("Batch segmentation service unavailable.")
            return

        if svc.get_model(self._DINOSIM_NAME) is None:
            self.lbl_status.setText("DINOSim adapter not registered.")
            return
        if svc.get_model("Cellpose (cpsam)") is None:
            self.lbl_status.setText("Cellpose adapter not registered.")
            return

        try:
            idx, tile_pil = self._load_reference_tile_image()
        except Exception as exc:
            self.lbl_status.setText(f"Could not load tile image: {exc}")
            logger.error("DINOSim Cellpose reference: failed to get tile image: %s", exc)
            return

        self._reference_worker = DINOSimCellposeReferenceWorker(
            svc,
            self._DINOSIM_NAME,
            "Cellpose (cpsam)",
            tile_pil,
            self._build_params(),
        )
        self._reference_worker.reference_ready.connect(
            lambda point_count, poly_count, elapsed, tile_idx=idx:
                self._on_dinosim_cellpose_reference_ready(point_count, poly_count, elapsed, tile_idx)
        )
        self._reference_worker.error.connect(self._on_dinosim_cellpose_reference_error)
        self._reference_worker.finished.connect(self._on_dinosim_reference_thread_finished)

        self._btn_pick_ref.setEnabled(False)
        self._btn_cellpose_ref.setEnabled(False)
        self.lbl_status.setText(
            f"Running Cellpose to create DINOSim reference points on tile {idx + 1}…"
        )
        self._reference_worker.start()

    def _on_dinosim_cellpose_reference_ready(
        self,
        point_count: int,
        poly_count: int,
        elapsed: float,
        tile_idx: int,
    ) -> None:
        self._btn_pick_ref.setEnabled(True)
        self._btn_cellpose_ref.setEnabled(True)
        self._refresh_dinosim_ref_status()
        self.refresh_selection_state()
        self.lbl_status.setText(
            f"DINOSim reference set from {point_count} Cellpose centroid"
            f"{'s' if point_count != 1 else ''} on tile {tile_idx + 1} ({elapsed:.2f}s)."
        )

    def _on_dinosim_cellpose_reference_error(self, err_msg: str) -> None:
        self._btn_pick_ref.setEnabled(True)
        self._btn_cellpose_ref.setEnabled(True)
        self._refresh_dinosim_ref_status()
        self.refresh_selection_state()
        self.lbl_status.setText(f"Cellpose reference failed: {err_msg}")

    def _on_dinosim_reference_thread_finished(self) -> None:
        self._reference_worker = None

    # ── Run / Pause / Resume ──────────────────────────────────────────────────

    def _on_run_clicked(self) -> None:
        # Pause/Resume toggle for an active pipeline
        if self._running and isinstance(self.worker, MacroPipelineWorker):
            if self.worker.is_paused:
                self.worker.resume()
                self.btn_run.setText("Pause")
            else:
                self.worker.pause()
                self.btn_run.setText("Resume")
            return

        model_name, color = self._selected_model()
        if not model_name or self.worker is not None:
            return

        s = self.main_window.current_session
        if not s or not s.tiles:
            self.lbl_status.setText("No slices found in the project.")
            return

        selected_indices = self._selected_slice_indices()
        if not selected_indices:
            self.lbl_status.setText("Check one or more slices before running.")
            return

        # DINOSim guard — reference must be set before running
        if model_name == self._DINOSIM_NAME and not self._dinosim_has_reference():
            self.lbl_status.setText("Pick reference points first (use the button above).")
            return

        use_pipeline = (model_name == "Cellpose (cpsam)" and self.chk_chain.isChecked())
        if use_pipeline:
            self._start_pipeline(s, selected_indices)
        else:
            self._run_single_model(model_name, color, s, selected_indices)

    def _run_single_model(self, model_name: str, color: str, s, slice_indices: list[int]) -> None:
        params = self._build_params()
        self.worker = SingleModelWorker(
            s, self.main_window.batch_segmentation_service,
            model_name, params, _layer_name(model_name), color,
            slice_indices=slice_indices,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_single_finished)
        self.worker.error.connect(self._on_error)

        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"Running <b>{model_name}</b> on {len(slice_indices)} selected slices…")
        self._set_running(True, pipeline=False)
        self.worker.start()

    def _start_pipeline(self, s, slice_indices: list[int]) -> None:
        params = self._build_params()
        self.worker = MacroPipelineWorker(
            s,
            self.main_window.batch_segmentation_service,
            self.main_window.segmentation_service,
            "Cellpose (cpsam)",
            "NuClick (PyTorch)",
            params,
            run_nuclick=True,
            slice_indices=slice_indices,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.time_update.connect(self._on_time_update)
        self.worker.finished.connect(self._on_pipeline_finished)
        self.worker.error.connect(self._on_error)

        self.lbl_time_cellpose.setText("Cellpose: --")
        self.lbl_time_cellpose.setStyleSheet(label_timer())
        self.lbl_time_cellpose.setVisible(True)
        self.lbl_time_nuclick.setText("NuClick: --")
        self.lbl_time_nuclick.setStyleSheet(label_timer())
        self.lbl_time_nuclick.setVisible(True)

        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"Starting pipeline on {len(slice_indices)} selected slices…")
        self._set_running(True, pipeline=True)
        self.worker.start()

    # ── State management ──────────────────────────────────────────────────────

    def _set_running(self, running: bool, pipeline: bool = False) -> None:
        self._running = running
        if running:
            self.btn_run.setText("Pause" if pipeline else "Running…")
            self.btn_run.setEnabled(pipeline)  # only pipeline supports pause/resume
            self.btn_cancel.setEnabled(True)
            for card in self._model_cards:
                card.setEnabled(False)
            self._btn_pick_ref.setEnabled(False)
            self._btn_cellpose_ref.setEnabled(False)
        else:
            self.btn_run.setText("Run selected")
            self.btn_cancel.setEnabled(False)
            for card in self._model_cards:
                card.setEnabled(True)
            self._btn_pick_ref.setEnabled(True)
            self._btn_cellpose_ref.setEnabled(True)
            self.refresh_selection_state()

    def _cancel(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.worker.wait()
            self.worker = None
        self._set_running(False)
        self.lbl_status.setText("Cancelled.")
        self.progress_bar.setValue(0)

    # ── Worker callbacks ──────────────────────────────────────────────────────

    def _on_progress(self, current: int, total: int, text: str) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.lbl_status.setText(text)

    def _on_single_finished(self, elapsed: float) -> None:
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.lbl_status.setText(f"Done in {elapsed:.2f}s")
        self.worker = None
        self._set_running(False)
        self._refresh_views()

    def _on_pipeline_finished(self) -> None:
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.lbl_status.setText("Pipeline completed.")
        self.worker = None
        self._set_running(False)
        self._refresh_views()

    def _on_time_update(self, phase: str, elapsed: float) -> None:
        done_style = f"color: {PALETTE['exec_time_done']}; font-weight: bold;"
        if phase == "Cellpose":
            self.lbl_time_cellpose.setText(f"Cellpose: {elapsed:.2f}s")
            self.lbl_time_cellpose.setStyleSheet(done_style)
        elif phase == "NuClick":
            self.lbl_time_nuclick.setText(f"NuClick: {elapsed:.2f}s")
            self.lbl_time_nuclick.setStyleSheet(done_style)
        if hasattr(self.main_window, "layer_dropdown"):
            self.main_window.layer_dropdown.refresh()

    def _on_error(self, err_msg: str) -> None:
        self.lbl_status.setText(f"Error: {err_msg}")
        self.worker = None
        self._set_running(False)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_params(self) -> dict:
        mw = self.main_window
        diameter = mw.spin_diameter.value()
        return {
            "diameter": None if diameter == 0.0 else diameter,
            "flow_threshold": mw.spin_flow.value(),
            "cellprob_threshold": mw.spin_cellprob.value(),
        }

    def _refresh_views(self) -> None:
        if hasattr(self.main_window, "layer_dropdown"):
            self.main_window.layer_dropdown.refresh()
        if hasattr(self.main_window, "canvas_renderer"):
            self.main_window.canvas_renderer.redraw()
        if hasattr(self.main_window, "tile_renderer"):
            self.main_window.tile_renderer.viewport().update()
