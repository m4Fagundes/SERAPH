import logging
from PyQt6.QtWidgets import QWidget, QLabel, QComboBox, QPushButton, QMessageBox, QFileDialog, QProgressDialog, QInputDialog
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from app.interface.gui.theme import btn_primary, btn_nuclei, btn_hdf5, label_section
from app.interface.gui.theme_manager import themed

logger = logging.getLogger(__name__)


class _H5ExportThread(QThread):
    """Runs export_nuclei_to_h5 in a background thread and emits Qt signals
    so the main thread can update the UI safely."""

    progress_updated = pyqtSignal(int, int)   # (current, total)
    export_done      = pyqtSignal(int)         # total nuclei exported
    export_error     = pyqtSignal(str)         # error message

    def __init__(self, service, session, filepath, layer, patient_label):
        super().__init__()
        self._service       = service
        self._session       = session
        self._filepath      = filepath
        self._layer         = layer
        self._patient_label = patient_label

    def run(self):
        try:
            n = self._service.export_nuclei_to_h5(
                self._session,
                self._filepath,
                self._layer,
                patient_label=self._patient_label,
                progress_callback=self.progress_updated.emit,
            )
            self.export_done.emit(n)
        except Exception as exc:
            self.export_error.emit(str(exc))


class ExportHandler:
    def __init__(self, main_window):
        self.mw = main_window
        self._h5_thread = None   # keep reference so GC doesn't kill it mid-run

    def setup_toolbar(self, toolbar):
        lbl_fmt = QLabel(" Format: ")
        themed(lbl_fmt, label_section)
        toolbar.addWidget(lbl_fmt)

        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "JPEG", "TIFF", "BMP", "WebP"])
        self.format_combo.currentTextChanged.connect(self._format_changed)
        toolbar.addWidget(self.format_combo)

        spacing = QWidget()
        spacing.setFixedWidth(15)
        toolbar.addWidget(spacing)

        export_btn = QPushButton("🚀 Export Slices")
        export_btn.setToolTip("Export all slice images to a folder in the selected format")
        export_btn.clicked.connect(self.export_slices)
        themed(export_btn, btn_primary)
        toolbar.addWidget(export_btn)

        export_nuc_btn = QPushButton("🦠 Export Nuclei")
        export_nuc_btn.setToolTip("Export individual nucleus crops to a folder")
        export_nuc_btn.clicked.connect(self.export_nuclei)
        themed(export_nuc_btn, btn_nuclei)
        toolbar.addWidget(export_nuc_btn)

        export_h5_btn = QPushButton("📦 Export Nuclei (HDF5)")
        export_h5_btn.setToolTip("Export nucleus dataset to HDF5 format  [Ctrl+E]")
        export_h5_btn.clicked.connect(self.export_nuclei_h5)
        themed(export_h5_btn, btn_hdf5)
        toolbar.addWidget(export_h5_btn)

    def _format_changed(self, text):
        formats = {"PNG": ".png", "JPEG": ".jpg", "TIFF": ".tiff", "BMP": ".bmp", "WebP": ".webp"}
        self.mw.export_format = formats.get(text, ".png")

    def export_slices(self):
        s = self.mw.current_session
        if not s:
            QMessageBox.warning(self.mw, "Export", "No image loaded.")
            return

        if not s.tiles:
            QMessageBox.warning(self.mw, "Export", "No slices selected to export.")
            return

        export_dir = QFileDialog.getExistingDirectory(self.mw, "Select Output Folder for Slices")
        if not export_dir:
            return

        fmt = getattr(self.mw, 'export_format', '.png')

        try:
            total_exported = self.mw.export_service.save_selected_cells(
                s,
                export_dir,
                fmt,
                lambda i, count: self.mw.statusBar().showMessage(f"Exporting: {i}/{count}")
            )
            QMessageBox.information(self.mw, "Export Complete", f"Successfully exported {total_exported} images.")
            self.mw.statusBar().showMessage("Export complete.")
        except Exception as e:
            QMessageBox.critical(self.mw, "Export Error", str(e))

    def export_nuclei(self):
        s = self.mw.current_session
        if not s:
            QMessageBox.warning(self.mw, "Export Nuclei", "No image loaded.")
            return

        if not s.tiles:
            QMessageBox.warning(self.mw, "Export Nuclei", "No slices available (please select slices first).")
            return

        available_layers = set()
        for tile in s.tiles:
            for layer in tile.segmentation_layers:
                available_layers.add(layer.get("name", "Unknown"))

        if not available_layers:
            QMessageBox.warning(self.mw, "Export Nuclei", "No segmentations found in any slice.")
            return

        layer_list = ["All Segmentations"] + sorted(list(available_layers))
        selected_layer, ok = QInputDialog.getItem(
            self.mw,
            "Select Layer",
            "Choose which segmentation type to export:",
            layer_list,
            0,
            False
        )

        if not ok or not selected_layer:
            return

        export_dir = QFileDialog.getExistingDirectory(self.mw, "Select Output Folder for Nuclei")
        if not export_dir:
            return

        fmt = getattr(self.mw, 'export_format', '.png')

        try:
            total_exported = 0

            if hasattr(self.mw, '_central_stack') and self.mw._central_stack.currentIndex() == 1:
                idx = self.mw.tile_renderer.slice_idx
                if idx is not None:
                    total_exported = self.mw.export_service.export_nuclei_from_slice(s, idx, export_dir, fmt, selected_layer)
            else:
                for i in range(len(s.tiles)):
                    total_exported += self.mw.export_service.export_nuclei_from_slice(s, i, export_dir, fmt, selected_layer)

            QMessageBox.information(self.mw, "Export Complete", f"Successfully exported {total_exported} nuclei images.")
            self.mw.statusBar().showMessage("Nuclei export complete.")
        except Exception as e:
            QMessageBox.critical(self.mw, "Export Error", str(e))

    def export_probability_maps(self):
        s = self.mw.current_session
        if not s:
            QMessageBox.warning(self.mw, "Export Probability Map", "No image loaded.")
            return

        if not s.tiles:
            QMessageBox.warning(
                self.mw,
                "Export Probability Map",
                "No slices available (please select slices first)."
            )
            return

        available_layers = set()
        for tile in s.tiles:
            for layer in tile.segmentation_layers:
                available_layers.add(layer.get("name", "Unknown"))

        if not available_layers:
            QMessageBox.warning(
                self.mw,
                "Export Probability Map",
                "No segmentations found in any slice."
            )
            return

        layer_list = ["All Segmentations"] + sorted(list(available_layers))
        selected_layer, ok = QInputDialog.getItem(
            self.mw,
            "Select Segmentation Strategy",
            "Choose which segmentation strategy to export:",
            layer_list,
            0,
            False
        )
        if not ok or not selected_layer:
            return

        export_dir = QFileDialog.getExistingDirectory(self.mw, "Select Output Folder for Raw TIFF Probability Maps")
        if not export_dir:
            return

        try:
            tile_indices = None
            if hasattr(self.mw, '_central_stack') and self.mw._central_stack.currentIndex() == 1:
                idx = self.mw.tile_renderer.slice_idx
                tile_indices = [idx] if idx is not None else None

            total_exported = self.mw.export_service.export_probability_maps(
                s,
                export_dir,
                selected_layer,
                tile_indices=tile_indices,
                progress_callback=lambda i, count: self.mw.statusBar().showMessage(
                    f"Exporting probability maps: {i}/{count}"
                )
            )
            if total_exported == 0:
                QMessageBox.warning(
                    self.mw,
                    "Export Probability Map",
                    "No raw probability maps were found for this selection. "
                    "Run the segmentation again with Cellpose, CellViT, or PathoSAM before exporting."
                )
                self.mw.statusBar().showMessage("No raw probability maps found.")
            else:
                QMessageBox.information(
                    self.mw,
                    "Export Complete",
                    f"Successfully exported {total_exported} raw TIFF probability map(s)."
                )
                self.mw.statusBar().showMessage("Raw probability map export complete.")
        except Exception as e:
            QMessageBox.critical(self.mw, "Export Error", str(e))

    def export_instance_masks(self):
        s = self.mw.current_session
        if not s:
            QMessageBox.warning(self.mw, "Export Instance Masks", "No image loaded.")
            return

        if not s.tiles:
            QMessageBox.warning(
                self.mw,
                "Export Instance Masks",
                "No slices available (please select slices first)."
            )
            return

        available_layers = set()
        for tile in s.tiles:
            for layer in tile.segmentation_layers:
                available_layers.add(layer.get("name", "Unknown"))

        if not available_layers:
            QMessageBox.warning(
                self.mw,
                "Export Instance Masks",
                "No segmentations found in any slice."
            )
            return

        layer_list = ["All Segmentations"] + sorted(list(available_layers))
        selected_layer, ok = QInputDialog.getItem(
            self.mw,
            "Select Segmentation Strategy",
            "Choose which segmentation strategy to export as instance masks:",
            layer_list,
            0,
            False
        )
        if not ok or not selected_layer:
            return

        export_dir = QFileDialog.getExistingDirectory(
            self.mw,
            "Select Output Folder for TIFF/NPY Instance Masks"
        )
        if not export_dir:
            return

        try:
            tile_indices = None
            if hasattr(self.mw, '_central_stack') and self.mw._central_stack.currentIndex() == 1:
                idx = self.mw.tile_renderer.slice_idx
                tile_indices = [idx] if idx is not None else None

            total_exported = self.mw.export_service.export_instance_masks(
                s,
                export_dir,
                selected_layer,
                tile_indices=tile_indices,
                progress_callback=lambda i, count: self.mw.statusBar().showMessage(
                    f"Exporting instance masks: {i}/{count}"
                )
            )
            if total_exported == 0:
                QMessageBox.warning(
                    self.mw,
                    "Export Instance Masks",
                    "No raw instance masks were found for model layers. "
                    "Run Cellpose, CellViT-SAM, or PathoSAM again, or select a GT layer."
                )
                self.mw.statusBar().showMessage("No instance masks exported.")
            else:
                QMessageBox.information(
                    self.mw,
                    "Export Complete",
                    f"Successfully exported {total_exported} TIFF/NPY instance mask set(s)."
                )
                self.mw.statusBar().showMessage("Instance mask export complete.")
        except Exception as e:
            QMessageBox.critical(self.mw, "Export Error", str(e))

    def export_nuclei_h5(self):
        s = self.mw.current_session
        if not s:
            QMessageBox.warning(self.mw, "Export HDF5", "No image loaded.")
            return

        if not s.tiles:
            QMessageBox.warning(self.mw, "Export HDF5", "No slices available (please select slices first).")
            return

        available_layers = set()
        for tile in s.tiles:
            for layer in tile.segmentation_layers:
                available_layers.add(layer.get("name", "Unknown"))

        if not available_layers:
            QMessageBox.warning(self.mw, "Export HDF5", "No segmentations found in any slice.")
            return

        # ── Microns-per-pixel gate ─────────────────────────────────────────
        # pixel_size_um is stored in the H5 file and drives the area filter
        # inside NucleiExtractionService. Export is blocked until a valid
        # positive value is confirmed.
        def _parse_mpp(raw) -> float:
            try:
                v = float(raw)
                if v > 0:
                    return v
            except (TypeError, ValueError):
                pass
            return 0.0

        current_mpp = _parse_mpp(getattr(s, "microns_per_pixel", "") or "")
        if current_mpp <= 0:
            mpp_text, ok = QInputDialog.getText(
                self.mw,
                "Physical Resolution Required",
                "Microns per pixel (µm/px) is required for HDF5 export.\n"
                "It sets the physical scale stored in pixel_size_um and\n"
                "enables the nucleus area filter (min 5 µm²).\n\n"
                "Enter the pixel size in microns (e.g. 0.2420):",
            )
            if not ok or not mpp_text.strip():
                return
            current_mpp = _parse_mpp(mpp_text.strip())
            if current_mpp <= 0:
                QMessageBox.critical(
                    self.mw, "Invalid Resolution",
                    f'"{mpp_text.strip()}" is not a valid positive number.\nExport cancelled.'
                )
                return
            s.microns_per_pixel = str(current_mpp)
        # ──────────────────────────────────────────────────────────────────

        layer_list = ["All Segmentations"] + sorted(list(available_layers))
        selected_layer, ok = QInputDialog.getItem(
            self.mw, "Select Layer",
            "Choose which segmentation type to export to HDF5:",
            layer_list, 0, False
        )
        if not ok or not selected_layer:
            return

        label_items = ["0 — Low Risk", "1 — High Risk"]
        label_text, ok = QInputDialog.getItem(
            self.mw, "Patient Label",
            "Is this patient High Risk or Low Risk?",
            label_items, 0, False
        )
        if not ok:
            return
        patient_label = int(label_text[0])

        export_file, _ = QFileDialog.getSaveFileName(
            self.mw, "Save HDF5 File", "", "HDF5 Files (*.h5)"
        )
        if not export_file:
            return

        # ── Progress dialog ────────────────────────────────────────────────
        progress = QProgressDialog("Preparing export…", None, 0, 100, self.mw)
        progress.setWindowTitle("HDF5 Export")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)   # no cancel — mid-stream cancel would corrupt the file
        progress.setValue(0)
        progress.show()

        # ── Worker thread — updates UI only via signals ────────────────────
        self._h5_thread = _H5ExportThread(
            self.mw.export_service, s, export_file, selected_layer, patient_label
        )

        def on_progress(current, total):
            pct = int(current / max(total, 1) * 100)
            progress.setValue(pct)
            progress.setLabelText(f"Exporting nuclei… {current:,} / {total:,}")
            self.mw.statusBar().showMessage(f"HDF5 export: {current:,} / {total:,} nuclei")

        def on_done(total):
            progress.close()
            if total == 0:
                QMessageBox.information(self.mw, "Export Complete", "No nuclei found to export.")
            else:
                QMessageBox.information(
                    self.mw, "Export Complete",
                    f"Successfully exported {total:,} nuclei to HDF5."
                )
            self.mw.statusBar().showMessage("HDF5 export complete.")
            self._h5_thread = None

        def on_error(msg):
            progress.close()
            QMessageBox.critical(self.mw, "Export Error", msg)
            self.mw.statusBar().showMessage("HDF5 export failed.")
            self._h5_thread = None

        self._h5_thread.progress_updated.connect(on_progress)
        self._h5_thread.export_done.connect(on_done)
        self._h5_thread.export_error.connect(on_error)
        self._h5_thread.start()
