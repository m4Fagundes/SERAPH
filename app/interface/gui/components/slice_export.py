import logging
from PyQt6.QtWidgets import QWidget, QLabel, QComboBox, QPushButton, QMessageBox, QFileDialog, QProgressDialog, QInputDialog
from PyQt6.QtCore import Qt, QThread, pyqtSignal

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
        lbl_fmt.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        toolbar.addWidget(lbl_fmt)

        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "JPEG", "TIFF", "BMP", "WebP"])
        self.format_combo.setStyleSheet("""
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
        self.format_combo.currentTextChanged.connect(self._format_changed)
        toolbar.addWidget(self.format_combo)

        spacing = QWidget()
        spacing.setFixedWidth(15)
        toolbar.addWidget(spacing)

        export_btn = QPushButton("🚀 Export Slices")
        export_btn.clicked.connect(self.export_slices)
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 15px;
                font-family: 'Segoe UI', Tahoma, sans-serif;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #0098ff; }
            QPushButton:pressed { background-color: #005a9e; }
        """)
        toolbar.addWidget(export_btn)

        export_nuc_btn = QPushButton("🦠 Export Nuclei")
        export_nuc_btn.clicked.connect(self.export_nuclei)
        export_nuc_btn.setStyleSheet("""
            QPushButton {
                background-color: #d81b60;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 15px;
                font-family: 'Segoe UI', Tahoma, sans-serif;
                font-weight: bold;
                margin-left: 5px;
            }
            QPushButton:hover { background-color: #e91e63; }
            QPushButton:pressed { background-color: #c2185b; }
        """)
        toolbar.addWidget(export_nuc_btn)

        export_h5_btn = QPushButton("📦 Export Nuclei (HDF5)")
        export_h5_btn.clicked.connect(self.export_nuclei_h5)
        export_h5_btn.setStyleSheet("""
            QPushButton {
                background-color: #8e44ad;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 15px;
                font-family: 'Segoe UI', Tahoma, sans-serif;
                font-weight: bold;
                margin-left: 5px;
            }
            QPushButton:hover { background-color: #9b59b6; }
            QPushButton:pressed { background-color: #732d91; }
        """)
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
