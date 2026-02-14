import os
from PIL import Image

class ImageSession:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        
        self.original_image = Image.open(path)
        self.real_width, self.real_height = self.original_image.size
        
        self.preview_image = None
        self.preview_scale = 1.0
        self._generate_cache()
        
        self.zoom_level = 1.0
        self.camera_x = 0
        self.camera_y = 0
        
        self.grid_w = 1000
        self.grid_h = 1000
        self.grid_color = "#FFFF00"
        self.selected_cells = set()

    def remap_selections(self, old_w, old_h, new_w, new_h):
        """Remap selected cells from old grid to new grid, preserving pixel coverage."""
        if not self.selected_cells:
            return
        max_col = max(0, (self.real_width - 1) // new_w)
        max_row = max(0, (self.real_height - 1) // new_h)
        new_cells = set()
        for (col, row) in self.selected_cells:
            # Pixel boundaries of the old cell
            px1 = col * old_w
            py1 = row * old_h
            px2 = min(px1 + old_w, self.real_width) - 1
            py2 = min(py1 + old_h, self.real_height) - 1
            # Range of new cells that overlap this pixel region
            c_start = max(0, px1 // new_w)
            c_end = min(max_col, px2 // new_w)
            r_start = max(0, py1 // new_h)
            r_end = min(max_row, py2 // new_h)
            for nc in range(c_start, c_end + 1):
                for nr in range(r_start, r_end + 1):
                    new_cells.add((nc, nr))
        self.selected_cells = new_cells

    def _generate_cache(self):
        try:
            max_size = 2048
            if self.real_width > max_size or self.real_height > max_size:
                ratio = min(max_size / self.real_width, max_size / self.real_height)
                new_w = int(self.real_width * ratio)
                new_h = int(self.real_height * ratio)
                self.preview_image = self.original_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
                self.preview_scale = self.real_width / new_w
            else:
                self.preview_image = self.original_image.copy()
                self.preview_scale = 1.0
        except:
            self.preview_image = self.original_image.copy()
            self.preview_scale = 1.0
