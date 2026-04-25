import logging
from typing import List, Tuple, Dict, Optional
from PIL.Image import Image

from app.domain.interfaces.segmentation_model import ISegmentationModel

logger = logging.getLogger(__name__)


class InteractiveSegmentationService:
    """
    Application Service that orchestrates interactive segmentation models.

    Follows Clean Architecture: this service depends only on the domain Port
    (ISegmentationModel). Concrete adapters are injected from the Composition
    Root — the service never instantiates infrastructure objects itself.
    """

    def __init__(self, models: Optional[List[ISegmentationModel]] = None):
        self._models: Dict[str, ISegmentationModel] = {}
        if models:
            for model in models:
                self.register_model(model)

    def register_model(self, model: ISegmentationModel):
        """Register a new segmentation model."""
        self._models[model.name] = model
        logger.info("Registered segmentation model: %s", model.name)

    def get_available_models(self) -> List[str]:
        """Returns the names of all available models."""
        return list(self._models.keys())

    def predict(self, model_name: str, image: Image, click_x: int, click_y: int) -> List[Tuple[int, int]]:
        """
        Executes a segmentation request handling business rules and error management.

        Args:
            model_name: The name of the model to use.
            image: Original PIL Image.
            click_x: X coordinate.
            click_y: Y coordinate.

        Returns:
            Polygon array of (x,y) coordinates.
        """
        model = self._models.get(model_name)
        if not model:
            logger.warning("Requested model '%s' not found.", model_name)
            return []

        if not (0 <= click_x < image.width and 0 <= click_y < image.height):
            logger.warning("Click coordinate (%d, %d) is out of bounds for image %s",
                           click_x, click_y, image.size)
            return []

        try:
            polygon = model.predict(image, click_x, click_y)
            return polygon
        except Exception as e:
            logger.exception("Error running interactive segmentation for %s: %s", model_name, e)
            return []

    def segment_at_point(self, model_name: str, session, slice_idx: int,
                         global_x: int, global_y: int) -> List[Tuple[int, int]]:
        """
        Full segmentation pipeline: extracts the image region from the pyramid,
        converts global coordinates to local, runs prediction, and converts
        the resulting polygon back to global coordinates.

        This method encapsulates the orchestration logic that belongs in the
        Application layer (not in the UI).

        Args:
            model_name: The name of the model to use.
            session: The current image session (has pyramid, tiles).
            slice_idx: Index of the isolated slice.
            global_x: Click X in absolute image coordinates.
            global_y: Click Y in absolute image coordinates.

        Returns:
            Polygon as list of (x, y) tuples in global coordinates, or [].
        """
        tile = session.tiles[slice_idx]
        if not tile.rects:
            return []
            
        bx1, by1, bx2, by2 = tile.bounding_box

        logger.info("segment_at_point: region=(%d,%d)-(%d,%d), click=(%d,%d)",
                     bx1, by1, bx2, by2, global_x, global_y)

        pil_img = session.pyramid.get_region_fullres(bx1, by1, bx2 - bx1, by2 - by1)
        
        # Apply tile masks (polygon and pixel_mask) by blacking out excluded regions
        pil_img = tile.get_ml_ready_image(pil_img)

        local_x = global_x - bx1
        local_y = global_y - by1

        logger.info("segment_at_point: image_size=%s, local_click=(%d,%d)",
                     pil_img.size, local_x, local_y)

        polygon = self.predict(model_name, pil_img, local_x, local_y)
        if polygon:
            global_poly = [(px + bx1, py + by1) for px, py in polygon]
            logger.info("segment_at_point: success, %d points", len(global_poly))
            return global_poly
        logger.warning("segment_at_point: predict returned empty polygon")
        return []

    def predict_batch(self, model_name: str, image: Image, clicks: List[Tuple[int, int]]) -> List[List[Tuple[int, int]]]:
        model = self._models.get(model_name)
        if not model:
            logger.warning("Requested model '%s' not found.", model_name)
            return []

        if not hasattr(model, 'predict_batch'):
            logger.warning("Model '%s' does not support predict_batch. Falling back to sequential.", model_name)
            results = []
            for cx, cy in clicks:
                results.append(self.predict(model_name, image, cx, cy))
            return results

        try:
            return model.predict_batch(image, clicks)
        except Exception as e:
            logger.exception("Error running batch interactive segmentation for %s: %s", model_name, e)
            return []

    def segment_at_points(self, model_name: str, session, slice_idx: int,
                          global_points: List[Tuple[int, int]]) -> List[List[Tuple[int, int]]]:
        """
        Batch version of segment_at_point, optimized for predicting multiple points 
        in a single image extract, utilizing GPU batch processing if available.
        """
        tile = session.tiles[slice_idx]
        if not tile.rects or not global_points:
            return []

        bx1, by1, bx2, by2 = tile.bounding_box

        logger.info("segment_at_points: region=(%d,%d)-(%d,%d), %d clicks",
                     bx1, by1, bx2, by2, len(global_points))

        pil_img = session.pyramid.get_region_fullres(bx1, by1, bx2 - bx1, by2 - by1)
        pil_img = tile.get_ml_ready_image(pil_img)

        local_points = [(gx - bx1, gy - by1) for gx, gy in global_points]

        polygons = self.predict_batch(model_name, pil_img, local_points)

        global_polygons = []
        for polygon in polygons:
            if polygon:
                global_polygons.append([(px + bx1, py + by1) for px, py in polygon])

        logger.info("segment_at_points: success, %d polygons returned", len(global_polygons))
        return global_polygons
