from typing import List, Tuple, Optional, Dict, Set
from PIL import Image

class Tile:
    """
    Domain entity representing an isolated slice (tile) from the main ImagePyramid.
    Encapsulates all metadata, shapes, annotations, and pixel modifications for this specific region.
    Also handles independent image rendering to prevent zooming crashes.
    """
    def __init__(self,
                 rects: Optional[List[Tuple[int, int, int, int]]] = None,
                 polygon: Optional[List[Tuple[int, int]]] = None):
        # Annotations
        self.rects: List[Tuple[int, int, int, int]] = rects or []
        self.polygon: Optional[List[Tuple[int, int]]] = polygon
        self.exclusions: List[Tuple[int, int, int, int]] = []
        self.pixel_mask: Set[Tuple[int, int]] = set()
        
        # Display & Metadata
        self.color: str = "#00FFFF"
        self.metadata: Dict[str, str] = {"name": "", "description": "", "microns_per_pixel": ""}
        
        # Memory-resident image for Independent Rendering (True Isolation)
        self._image_cache: Optional[Image.Image] = None
        
    @property
    def bounding_box(self) -> Tuple[int, int, int, int]:
        """Calculates the global bounding box encompassing all rects in this tile."""
        if not self.rects:
            return (0, 0, 0, 0)
        
        min_x = min(r[0] for r in self.rects)
        min_y = min(r[1] for r in self.rects)
        max_x = max(r[2] for r in self.rects)
        max_y = max(r[3] for r in self.rects)
        return (min_x, min_y, max_x, max_y)

    def load_pixels(self, pyramid) -> Image.Image:
        """
        Extracts the high-resolution pixels from the main pyramid into this Tile's local memory.
        This enables 'True Isolation': rendering and zooming without ever loading the full pyramid again.
        """
        if self._image_cache is not None:
            return self._image_cache
            
        bx1, by1, bx2, by2 = self.bounding_box
        if bx1 == bx2 or by1 == by2:
            return None
            
        # Get pixels using get_region_fullres 
        region = pyramid.get_region_fullres(bx1, by1, bx2 - bx1, by2 - by1)
        if region:
            self._image_cache = region.convert("RGB")
        return self._image_cache

    def apply_polygon_mask(self, img: Image.Image) -> Image.Image:
        """Clip *img* (bounding-box crop) to the brush polygon shape.

        python-patterns §4 — Single Responsibility:
          The Tile domain entity owns its own polygon geometry, so it is the
          correct place to convert that geometry into a pixel mask.

        Returns a new RGBA image where pixels outside ``self.polygon`` are
        fully transparent.  If ``self.polygon`` is None the original image is
        returned unchanged (grid tiles use this path — no masking).
        """
        if not self.polygon or len(self.polygon) < 3:
            return img

        from PIL import ImageDraw

        bx1, by1, _, _ = self.bounding_box

        # Translate global polygon coords → local image coords
        local_poly = [(pt[0] - bx1, pt[1] - by1) for pt in self.polygon]

        # Build an alpha mask: white inside polygon, black outside
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).polygon(local_poly, fill=255)

        rgba = img.convert("RGBA")
        rgba.putalpha(mask)
        return rgba

    def clear_cache(self):
        """Releases the memory-resident image when leaving isolation mode."""
        self._image_cache = None

    def serialize(self) -> dict:
        """Serializes the Tile entity for saving to project JSON."""
        return {
            "rects": [list(r) for r in self.rects],
            "polygon": [list(p) for p in self.polygon] if self.polygon else None,
            "exclusions": [list(e) for e in self.exclusions],
            "pixel_mask": [list(px) for px in self.pixel_mask],
            "color": self.color,
            "metadata": self.metadata
        }

    @classmethod
    def deserialize(cls, data: dict) -> 'Tile':
        """Reconstructs the Tile entity from project JSON."""
        rects_data = data.get("rects") or []
        rects = [tuple(r) for r in rects_data]
        tile = cls(rects)
        if data.get("polygon"):
            tile.polygon = [tuple(p) for p in data["polygon"]]
        tile.exclusions = [tuple(e) for e in data.get("exclusions", [])]
        tile.pixel_mask = set(tuple(px) for px in data.get("pixel_mask", []))
        tile.color = data.get("color", "#00FFFF")
        tile.metadata = data.get("metadata", {"name": "", "description": "", "microns_per_pixel": ""})
        return tile
