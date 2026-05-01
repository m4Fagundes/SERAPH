import logging
import time
from typing import Optional
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from app.domain.geometry import get_polygon_centroid

logger = logging.getLogger(__name__)

class MacroPipelineWorker(QThread):
    progress = pyqtSignal(int, int, str) # current, total, status_text
    time_update = pyqtSignal(str, float) # phase, elapsed_time
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, session, batch_service, interactive_service, cellpose_model, nuclick_model, cellpose_params):
        super().__init__()
        self.session = session
        self.batch_service = batch_service
        self.interactive_service = interactive_service
        self.cellpose_model = cellpose_model
        self.nuclick_model = nuclick_model
        self.cellpose_params = cellpose_params
        
        self.is_paused = False
        self.is_cancelled = False
        
        # State machine
        self.current_phase = 1 # 1: Cellpose, 2: Nuclick
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
                    if self.is_cancelled: return

                    self.progress.emit(i, total_slices, f"Cellpose: Analyzing Slice {i+1}/{total_slices}...")
                    
                    # Run Cellpose
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
                self.current_phase = 2

            # PHASE 2: NuClick
            if self.current_phase == 2:
                start_time = time.monotonic()
                for i in range(self.current_slice_idx, total_slices):
                    while self.is_paused and not self.is_cancelled:
                        time.sleep(0.1)
                    if self.is_cancelled: return

                    self.progress.emit(i, total_slices, f"NuClick: Refining Slice {i+1}/{total_slices}...")
                    
                    tile = self.session.tiles[i]
                    centroids = []
                    # Get centroids only from the newly added Macro Cellpose layer
                    for layer in tile.segmentation_layers:
                        if layer.get("name") == "Macro Cellpose":
                            for poly in layer.get("polygons", []):
                                centroids.append(get_polygon_centroid(poly))
                    
                    if centroids:
                        nuclick_polys = self.interactive_service.segment_at_points(
                            self.nuclick_model, self.session, i, centroids
                        )
                        if nuclick_polys:
                            tile.add_layer("Macro NuClick", self.nuclick_model, nuclick_polys, "#00FFFF")

                    self.current_slice_idx = i + 1

                elapsed = time.monotonic() - start_time
                self.time_update.emit("NuClick", elapsed)

            self.finished.emit()

        except Exception as e:
            logger.exception("Error in MacroPipelineWorker: %s", e)
            self.error.emit(str(e))


class MacroPipelinePanel(QDockWidget):
    """
    Dock widget to control the Macro Pipeline (Cellpose -> NuClick) on all tiles.
    """
    def __init__(self, parent=None):
        super().__init__("🚀 Macro Batch Pipeline", parent)
        self.main_window = parent
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        
        self.setStyleSheet("""
            QDockWidget { background-color: #252526; color: #ccc; font-family: 'Segoe UI', Tahoma, sans-serif; font-weight: bold; }
            QLabel { color: #cccccc; font-size: 9pt; }
            QPushButton { background-color: #0e639c; color: white; padding: 6px; font-weight: bold; border-radius: 4px; border: none; font-family: 'Segoe UI', Tahoma, sans-serif; }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:disabled { background-color: #555555; color: #888888; }
            QProgressBar { border: 1px solid #555; border-radius: 3px; text-align: center; color: white; background-color: #3c3c3c; }
            QProgressBar::chunk { background-color: #00FF88; }
        """)

        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        
        self.lbl_info = QLabel("Segments all slices with Cellpose\nand refines all with NuClick.")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet("color: #aaaaaa; font-size: 8pt; margin-bottom: 8px;")
        self.layout.addWidget(self.lbl_info)

        self.btn_start = QPushButton("▶️ Start Pipeline")
        self.btn_start.clicked.connect(self._toggle_start_pause)
        
        self.btn_cancel = QPushButton("⏹️ Cancel")
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_cancel.setEnabled(False)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_cancel)
        self.layout.addLayout(btn_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Ready to start.")
        self.layout.addWidget(self.lbl_status)

        self.lbl_time_cellpose = QLabel("Cellpose Time: --")
        self.lbl_time_cellpose.setStyleSheet("color: #F1C40F; font-weight: bold;")
        self.layout.addWidget(self.lbl_time_cellpose)

        self.lbl_time_nuclick = QLabel("NuClick Time: --")
        self.lbl_time_nuclick.setStyleSheet("color: #F1C40F; font-weight: bold;")
        self.layout.addWidget(self.lbl_time_nuclick)

        self.layout.addStretch()
        self.setWidget(self.container)

        self.worker = None

    def _toggle_start_pause(self):
        s = self.main_window.current_session
        if not s or not s.tiles:
            self.lbl_status.setText("No slices found in the project.")
            return

        if self.worker is None:
            # START completely new
            self._start_pipeline()
        else:
            # PAUSE / RESUME logic
            if self.worker.is_paused:
                self.worker.resume()
                self.btn_start.setText("⏸️ Pause")
                self.lbl_status.setText("Resuming pipeline...")
            else:
                self.worker.pause()
                self.btn_start.setText("▶️ Resume")
                self.lbl_status.setText("Pipeline paused.")

    def _start_pipeline(self):
        s = self.main_window.current_session
        
        cellpose_model = "Cellpose (nuclei)"
        nuclick_model = "NuClick (PyTorch)"

        diameter = self.main_window.spin_diameter.value()
        diameter = None if diameter == 0.0 else diameter
        params = {
            "diameter": diameter,
            "flow_threshold": self.main_window.spin_flow.value(),
            "cellprob_threshold": self.main_window.spin_cellprob.value(),
        }

        self.worker = MacroPipelineWorker(
            s, self.main_window.batch_segmentation_service,
            self.main_window.segmentation_service,
            cellpose_model, nuclick_model, params
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.time_update.connect(self._on_time_update)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)

        self.btn_start.setText("⏸️ Pause")
        self.btn_cancel.setEnabled(True)
        self.lbl_time_cellpose.setText("Cellpose Time: --")
        self.lbl_time_nuclick.setText("NuClick Time: --")
        self.progress_bar.setValue(0)
        
        self.worker.start()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()
            self.worker.wait()
            self.worker = None
            self.btn_start.setText("▶️ Iniciar Pipeline")
            self.btn_cancel.setEnabled(False)
            self.lbl_status.setText("Cancelled by user.")
            self.progress_bar.setValue(0)

    def _on_progress(self, current, total, text):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.lbl_status.setText(text)

    def _on_time_update(self, phase, elapsed):
        if phase == "Cellpose":
            self.lbl_time_cellpose.setText(f"Cellpose Time: {elapsed:.2f}s")
            self.lbl_time_cellpose.setStyleSheet("color: #00FF88; font-weight: bold;")
        elif phase == "NuClick":
            self.lbl_time_nuclick.setText(f"NuClick Time: {elapsed:.2f}s")
            self.lbl_time_nuclick.setStyleSheet("color: #00FF88; font-weight: bold;")
            
        if hasattr(self.main_window, 'layer_dropdown'):
            self.main_window.layer_dropdown.refresh()

    def _on_finished(self):
        self.btn_start.setText("▶️ Iniciar Pipeline")
        self.btn_cancel.setEnabled(False)
        self.lbl_status.setText("Pipeline completed successfully!")
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.worker = None
        
        if hasattr(self.main_window, 'layer_dropdown'):
            self.main_window.layer_dropdown.refresh()
        if hasattr(self.main_window, 'canvas_renderer'):
            self.main_window.canvas_renderer.redraw()
        if hasattr(self.main_window, 'tile_renderer'):
            self.main_window.tile_renderer.viewport().update()

    def _on_error(self, err_msg):
        self.lbl_status.setText(f"Error: {err_msg}")
        self.btn_start.setText("▶️ Start Pipeline")
        self.btn_cancel.setEnabled(False)
        self.worker = None
