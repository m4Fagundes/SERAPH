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
        self.selected_cells = []
        self.slice_metadata = []  # parallel to selected_cells

    def sync_metadata(self):
        """Ensure slice_metadata stays aligned with selected_cells."""
        while len(self.slice_metadata) < len(self.selected_cells):
            self.slice_metadata.append({"description": "", "microns_per_pixel": ""})
        self.slice_metadata = self.slice_metadata[:len(self.selected_cells)]

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
