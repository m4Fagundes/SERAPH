import os
from app.domain.pyramid import ImagePyramid


class ImageSession:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)

        # On-demand image reader — opens instantly, no build step
        self.pyramid = ImagePyramid(path)
        self.real_width = self.pyramid.image_width
        self.real_height = self.pyramid.image_height
        self.pyramid_ready = True  # always ready (on-demand)

        self._thumbnail = None

        self.zoom_level = 1.0
        self.camera_x = 0
        self.camera_y = 0

        self.grid_w = 1000
        self.grid_h = 1000
        self.grid_color = "#FFFF00"
        self.selected_cells = []
        self.selected_polygons = []   # parallel to selected_cells: None (grid) or list of (x,y) (brush)
        self.slice_metadata = []
        self.export_dir = None
        self.export_format = None

    def get_thumbnail(self, max_size=220):
        """Get a cached thumbnail for sidebar previews."""
        if self._thumbnail is None:
            self._thumbnail = self.pyramid.get_thumbnail(max_size=max_size)
        return self._thumbnail

    def sync_metadata(self):
        """Ensure slice_metadata and selected_polygons stay aligned with selected_cells."""
        n = len(self.selected_cells)
        while len(self.slice_metadata) < n:
            self.slice_metadata.append({"description": "", "microns_per_pixel": ""})
        self.slice_metadata = self.slice_metadata[:n]
        while len(self.selected_polygons) < n:
            self.selected_polygons.append(None)
        self.selected_polygons = self.selected_polygons[:n]
