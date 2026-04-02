from typing import Any, Dict
from PIL import Image
from app.domain.tile_analysis import TileAnalyzer

class BasicStatsAnalyzer(TileAnalyzer):
    """
    A simple dummy analyzer that calculates basic image statistics.
    Useful for testing the architectural plumbing before real algorithms are added.
    """
    @property
    def name(self) -> str:
        return "BasicStats"

    def analyze(self, image_patch: Image.Image, **kwargs: Any) -> Dict[str, Any]:
        """Calculates basic stats: width, height, mode, and average color if RGB."""
        width, height = image_patch.size
        mode = image_patch.mode
        
        result: Dict[str, Any] = {
            "width": width,
            "height": height,
            "mode": mode,
        }
        
        # Calculate average color for RGB/RGBA images
        if mode in ("RGB", "RGBA"):
            # Ensure it's RGB for simplicity in this dummy analyzer
            img_rgb = image_patch.convert("RGB") if mode == "RGBA" else image_patch
            # Resize to 1x1 to get the average color
            avg_img = img_rgb.resize((1, 1), Image.Resampling.BILINEAR)
            r, g, b = avg_img.getpixel((0, 0)) # type: ignore
            result["average_color"] = {"r": r, "g": g, "b": b}
            result["average_hex"] = f"#{r:02x}{g:02x}{b:02x}"
            
        return result
