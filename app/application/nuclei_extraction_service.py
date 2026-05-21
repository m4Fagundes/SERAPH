import logging
from typing import List, Tuple, Dict, Any
from PIL import Image, ImageDraw

from app.domain.session import ImageSession
from app.domain.geometry import (
    get_polygon_bounding_box,
    is_rect_overlapping,
    polygon_area,
    polygon_circularity,
    get_polygon_centroid,
    is_point_in_polygon,
)

logger = logging.getLogger(__name__)

# --- Quality-filter thresholds (tune here) ---
# Minimum nucleus area in μm².  Team decision: exclude anything below 5 μm²
# (~3-4 % of detections per patient, consistent with Cellpose's known error rate).
_MIN_AREA_UM2: float = 5.0
# Maximum bounding-box aspect ratio (long / short side). Rejects thin streaks.
_MAX_ASPECT_RATIO: float = 5.0
# Minimum circularity index  4π·A/P²  (1.0 = perfect circle).
# 0.15 still accepts moderately elongated / irregular nuclei.
_MIN_CIRCULARITY: float = 0.15
# Pixels from the tile's bounding-box edge at which a nucleus is considered
# cut/partial and should be excluded from export.
_BORDER_MARGIN_PX: int = 2

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
        filtered_area = filtered_aspect = filtered_circ = filtered_border = 0

        # Build ordered list of Circle tile polygons for spatial context labeling.
        # Three conventions supported:
        #   1. Tile explicitly named "Circle" (case-insensitive) — future standard.
        #   2. Unlabeled tile (name == "" or the legacy "Unknown" fallback) whose
        #      polygon spatially contains the centroid of ANY other tile.
        #      The large circle encloses many tiles; small unlabeled Invasive
        #      sub-regions inside it contain none → they are NOT detected as circles.
        # Sorted left→right by centroid X so numbering is stable across exports.
        all_tile_centroids = [
            (t, get_polygon_centroid(t.polygon))
            for t in session.tiles
            if t.polygon
        ]
        circle_polygons = []
        for t in session.tiles:
            tname = t.metadata.get("name", "").strip()
            if not t.polygon:
                continue
            if tname.lower() == "circle":
                circle_polygons.append(t.polygon)
                logger.debug("Circle tile (explicit): name=%r", tname)
            elif not tname or tname.lower() == "unknown":
                # Unlabeled (or legacy "Unknown"): container if it encloses ≥1 other tile.
                is_container = any(
                    other is not t and is_point_in_polygon(cx, cy, t.polygon)
                    for other, (cx, cy) in all_tile_centroids
                )
                if is_container:
                    circle_polygons.append(t.polygon)
                    logger.debug("Circle tile (auto-detected unlabeled container): centroid=%s", get_polygon_centroid(t.polygon))
        circle_polygons.sort(key=lambda p: get_polygon_centroid(p)[0])
        if circle_polygons:
            logger.info("Tile %d — %d circle container(s) detected for context labeling.", tile_idx, len(circle_polygons))

        # Convert μm² threshold → px² using the session's physical resolution.
        # area_um2 = area_px2 * mpp²  →  min_px2 = min_um2 / mpp²
        try:
            mpp = float(session.microns_per_pixel)
            if mpp <= 0:
                raise ValueError("non-positive mpp")
            min_area_px2 = _MIN_AREA_UM2 / (mpp * mpp)
        except (ValueError, TypeError):
            logger.warning(
                "microns_per_pixel not set or invalid (%r) — area filter disabled for tile %d.",
                session.microns_per_pixel, tile_idx,
            )
            min_area_px2 = 0.0  # skip area filter when calibration is missing

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

                crop_x1, crop_y1, crop_x2, crop_y2 = poly_rect
                crop_w = crop_x2 - crop_x1
                crop_h = crop_y2 - crop_y1

                if crop_w <= 0 or crop_h <= 0:
                    nucleus_id += 1
                    continue

                # ── Quality filters ──────────────────────────────────────────
                area = polygon_area(poly)
                if area < min_area_px2:
                    filtered_area += 1
                    nucleus_id += 1
                    continue

                aspect = max(crop_w, crop_h) / max(min(crop_w, crop_h), 1)
                if aspect > _MAX_ASPECT_RATIO:
                    filtered_aspect += 1
                    nucleus_id += 1
                    continue

                circ = polygon_circularity(poly)
                if circ < _MIN_CIRCULARITY:
                    filtered_circ += 1
                    nucleus_id += 1
                    continue

                # ── Border / partial-cell filter ────────────────────────────
                # Exclude nuclei whose bounding box touches the ROI edge —
                # those cells are cut and would introduce incomplete samples.
                if (crop_x1 <= bx1 + _BORDER_MARGIN_PX or
                        crop_y1 <= by1 + _BORDER_MARGIN_PX or
                        crop_x2 >= bx2 - _BORDER_MARGIN_PX or
                        crop_y2 >= by2 - _BORDER_MARGIN_PX):
                    filtered_border += 1
                    nucleus_id += 1
                    continue
                # ─────────────────────────────────────────────────────────────

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
                    
                    # 3. Resolve ROI label with optional Circle context.
                    roi_name = tile.metadata.get("name", "").strip()
                    if circle_polygons:
                        cx, cy = get_polygon_centroid(poly)
                        for cidx, cpoly in enumerate(circle_polygons, 1):
                            if is_point_in_polygon(cx, cy, cpoly):
                                # Unlabeled or Circle tile itself → implicit Invasive
                                base = roi_name if roi_name and roi_name.lower() != "circle" else "Invasive"
                                roi_name = f"{base} Circle {cidx}"
                                break

                    metadata = {
                        "nucleus_id": nucleus_id,
                        "global_bbox": poly_rect,
                        "tile_intersection": tile_idx,
                        "roi_name": roi_name,
                    }
                    
                    extracted_nuclei.append((nucleus_img, metadata))
                    
                except Exception as e:
                    logger.error("Error extracting nucleus %d at %s: %s", nucleus_id, poly_rect, e)
                    # We do not fail the whole process for one bad cell.

                nucleus_id += 1

        logger.info(
            "Tile %d — extracted %d nuclei | filtered: area=%d aspect=%d circularity=%d border=%d",
            tile_idx, len(extracted_nuclei),
            filtered_area, filtered_aspect, filtered_circ, filtered_border,
        )
        return extracted_nuclei
