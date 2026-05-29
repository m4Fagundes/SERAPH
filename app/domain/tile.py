from typing import List, Tuple, Optional, Dict, Set
import colorsys
from PIL import Image

# ── Segmentation mask colours ───────────────────────────────────────────────
# Keep these intentionally cool: cyan, teal, green and blue. Avoid red, pink,
# purple, orange and warm yellow because they blend into common H&E tissue tones.
LAYER_COLORS = [
    "#00E5FF",  # Vivid cyan
    "#20E3B2",  # Teal mint
    "#00E676",  # Spring green
    "#339AF0",  # Clear blue
    "#1DE9B6",  # Aquamarine
    "#4DABF7",  # Sky blue
    "#12D8C8",  # Blue teal
    "#69DB7C",  # Fresh green
]

_DEFAULT_MASK_COLOR = LAYER_COLORS[0]


def _hex_to_rgb(color: str) -> tuple[int, int, int] | None:
    if not isinstance(color, str):
        return None
    text = color.strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def is_safe_mask_color(color: str) -> bool:
    """Return True when a colour is safely separated from H&E warm/purple tones."""
    rgb = _hex_to_rgb(color)
    if rgb is None:
        return False
    r, g, b = (v / 255 for v in rgb)
    hue, saturation, value = colorsys.rgb_to_hsv(r, g, b)
    hue_deg = hue * 360

    if saturation < 0.35 or value < 0.35:
        return False

    # Safe zone: green/cyan/blue. Reject red, orange, yellow, pink and purple.
    return 80 <= hue_deg <= 250


def safe_mask_color(color: Optional[str], fallback_index: int = 0) -> str:
    """Return a safe segmentation mask colour, replacing warm/purple colours."""
    if color and is_safe_mask_color(color):
        return color
    return LAYER_COLORS[fallback_index % len(LAYER_COLORS)]


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
        self.metadata: Dict[str, str] = {"name": "", "description": "", "comment": "", "microns_per_pixel": ""}
        
        # Per-tile segmentation LAYERS.
        # Each layer groups all polygons from one segmentation run.
        # Structure: [
        #   {
        #     "name": "Cellpose (cpsam)",       # Display name
        #     "model": "cellpose_cpsam",         # Model identifier
        #     "polygons": [[(x,y), ...], ...],    # List of polygon contours
        #     "visible": True,                    # Toggle visibility
        #     "color": "#00E5FF",                 # Cool, high-contrast layer color
        #   }, ...
        # ]
        self.segmentation_layers: List[Dict] = []
        
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
        """Clip *img* (bounding-box crop) to the brush polygon shape and pixel_mask.

        python-patterns §4 — Single Responsibility:
          The Tile domain entity owns its own polygon geometry and pixel_mask, so it is the
          correct place to convert that geometry into a pixel mask.

        Returns a new RGBA image where pixels outside ``self.polygon`` or inside ``self.pixel_mask``
        are fully transparent. If no masks exist, returns original image.
        """
        has_poly = self.polygon and len(self.polygon) >= 3
        has_pixel = bool(self.pixel_mask)

        if not has_poly and not has_pixel:
            return img

        from PIL import ImageDraw

        bx1, by1, _, _ = self.bounding_box

        # Build an alpha mask: white (255) means KEEP, black (0) means REMOVE
        if has_poly:
            local_poly = [(pt[0] - bx1, pt[1] - by1) for pt in self.polygon]
            mask = Image.new("L", img.size, 0)
            ImageDraw.Draw(mask).polygon(local_poly, fill=255)
        else:
            mask = Image.new("L", img.size, 255)

        if has_pixel:
            draw = ImageDraw.Draw(mask)
            for (px, py) in self.pixel_mask:
                draw.point((px - bx1, py - by1), fill=0)

        rgba = img.convert("RGBA")
        rgba.putalpha(mask)
        return rgba

    def get_ml_ready_image(self, img: Image.Image) -> Image.Image:
        """Returns an RGB image with masked areas replaced by white pixels for ML models."""
        masked = self.apply_polygon_mask(img)
        if masked.mode != "RGBA":
            return masked.convert("RGB")
        
        # We use WHITE (255, 255, 255) instead of BLACK because H&E slides have
        # a naturally white background. For Cellpose, the blue channel is inverted 
        # (255 - blue). If background is black (blue=0), it becomes 255 (super bright) 
        # and breaks the normalization/segmentation. White becomes 0 (perfectly dark/ignored).
        bg = Image.new("RGB", masked.size, (255, 255, 255))
        bg.paste(masked, mask=masked.split()[3])
        return bg

    def clear_cache(self):
        """Releases the memory-resident image when leaving isolation mode."""
        self._image_cache = None

    # ── Layer helpers ─────────────────────────────────────────────────────────

    def add_layer(self, name: str, model: str, polygons: list,
                  color: Optional[str] = None) -> int:
        """Create a new segmentation layer and return its index.

        Args:
            name: Human-readable display name (e.g. "Cellpose (cpsam)").
            model: Model identifier string.
            polygons: List of polygon contours  [[(x,y), ...], ...].
            color: Optional hex color. Auto-assigned if None.

        Returns:
            Index of the newly created layer.
        """
        if color is None:
            idx = len(self.segmentation_layers)
            color = LAYER_COLORS[idx % len(LAYER_COLORS)]
        else:
            color = safe_mask_color(color, len(self.segmentation_layers))

        self.segmentation_layers.append({
            "name": name,
            "model": model,
            "model_name": model,
            "polygons": polygons,
            "visible": True,
            "color": color,
            "execution_time_s": None,
            "vram_free_gb_start": None,
            "vram_device_name": None,
            "vram_device_id": None,
        })
        return len(self.segmentation_layers) - 1

    def get_visible_polygons(self) -> list:
        """Return a flat list of (polygon, color) for all visible layers."""
        result = []
        for layer in self.segmentation_layers:
            if not layer.get("visible", True):
                continue
            color = safe_mask_color(layer.get("color"), 0)
            for poly in layer.get("polygons", []):
                if poly and len(poly) >= 3:
                    result.append((poly, color))
        return result

    # ── Serialization ─────────────────────────────────────────────────────────

    def serialize(self) -> dict:
        """Serializes the Tile entity for saving to project JSON."""
        return {
            "rects": [list(r) for r in self.rects],
            "polygon": [list(p) for p in self.polygon] if self.polygon else None,
            "exclusions": [list(e) for e in self.exclusions],
            "pixel_mask": [list(px) for px in self.pixel_mask],
            "color": self.color,
            "metadata": self.metadata,
            "segmentation_layers": [
                {
                    "name": layer.get("name", "Unknown"),
                    "model": layer.get("model", "Unknown"),
                    "model_name": layer.get("model_name", layer.get("model", "Unknown")),
                    "polygons": [
                        [list(pt) for pt in poly]
                        for poly in layer.get("polygons", [])
                    ],
                    "visible": layer.get("visible", True),
                    "color": safe_mask_color(layer.get("color"), i),
                    "execution_time_s": layer.get("execution_time_s"),
                    "vram_free_gb_start": layer.get("vram_free_gb_start"),
                    "vram_device_name": layer.get("vram_device_name"),
                    "vram_device_id": layer.get("vram_device_id"),
                    "pipeline_run_id": layer.get("pipeline_run_id"),
                    "source_layer_name": layer.get("source_layer_name"),
                }
                for i, layer in enumerate(self.segmentation_layers)
            ],
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
        
        # Ensure 'comment' exists for backward compatibility
        default_meta = {"name": "", "description": "", "comment": "", "microns_per_pixel": ""}
        loaded_meta = data.get("metadata", {})
        tile.metadata = {**default_meta, **loaded_meta}
        
        # ── Restore segmentation layers ──────────────────────────────────────
        raw_layers = data.get("segmentation_layers", [])
        tile.segmentation_layers = []
        for layer_data in raw_layers:
            tile.segmentation_layers.append({
                "name": layer_data.get("name", "Unknown"),
                "model": layer_data.get("model", "Unknown"),
                "model_name": layer_data.get("model_name", layer_data.get("model", "Unknown")),
                "polygons": [
                    [tuple(pt) for pt in poly]
                    for poly in layer_data.get("polygons", [])
                ],
                "visible": layer_data.get("visible", True),
                "color": safe_mask_color(layer_data.get("color"), len(tile.segmentation_layers)),
                "execution_time_s": layer_data.get("execution_time_s"),
                "vram_free_gb_start": layer_data.get("vram_free_gb_start"),
                "vram_device_name": layer_data.get("vram_device_name"),
                "vram_device_id": layer_data.get("vram_device_id"),
                "pipeline_run_id": layer_data.get("pipeline_run_id"),
                "source_layer_name": layer_data.get("source_layer_name"),
            })

        # ── Backward compat: old per-polygon "segmentations" → layers ────────
        raw_segs = data.get("segmentations", [])
        if raw_segs and not raw_layers:
            # Group old individual segmentations by model into layers
            from collections import defaultdict
            grouped = defaultdict(list)
            for seg_data in raw_segs:
                model = seg_data.get("model", "Imported")
                poly = [tuple(pt) for pt in seg_data.get("polygon", [])]
                if poly:
                    grouped[model].append(poly)
            for i, (model, polys) in enumerate(grouped.items()):
                color = LAYER_COLORS[i % len(LAYER_COLORS)]
                tile.segmentation_layers.append({
                    "name": model,
                    "model": model,
                    "model_name": model,
                    "polygons": polys,
                    "visible": True,
                    "color": color,
                    "execution_time_s": None,
                    "vram_free_gb_start": None,
                    "vram_device_name": None,
                    "vram_device_id": None,
                })
        
        return tile
