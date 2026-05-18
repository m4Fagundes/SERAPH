import logging
from typing import List, Tuple, Dict, Any
from PIL import Image, ImageDraw

from app.domain.session import ImageSession
from app.domain.geometry import get_polygon_bounding_box, is_rect_overlapping

logger = logging.getLogger(__name__)

class NucleiExtractionService:
    """
    Application Service responsible for extracting individual segmented nuclei
    from a specific tile/slice. 
    Follows Single Responsibility Principle (Clean Architecture).
    """

    def extract_nuclei_from_tile(self, session: ImageSession, tile_idx: int, selected_layer: str = "All Segmentations") -> List[Tuple[Image.Image, Dict[str, Any]]]:
        """
        Extracts all segmented nuclei that intersect with the given tile.

        Args:
            session: The active image session containing tiles and segmentations.
            tile_idx: The index of the tile to process.
            selected_layer: If provided, only extract nuclei from the layer matching this name.

        Returns:
            A list of tuples containing:
            - The extracted nucleus image (RGBA, transparent background).
            - A metadata dict with global original coordinates for reference.
        """
        try:
            tile = session.tiles[tile_idx]
        except IndexError:
            logger.error("Tile index %d out of bounds.", tile_idx)
            raise ValueError(f"Tile index {tile_idx} not found.")

        # If tile has no boxes, we can't extract
        bx1, by1, bx2, by2 = tile.bounding_box
        if bx1 == bx2 or by1 == by2:
            return []

        tile_rect = (bx1, by1, bx2, by2)
        extracted_nuclei = []

        # Find overlapping nuclei from per-tile segmentation layers
        nucleus_id = 0
        for layer in tile.segmentation_layers:
            # Filter by layer name if requested
            if selected_layer != "All Segmentations" and layer.get("name", "Unknown") != selected_layer:
                continue
                
            for poly in layer.get("polygons", []):
                if not poly or len(poly) < 3:
                    nucleus_id += 1
                    continue

                poly_rect = get_polygon_bounding_box(poly)
                
                # Check overlap mathematically first
                if not is_rect_overlapping(tile_rect, poly_rect):
                    nucleus_id += 1
                    continue
                
                # The nucleus intersects the tile.
                # We crop the exact bounding box of the polygon from the pyramid
                # so we only load what we need, not the entire tile.
                crop_x1, crop_y1, crop_x2, crop_y2 = poly_rect
                
                crop_w = crop_x2 - crop_x1
                crop_h = crop_y2 - crop_y1
                
                if crop_w <= 0 or crop_h <= 0:
                    nucleus_id += 1
                    continue

                try:
                    # 1. Fetch exact high-res pixels
                    nucleus_img = session.pyramid.get_region_fullres(crop_x1, crop_y1, crop_w, crop_h)
                    nucleus_img = nucleus_img.convert("RGBA")
                    
                    # 2. Apply polygon mask
                    mask = Image.new("L", (crop_w, crop_h), 0)
                    draw = ImageDraw.Draw(mask)
                    
                    # Translate global coords to local crop coords
                    local_poly = [(px - crop_x1, py - crop_y1) for px, py in poly]
                    draw.polygon(local_poly, fill=255)
                    
                    # Optional: Handle pixels outside the polygon
                    nucleus_img.putalpha(mask)
                    
                    # 3. Save to output list
                    metadata = {
                        "nucleus_id": nucleus_id,
                        "global_bbox": poly_rect,
                        "tile_intersection": tile_idx,
                        "roi_name": tile.metadata.get("name", "")
                    }
                    
                    extracted_nuclei.append((nucleus_img, metadata))
                    
                except Exception as e:
                    logger.error("Error extracting nucleus %d at %s: %s", nucleus_id, poly_rect, e)
                    # We do not fail the whole process for one bad cell.

                nucleus_id += 1

        logger.info("Extracted %d nuclei from tile %d.", len(extracted_nuclei), tile_idx)
        return extracted_nuclei
