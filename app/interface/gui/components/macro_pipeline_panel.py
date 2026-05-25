import logging
import time
from typing import Optional
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QCheckBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize

from app.domain.geometry import get_polygon_centroid
from app.interface.gui.theme import PALETTE, label_timer
from app.interface.gui.design_system import COLORS, SPACE, SIZE, RADIUS
from app.interface.gui.widgets.buttons import ActionButton, SecondaryButton

logger = logging.getLogger(__name__)

# ── Model registry ────────────────────────────────────────────────────────────

_KNOWN_MODELS = [
    ("Cellpose (cpsam)", "#FF00FF"),
    ("NuClick (PyTorch)", "#00E5FF"),
    ("CellViT-SAM",       "#00E5FF"),
]

def _layer_name(model_name: str) -> str:
    short = model_name.split(" ")[0]
    return f"Macro {short}"


# ── Workers ───────────────────────────────────────────────────────────────────

class MacroPipelineWorker(QThread):
    progress = pyqtSignal(int, int, str)   # current, total, status_text
    time_update = pyqtSignal(str, float)   # phase, elapsed_time
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, session, batch_service, interactive_service,
                 cellpose_model, nuclick_model, cellpose_params, run_nuclick=True):
        super().__init__()
        self.session = session
        self.batch_service = batch_service
        self.interactive_service = interactive_service
        self.cellpose_model = cellpose_model
        self.nuclick_model = nuclick_model
        self.cellpose_params = cellpose_params
        self.run_nuclick = run_nuclick

        self.is_paused = False
        self.is_cancelled = False

        self.current_phase = 1
        self.current_slice_idx = 0

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            total_slices = len(self.session.tiles)
            if total_slices == 0:
                self.finished.emit()
                return

            # PHASE 1: Cellpose
            if self.current_phase == 1:
                start_time = time.monotonic()
                for i in range(self.current_slice_idx, total_slices):
                    while self.is_paused and not self.is_cancelled:
                        time.sleep(0.1)
                    if self.is_cancelled:
                        return

                    self.progress.emit(i, total_slices, f"Cellpose: Slice {i+1}/{total_slices}…")

                    polys = self.batch_service.segment_tile(
                        self.cellpose_model, self.session, i,
                        **self.cellpose_params
                    )

                    if polys:
                        self.session.tiles[i].add_layer("Macro Cellpose", self.cellpose_model, polys, "#FF00FF")

                    self.current_slice_idx = i + 1

                elapsed = time.monotonic() - start_time
                self.time_update.emit("Cellpose", elapsed)
                self.current_slice_idx = 0

                if self.run_nuclick:
                    self.current_phase = 2
                else:
                    self.finished.emit()
                    return

            # PHASE 2: NuClick — seeds from Cellpose centroids
            if self.current_phase == 2 and self.run_nuclick:
                start_time = time.monotonic()
                for i in range(self.current_slice_idx, total_slices):
                    while self.is_paused and not self.is_cancelled:
                        time.sleep(0.1)
                    if self.is_cancelled:
                        return

                    self.progress.emit(i, total_slices, f"NuClick: Slice {i+1}/{total_slices}…")

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

                    self.current_slice_idx = i + 1

                elapsed = time.monotonic() - start_time
                self.time_update.emit("NuClick", elapsed)

            self.finished.emit()

        except Exception as e:
            logger.exception("Error in MacroPipelineWorker: %s", e)
            self.error.emit(str(e))


class SingleModelWorker(QThread):
    """Runs a single batch model across all tiles."""
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(float)           # elapsed seconds
    error = pyqtSignal(str)

    def __init__(self, session, batch_service, model_name: str, params: dict,
                 layer_name: str, layer_color: str):
        super().__init__()
        self.session = session
        self.batch_service = batch_service
        self.model_name = model_name
        self.params = params
        self.layer_name = layer_name
        self.layer_color = layer_color
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            total_slices = len(self.session.tiles)
            if total_slices == 0:
                self.finished.emit(0.0)
                return

            start_time = time.monotonic()
            for i in range(total_slices):
                if self.is_cancelled:
                    return

                self.progress.emit(
                    i, total_slices,
                    f"{self.model_name}: Slice {i+1}/{total_slices}…"
                )

                polys = self.batch_service.segment_tile(
                    self.model_name, self.session, i, **self.params
                )

                if polys:
                    self.session.tiles[i].add_layer(
                        self.layer_name, self.model_name, polys, self.layer_color
                    )

            elapsed = time.monotonic() - start_time
            self.finished.emit(elapsed)

        except Exception as e:
            logger.exception("Error in SingleModelWorker (%s): %s", self.model_name, e)
            self.error.emit(str(e))


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
    All other models run as single independent passes.
    """

    _MODEL_DESCRIPTIONS = {
        "Cellpose (cpsam)": "cpsam · CUDA",
        "NuClick (PyTorch)": "PyTorch",
        "CellViT-SAM":       "ViT-SAM",
    }

    def __init__(self, parent=None):
        super().__init__("Segmentation", parent)
        self.main_window = parent
        self.setFeatures(
            QDockWidget.DockWidgetFeature.NoDockWidgetFeatures |
            QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.worker: Optional[QThread] = None
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

        layout.addSpacing(SPACE[1])

        # ── Progress ──────────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Select a model above to run.")
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

        self.btn_run = ActionButton("Run on all slices", size="lg")
        self.btn_run.setEnabled(False)
        self.btn_run.setToolTip("Run selected model on every slice in the project")
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
            self.btn_run.setEnabled(True)
            self.chk_chain.setVisible(clicked_card.model_name == "Cellpose (cpsam)")
            _ModelCard.mousePressEvent(clicked_card, event)
        return handler

    def _selected_model(self):
        """Return (model_name, color) of the selected card, or (None, None)."""
        for card, (name, color) in zip(self._model_cards, _KNOWN_MODELS):
            if card.is_selected():
                return name, color
        return None, None

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

        use_pipeline = (model_name == "Cellpose (cpsam)" and self.chk_chain.isChecked())
        if use_pipeline:
            self._start_pipeline(s)
        else:
            self._run_single_model(model_name, color, s)

    def _run_single_model(self, model_name: str, color: str, s) -> None:
        params = self._build_params()
        self.worker = SingleModelWorker(
            s, self.main_window.batch_segmentation_service,
            model_name, params, _layer_name(model_name), color
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_single_finished)
        self.worker.error.connect(self._on_error)

        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"Running <b>{model_name}</b>…")
        self._set_running(True, pipeline=False)
        self.worker.start()

    def _start_pipeline(self, s) -> None:
        params = self._build_params()
        self.worker = MacroPipelineWorker(
            s,
            self.main_window.batch_segmentation_service,
            self.main_window.segmentation_service,
            "Cellpose (cpsam)",
            "NuClick (PyTorch)",
            params,
            run_nuclick=True,
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
        self.lbl_status.setText("Starting pipeline…")
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
        else:
            self.btn_run.setText("Run on all slices")
            self.btn_run.setEnabled(any(c.is_selected() for c in self._model_cards))
            self.btn_cancel.setEnabled(False)
            for card in self._model_cards:
                card.setEnabled(True)

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
