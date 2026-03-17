import sys
from PyQt6.QtWidgets import QApplication
from app.interface.gui.components.tile_preview_dialog import TilePreviewDialog
from PIL import Image

class MockPyramid:
    def get_region_fullres(self, x1, y1, w, h):
        return Image.new("RGB", (w, h), "white")

class MockSession:
    def __init__(self):
        self.selected_cells = [[(0, 0, 100, 100)]]
        self.slice_metadata = [{"name": "Slice 1"}]
        self.pyramid = MockPyramid()
        
app = QApplication(sys.argv)
s = MockSession()
dialog = TilePreviewDialog(session=s, slice_idx=0)
print("Dialog created successfully!")
