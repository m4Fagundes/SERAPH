"""
BatchSegmentationService — Application Service for batch segmentation models.

Architecture (architecture-patterns):
    Mediates between the domain Port (IBatchSegmentationModel) and the
    presentation layer. This service NEVER instantiates infrastructure
    objects itself — concrete adapters are injected from the Composition Root.

Design Decision (python-patterns §8 — Error Handling):
    Raises domain exceptions in services; logs and returns empty on failure
    to keep the GUI layer safely decoupled.

Design Decision (python-patterns §2 — Sync for CPU-bound):
    This service is synchronous. The GUI layer is responsible for calling
    it off-thread via QRunnable or QThread to keep the UI responsive.
"""

import logging
from typing import Dict, List, Optional, Tuple

from PIL.Image import Image

from app.domain.interfaces.batch_segmentation_model import IBatchSegmentationModel

logger = logging.getLogger(__name__)


class BatchSegmentationService:
    """
    Application Service that orchestrates batch segmentation models.

    Follows Clean Architecture: depends only on the domain Port
    (IBatchSegmentationModel). Concrete adapters are injected from
    the Composition Root.
    """

    def __init__(self, models: Optional[List[IBatchSegmentationModel]] = None):
        self._models: Dict[str, IBatchSegmentationModel] = {}
        self._last_probability_map = None
        if models:
            for model in models:
                self.register_model(model)

    def register_model(self, model: IBatchSegmentationModel) -> None:
        """Register a new batch segmentation model."""
        self._models[model.name] = model
        logger.info("Registered batch segmentation model: %s", model.name)

    def get_available_models(self) -> List[str]:
        """Returns the names of all available batch models."""
        return list(self._models.keys())

    def is_batch_model(self, model_name: str) -> bool:
        """Check if a model name belongs to a registered batch model."""
        return model_name in self._models

    def segment(
        self,
        model_name: str,
        image: Image,
        diameter: float | None = None,
        flow_threshold: float | None = None,
        cellprob_threshold: float | None = None,
    ) -> List[List[Tuple[int, int]]]:
        """
        Execute batch segmentation on an image.

        Args:
            model_name: The name of the model to use.
            image: PIL Image (RGB).
            diameter: Expected object diameter in pixels (optional).
            flow_threshold: Override flow error threshold (optional).
            cellprob_threshold: Override cell probability threshold (optional).

        Returns:
            List of polygon boundaries [(x, y), ...] for each detected object.
        """
        model = self._models.get(model_name)
        if not model:
            logger.warning("Requested batch model '%s' not found.", model_name)
            return []

        try:
            polygons = model.segment(
                image,
                diameter=diameter,
                flow_threshold=flow_threshold,
                cellprob_threshold=cellprob_threshold,
            )
            self._last_probability_map = model.probability_map()
            return polygons
        except Exception as e:
            logger.exception(
                "Error running batch segmentation for %s: %s", model_name, e
            )
            self._last_probability_map = None
            return []

    def segment_tile(
        self,
        model_name: str,
        session,
        slice_idx: int,
        diameter: float | None = None,
        flow_threshold: float | None = None,
        cellprob_threshold: float | None = None,
    ) -> List[List[Tuple[int, int]]]:
        """
        Full batch segmentation pipeline: extracts the image region from
        the pyramid, runs segmentation, and converts the resulting polygons
        to global coordinates.

        Args:
            model_name: Name of the batch model to use.
            session: The current image session (has pyramid, tiles).
            slice_idx: Index of the isolated tile/slice.
            diameter: Expected object diameter in pixels (optional).
            flow_threshold: Override flow error threshold (optional).
            cellprob_threshold: Override cell probability threshold (optional).

        Returns:
            List of polygons in global coordinates, or [].
        """
        tile = session.tiles[slice_idx]
        if not tile.rects:
            return []

        bx1, by1, bx2, by2 = tile.bounding_box

        logger.info(
            "segment_tile (batch): region=(%d,%d)-(%d,%d)",
            bx1, by1, bx2, by2,
        )

        pil_img = session.pyramid.get_region_fullres(
            bx1, by1, bx2 - bx1, by2 - by1
        )
        
        # Apply tile masks (polygon and pixel_mask) by blacking out excluded regions
        pil_img = tile.get_ml_ready_image(pil_img)

        polygons = self.segment(
            model_name, pil_img,
            diameter=diameter,
            flow_threshold=flow_threshold,
            cellprob_threshold=cellprob_threshold,
        )

        # Convert local coordinates → global coordinates
        if polygons:
            global_polygons = []
            for poly in polygons:
                global_poly = [(px + bx1, py + by1) for px, py in poly]
                global_polygons.append(global_poly)
            logger.info(
                "segment_tile: success, %d polygons detected.", len(global_polygons)
            )
            return global_polygons

        logger.warning("segment_tile: no objects detected.")
        return []

    def probability_map(self):
        """Return the probability map from the most recent segment() or segment_tile() call."""
        return self._last_probability_map
