import logging
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton, QMessageBox, QFileDialog

logger = logging.getLogger(__name__)

class ExportHandler:
    def __init__(self, main_window):
        self.mw = main_window

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
        
        # Spacer before export button
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
            QPushButton:hover {
                background-color: #0098ff;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
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
            QPushButton:hover {
                background-color: #e91e63;
            }
            QPushButton:pressed {
                background-color: #c2185b;
            }
        """)
        toolbar.addWidget(export_nuc_btn)

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
            
        from PyQt6.QtWidgets import QInputDialog
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
            
            # Check if we are inside a specific slice context (Micro environment)
            if hasattr(self.mw, '_central_stack') and self.mw._central_stack.currentIndex() == 1:
                idx = self.mw.tile_renderer.slice_idx
                if idx is not None:
                    total_exported = self.mw.export_service.export_nuclei_from_slice(s, idx, export_dir, fmt, selected_layer)
            else:
                # Iterate through all tiles if in global view
                for i in range(len(s.tiles)):
                    total_exported += self.mw.export_service.export_nuclei_from_slice(s, i, export_dir, fmt, selected_layer)
            
            QMessageBox.information(self.mw, "Export Complete", f"Successfully exported {total_exported} nuclei images.")
            self.mw.statusBar().showMessage("Nuclei export complete.")
        except Exception as e:
            QMessageBox.critical(self.mw, "Export Error", str(e))
