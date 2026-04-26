import sys

path = r'c:\Users\mathe\OneDrive\Documentos\MyLife\Scientific Research\grid-image-analyzer\app\interface\gui\components\slice_export.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

target1 = 'export_dir = QFileDialog.getExistingDirectory(self.mw, "Select Output Folder for Nuclei")'
replace1 = """        available_layers = set()
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

        export_dir = QFileDialog.getExistingDirectory(self.mw, "Select Output Folder for Nuclei")"""

text = text.replace(target1, replace1)

target2 = 'total_exported = self.mw.export_service.export_nuclei_from_slice(s, idx, export_dir, fmt)'
replace2 = 'total_exported = self.mw.export_service.export_nuclei_from_slice(s, idx, export_dir, fmt, selected_layer)'
text = text.replace(target2, replace2)

target3 = 'total_exported += self.mw.export_service.export_nuclei_from_slice(s, i, export_dir, fmt)'
replace3 = 'total_exported += self.mw.export_service.export_nuclei_from_slice(s, i, export_dir, fmt, selected_layer)'
text = text.replace(target3, replace3)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

print("SUCCESS")
