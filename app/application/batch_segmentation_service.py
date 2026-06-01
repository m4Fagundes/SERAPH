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
from app.infrastructure.ml_models.gpu_memory import (
    cleanup_cuda_memory,
    cuda_memory_snapshot,
    cuda_memory_summary,
)

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
        self._last_instance_map = None
        self._last_vram_snapshot_start = None
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

    def get_model(self, model_name: str):
        """Return the adapter instance for model_name, or None if not registered."""
        return self._models.get(model_name)

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
            self._release_other_gpu_models(model_name)
            self._last_vram_snapshot_start = cuda_memory_snapshot()
            cuda_memory_summary(f"before {model_name}")
            polygons = model.segment(
                image,
                diameter=diameter,
                flow_threshold=flow_threshold,
                cellprob_threshold=cellprob_threshold,
            )
            self._last_probability_map = model.probability_map()
            instance_map = getattr(model, "instance_map", lambda: None)()
            self._last_instance_map = instance_map
            return polygons
        except Exception as e:
            logger.exception(
                "Error running batch segmentation for %s: %s", model_name, e
            )
            self._last_probability_map = None
            self._last_instance_map = None
            self._last_vram_snapshot_start = None
            return []
        finally:
            cleanup_hook = getattr(model, "cleanup_after_segment", None)
            if callable(cleanup_hook):
                try:
                    cleanup_hook()
                except Exception as cleanup_exc:
                    logger.debug(
                        "Cleanup hook failed for %s: %s", model_name, cleanup_exc
                    )
            cleanup_cuda_memory(f"after {model_name}")

    def _release_other_gpu_models(self, active_model_name: str) -> None:
        """Ask inactive adapters to release GPU-resident model weights."""
        for name, model in self._models.items():
            if name == active_model_name:
                continue
            release_hook = getattr(model, "release_gpu_memory", None)
            if not callable(release_hook):
                continue
            try:
                released = release_hook()
                if released:
                    logger.info(
                        "Released GPU memory for inactive model: %s", name
                    )
            except Exception as exc:
                logger.debug("GPU release hook failed for %s: %s", name, exc)

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
        prepared = self.prepare_tile_image(session, slice_idx)
        if prepared is None:
            return []

        return self.segment_prepared_tile(
            model_name,
            prepared[0],
            prepared[1],
            diameter=diameter,
            flow_threshold=flow_threshold,
            cellprob_threshold=cellprob_threshold,
        )

    def prepare_tile_image(self, session, slice_idx: int) -> Optional[Tuple[Image, Tuple[int, int]]]:
        """Extract a slice image and apply its tile mask before model inference."""
        tile = session.tiles[slice_idx]
        if not tile.rects:
            return None

        bx1, by1, bx2, by2 = tile.bounding_box

        logger.info(
            "prepare_tile_image (batch): region=(%d,%d)-(%d,%d)",
            bx1, by1, bx2, by2,
        )

        pil_img = session.pyramid.get_region_fullres(
            bx1, by1, bx2 - bx1, by2 - by1
        )
        
        # Apply tile masks (polygon and pixel_mask) by blacking out excluded regions
        pil_img = tile.get_ml_ready_image(pil_img)
        return pil_img, (bx1, by1)

    def segment_prepared_tile(
        self,
        model_name: str,
        pil_img: Image,
        origin: Tuple[int, int],
        diameter: float | None = None,
        flow_threshold: float | None = None,
        cellprob_threshold: float | None = None,
    ) -> List[List[Tuple[int, int]]]:
        """Run segmentation on a prepared tile image and offset polygons to WSI coordinates."""
        polygons = self.segment(
            model_name, pil_img,
            diameter=diameter,
            flow_threshold=flow_threshold,
            cellprob_threshold=cellprob_threshold,
        )

        # Convert local coordinates → global coordinates
        if polygons:
            bx1, by1 = origin
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

    def instance_map(self):
        """Return the raw instance-label map from the most recent segmentation call."""
        return self._last_instance_map

    def vram_snapshot_start(self):
        """Return CUDA memory snapshot captured immediately before the last segmentation."""
        return self._last_vram_snapshot_start
