import logging
import numpy as np
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


class ManualAdjustmentService:
    """
    Application Service for manual fine-tuning of segmentation polygons.

    Follows Clean Architecture: this service handles the business logic of
    merging manual strokes with existing segmentation polygons.
    """

    def __init__(self, stroke_width: int = 1, dilation_radius: int = 0):
        """
        Initialize the manual adjustment service.

        Args:
            stroke_width: Width of the manual stroke in pixels
            dilation_radius: Radius for morphological dilation to expand the stroke
        """
        self.stroke_width = stroke_width
        self.dilation_radius = dilation_radius

    def apply_fine_tune(
        self,
        stroke_points: List[Tuple[int, int]],
        segmentations: List[List[Tuple[int, int]]],
        image_width: int,
        image_height: int,
        target_idx: Optional[int] = None,
        is_erase: bool = False
    ) -> List[List[Tuple[int, int]]]:
        """
        Apply manual fine-tuning strokes to segmentation polygons.

        Args:
            stroke_points: List of (x, y) points from mouse drag
            segmentations: Current list of segmentation polygons
            image_width: Width of the image region
            image_height: Height of the image region
            target_idx: Optional index of specific polygon to adjust
            is_erase: If True, subtract the stroke from polygons.

        Returns:
            Updated list of segmentation polygons
        """
        if not stroke_points:
            return segmentations

        # Create a binary mask from the stroke
        stroke_mask = self._create_stroke_mask(stroke_points, image_width, image_height)

        # Find which polygons intersect with the stroke
        if target_idx is not None and 0 <= target_idx < len(segmentations):
            # Adjust specific polygon
            polygons_to_adjust = [(target_idx, segmentations[target_idx])]
        else:
            # Find all polygons that intersect with the stroke
            polygons_to_adjust = self._find_intersecting_polygons(
                stroke_mask, segmentations, stroke_points, image_width, image_height
            )

        if not polygons_to_adjust:
            if not is_erase:
                # Create new polygon from stroke only if not erasing
                new_polygon = self._create_polygon_from_stroke(stroke_mask)
                if new_polygon:
                    segmentations.append(new_polygon)
            return segmentations

        # Adjust each intersecting polygon
        updated_segmentations = segmentations.copy()
        for idx, polygon in polygons_to_adjust:
            updated_polygon = self._merge_polygon_with_stroke(
                polygon, stroke_mask, image_width, image_height, is_erase
            )
            if updated_polygon:
                updated_segmentations[idx] = updated_polygon
            elif is_erase:
                # If erasure completely removed the polygon, we could delete it, but let's just make it empty or remove it.
                updated_segmentations[idx] = None
                
        # Remove empty / deleted segmentations
        updated_segmentations = [seg for seg in updated_segmentations if seg is not None and len(seg) >= 3]

        return updated_segmentations

    def _create_stroke_mask(
        self,
        stroke_points: List[Tuple[int, int]],
        width: int,
        height: int
    ) -> np.ndarray:
        """Create a binary mask from stroke points."""
        mask = np.zeros((height, width), dtype=np.uint8)

        if len(stroke_points) < 2:
            # Single point - draw a circle
            x, y = stroke_points[0]
            rr, cc = self._draw_circle(y, x, self.stroke_width // 2, height, width)
            mask[rr, cc] = 1
            return mask

        # Draw line segments between consecutive points
        for i in range(len(stroke_points) - 1):
            x1, y1 = stroke_points[i]
            x2, y2 = stroke_points[i + 1]

            # Create a temporary image to draw the line
            img = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(img)
            draw.line([(x1, y1), (x2, y2)], fill=1, width=self.stroke_width)

            # Add to mask
            line_mask = np.array(img)
            mask = np.logical_or(mask, line_mask).astype(np.uint8)

        # Apply dilation to expand the stroke
        if self.dilation_radius > 0:
            from scipy import ndimage
            structure = np.ones((2*self.dilation_radius + 1, 2*self.dilation_radius + 1))
            mask = ndimage.binary_dilation(mask, structure=structure).astype(np.uint8)

        return mask

    def _draw_circle(
        self,
        center_y: int,
        center_x: int,
        radius: int,
        height: int,
        width: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Draw a circle using midpoint circle algorithm."""
        y_coords = []
        x_coords = []

        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx*dx + dy*dy <= radius*radius:
                    y = center_y + dy
                    x = center_x + dx
                    if 0 <= y < height and 0 <= x < width:
                        y_coords.append(y)
                        x_coords.append(x)

        return np.array(y_coords), np.array(x_coords)

    def _find_intersecting_polygons(
        self,
        stroke_mask: np.ndarray,
        segmentations: List[List[Tuple[int, int]]],
        stroke_points: List[Tuple[int, int]],
        width: int,
        height: int
    ) -> List[Tuple[int, List[Tuple[int, int]]]]:
        """Find polygons that intersect with the stroke mask."""
        intersecting = []

        stroke_min_x = min(p[0] for p in stroke_points) - 10
        stroke_min_y = min(p[1] for p in stroke_points) - 10
        stroke_max_x = max(p[0] for p in stroke_points) + 10
        stroke_max_y = max(p[1] for p in stroke_points) + 10

        from scipy import ndimage
        structure = np.ones((5, 5))
        dilated_stroke = ndimage.binary_dilation(stroke_mask, structure=structure)

        for idx, polygon in enumerate(segmentations):
            if not polygon or len(polygon) < 3:
                continue

            # ── Fast Bounding Box Check ── 
            poly_min_x = min(p[0] for p in polygon)
            poly_min_y = min(p[1] for p in polygon)
            poly_max_x = max(p[0] for p in polygon)
            poly_max_y = max(p[1] for p in polygon)

            if (poly_max_x < stroke_min_x or poly_min_x > stroke_max_x or
                poly_max_y < stroke_min_y or poly_min_y > stroke_max_y):
                continue

            # Create mask for this polygon only if bbox overlaps
            poly_mask = np.zeros((height, width), dtype=np.uint8)

            # Use PIL to fill polygon
            img = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(img)
            draw.polygon([(x, y) for x, y in polygon], fill=1)
            poly_mask = np.array(img)

            # Check intersection with dilated stroke
            intersection = np.logical_and(dilated_stroke, poly_mask)
            if np.any(intersection):
                intersecting.append((idx, polygon))

        return intersecting

    def _merge_polygon_with_stroke(
        self,
        polygon: List[Tuple[int, int]],
        stroke_mask: np.ndarray,
        width: int,
        height: int,
        is_erase: bool = False
    ) -> Optional[List[Tuple[int, int]]]:
        """Merge a polygon with stroke mask and extract new contour."""
        try:
            # Create polygon mask
            poly_mask = np.zeros((height, width), dtype=np.uint8)
            img = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(img)
            draw.polygon([(x, y) for x, y in polygon], fill=1)
            poly_mask = np.array(img)

            # Combine with stroke mask
            if is_erase:
                combined_mask = np.logical_and(poly_mask, np.logical_not(stroke_mask)).astype(np.uint8)
            else:
                combined_mask = np.logical_or(poly_mask, stroke_mask).astype(np.uint8)

            # Check if mask is almost empty now
            if not np.any(combined_mask):
                return None

            # Extract new contour
            new_polygon = self._extract_contour(combined_mask)
            if new_polygon is None or len(new_polygon) < 3:
                return None
            return new_polygon

        except Exception as e:
            logger.error("Error merging polygon with stroke: %s", e)
            return None

    def _create_polygon_from_stroke(
        self,
        stroke_mask: np.ndarray
    ) -> Optional[List[Tuple[int, int]]]:
        """Create a new polygon from stroke mask."""
        try:
            # Find bounding box of stroke
            non_zero = np.where(stroke_mask)
            if len(non_zero[0]) == 0:
                return None

            # Add some padding
            min_y, max_y = np.min(non_zero[0]), np.max(non_zero[0])
            min_x, max_x = np.min(non_zero[1]), np.max(non_zero[1])

            pad = 5
            min_y = max(0, min_y - pad)
            max_y = min(stroke_mask.shape[0] - 1, max_y + pad)
            min_x = max(0, min_x - pad)
            max_x = min(stroke_mask.shape[1] - 1, max_x + pad)

            # Extract contour from the bounded region
            region_mask = stroke_mask[min_y:max_y+1, min_x:max_x+1]
            contour = self._extract_contour(region_mask)

            # Adjust coordinates back to original space
            if contour:
                adjusted_contour = [(x + min_x, y + min_y) for x, y in contour]
                return adjusted_contour

        except Exception as e:
            logger.error("Error creating polygon from stroke: %s", e)

        return None

    def _extract_contour(self, mask: np.ndarray) -> Optional[List[Tuple[int, int]]]:
        """
        Extract contour from binary mask using cv2 to maintain strict pixel-perfect edges.
        
        Args:
            mask: Binary mask (0 or 1)

        Returns:
            List of (x, y) points representing the contour in integer coordinates, or None
        """
        try:
            import cv2
            
            # Find contours with cv2 to avoid sub-pixel diagonal clipping completely
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            if not contours:
                return None

            # Use the largest contour
            largest_contour = max(contours, key=len)

            # Convert to list of integer points
            polygon = [(int(pt[0][0]), int(pt[0][1])) for pt in largest_contour]

            if len(polygon) < 3:
                return None

            return polygon

        except ImportError:
            logger.warning("cv2 not available for contour extraction")
            # Fallback: use bounding box
            non_zero = np.where(mask)
            if len(non_zero[0]) == 0:
                return None

            min_y, max_y = np.min(non_zero[0]), np.max(non_zero[0])
            min_x, max_x = np.min(non_zero[1]), np.max(non_zero[1])

            # Create a simple rectangle
            return [
                (min_x, min_y),
                (max_x, min_y),
                (max_x, max_y),
                (min_x, max_y)
            ]
        except Exception as e:
            logger.error("Error extracting contour: %s", e)
            return None

    def _approximate_polygon(
        self,
        polygon: List[Tuple[int, int]],
        tolerance: float = 2.0
    ) -> List[Tuple[int, int]]:
        """Simplify polygon using Ramer-Douglas-Peucker algorithm."""
        try:
            from skimage import measure

            # Convert to numpy array (y, x format for skimage)
            points = np.array([(y, x) for x, y in polygon])

            # Approximate polygon
            approx = measure.approximate_polygon(points, tolerance)

            # Convert back to (x, y) format
            return [(int(x), int(y)) for y, x in approx]

        except Exception:
            # Fallback: sample every nth point
            n = max(1, len(polygon) // 50)
            return polygon[::n]