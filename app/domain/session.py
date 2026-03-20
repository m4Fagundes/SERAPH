import os
from typing import List, Tuple, Optional, Dict, Set
from app.domain.pyramid import ImagePyramid


from app.domain.tile import Tile


# 10 visually distinct colors for tile overlays
TILE_COLORS = [
    "#00FFFF",  # cyan
    "#FF6B6B",  # coral red
    "#51CF66",  # green
    "#FFD43B",  # yellow
    "#CC5DE8",  # purple
    "#FF922B",  # orange
    "#74C0FC",  # light blue
    "#F06595",  # pink
    "#20C997",  # teal
    "#A9E34B",  # lime
]


class ImageSession:
    def __init__(self, path: str):
        self.path: str = path
        self.name: str = os.path.basename(path)

        # On-demand image reader — opens instantly, no build step
        self.pyramid: ImagePyramid = ImagePyramid(path)
        self.real_width: int = self.pyramid.image_width
        self.real_height: int = self.pyramid.image_height
        self.pyramid_ready: bool = True  # always ready (on-demand)

        self._thumbnail: Optional[bytes] = None

        self.zoom_level: float = 1.0
        self.camera_x: int = 0
        self.camera_y: int = 0

        self.grid_w: int = 1000
        self.grid_h: int = 1000
        self.grid_color: str = "#FFFF00"
        
        # New Domain Entity List
        self.tiles: List[Tile] = []
        self.segmentations: List[List[Tuple[int, int]]] = []

        self.export_dir: Optional[str] = None
        self.export_format: Optional[str] = None

    def get_thumbnail(self, max_size: int = 220) -> bytes:
        """Get a cached thumbnail for sidebar previews."""
        if self._thumbnail is None:
            self._thumbnail = self.pyramid.get_thumbnail(max_size=max_size)
        return self._thumbnail

    def set_grid(self, grid_w: int, grid_h: int, grid_color: str) -> None:
        """Set grid dimensions and color."""
        self.grid_w = grid_w
        self.grid_h = grid_h
        self.grid_color = grid_color

    def set_zoom(self, zoom_level: float) -> None:
        """Set the current zoom level."""
        self.zoom_level = zoom_level

    def move_camera(self, camera_x: int, camera_y: int) -> None:
        """Move the camera position."""
        self.camera_x = camera_x
        self.camera_y = camera_y

    def set_export_settings(self, export_dir: str, export_format: str) -> None:
        """Set the export directory and format."""
        self.export_dir = export_dir
        self.export_format = export_format

    # ------------------------------------------------------------------
    # Memory management helpers
    # ------------------------------------------------------------------

    def unload_image(self) -> None:
        """Release pixel buffers for this session.

        Call when switching away from a session to free RAM / file
        descriptors.  Thumbnail cache is preserved so the sidebar
        preview stays fast.
        """
        if self.pyramid_ready:
            self.pyramid.unload()
            self.pyramid_ready = False

    def reload_image(self) -> None:
        """Re-open the image file if previously unloaded."""
        if not self.pyramid_ready:
            self.pyramid = ImagePyramid(self.path)
            self.pyramid_ready = True
