"""
CellposeAdapter — Infrastructure Adapter for the Cellpose segmentation model.

Architecture (architecture-patterns / python-patterns):
    Implements the IBatchSegmentationModel domain Port.
    All Cellpose-specific logic (imports, model loading, inference,
    mask → polygon conversion) is encapsulated here.

Design Decision (python-patterns §2 — Sync for CPU-bound):
    Cellpose inference is CPU/GPU-bound. The adapter is synchronous;
    the Application/GUI layer is responsible for running it off-thread.

Lazy-Loading Pattern (same as NuClickAdapter):
    Heavy imports (cellpose, torch, numpy, cv2) are deferred to first
    use to avoid DLL conflicts with PyQt6 on Windows.
"""

import logging
from typing import List, Tuple

from PIL.Image import Image

from app.domain.interfaces.batch_segmentation_model import IBatchSegmentationModel

logger = logging.getLogger(__name__)


class CellposeAdapter(IBatchSegmentationModel):
    """
    Adapter that wraps the Cellpose library to provide batch
    nucleus segmentation through the IBatchSegmentationModel port.

    Usage:
        adapter = CellposeAdapter(model_type="nuclei")
        polygons = adapter.segment(pil_image, diameter=30.0)
    """

    # Default Cellpose parameters (tunable per-instance)
    DEFAULT_FLOW_THRESHOLD = 0.4
    DEFAULT_CELLPROB_THRESHOLD = 0.0
    DEFAULT_MIN_SIZE = 15

    def __init__(
        self,
        model_type: str = "nuclei",
        gpu: bool = True,
        flow_threshold: float = DEFAULT_FLOW_THRESHOLD,
        cellprob_threshold: float = DEFAULT_CELLPROB_THRESHOLD,
        min_size: int = DEFAULT_MIN_SIZE,
    ):
        """
        Args:
            model_type: Cellpose model type ("nuclei", "cyto", "cyto2", etc.).
            gpu: Whether to attempt GPU acceleration.
            flow_threshold: Flow error threshold for mask quality filtering.
            cellprob_threshold: Cell probability threshold.
            min_size: Minimum mask area in pixels.
        """
        self._model_type = model_type
        self._gpu = gpu
        self._flow_threshold = flow_threshold
        self._cellprob_threshold = cellprob_threshold
        self._min_size = min_size

        # Lazy-loaded model instance
        self._model = None
        self._load_attempted = False

    # ── Domain Port Implementation ──────────────────────────────────────────

    @property
    def name(self) -> str:
        return f"Cellpose ({self._model_type})"

    def segment(
        self,
        image: Image,
        diameter: float | None = None,
        flow_threshold: float | None = None,
        cellprob_threshold: float | None = None,
    ) -> List[List[Tuple[int, int]]]:
        """
        Run Cellpose inference on the full image, returning polygons
        for every detected object.

        Args:
            image: PIL Image (RGB).
            diameter: Expected nucleus diameter in pixels.
                      None = Cellpose auto-estimates.
            flow_threshold: Override flow error threshold (None = use default).
            cellprob_threshold: Override cell probability threshold (None = use default).

        Returns:
            List of polygon boundaries. Each polygon is [(x, y), ...].
        """
        self._ensure_model_loaded()

        if self._model is None:
            logger.warning("Cellpose model not loaded. Returning empty.")
            return []

        import numpy as np
        import cv2

        # Use runtime overrides or fall back to instance defaults
        _flow = flow_threshold if flow_threshold is not None else self._flow_threshold
        _cellprob = cellprob_threshold if cellprob_threshold is not None else self._cellprob_threshold

        logger.info(
            "Running Cellpose (%s) on image %s, diameter=%s, flow=%.2f, cellprob=%.1f",
            self._model_type, image.size, diameter, _flow, _cellprob,
        )

        # 1. PIL → numpy RGB (H, W, 3)
        if image.mode != "RGB":
            image = image.convert("RGB")
        img_np = np.asarray(image)

        # 2. H&E pre-processing: extract and invert the blue channel
        #    In H&E staining, hematoxylin stains nuclei and absorbs
        #    strongly in the blue channel. Inverting makes nuclei appear
        #    bright on a dark background, which Cellpose detects better.
        blue_channel = img_np[:, :, 2].astype(np.float32)
        inverted = 255.0 - blue_channel
        # Normalize to 0-255 range
        inv_min, inv_max = inverted.min(), inverted.max()
        if inv_max > inv_min:
            inverted = ((inverted - inv_min) / (inv_max - inv_min) * 255.0)
        img_processed = inverted.astype(np.uint8)

        # 3. Run Cellpose evaluation on pre-processed single-channel image
        masks, flows, styles = self._model.eval(
            img_processed,
            diameter=diameter,
            flow_threshold=_flow,
            cellprob_threshold=_cellprob,
            min_size=self._min_size,
            channels=[0, 0],  # grayscale (already preprocessed)
        )

        logger.info("Cellpose detected %d objects.", masks.max() if masks.size else 0)

        # 3. Convert label masks → contour polygons
        polygons = self._masks_to_polygons(masks)

        logger.info("Extracted %d polygons from masks.", len(polygons))
        return polygons

    # ── Private Methods ─────────────────────────────────────────────────────

    def _ensure_model_loaded(self) -> None:
        """Lazy-load the Cellpose model on first use.

        Same rationale as NuClickAdapter: importing cellpose at startup
        can conflict with PyQt6 DLL loading order on Windows.
        """
        if self._load_attempted:
            return
        self._load_attempted = True
        self._load_model()

    def _load_model(self) -> None:
        """Import cellpose and instantiate the CellposeModel."""
        try:
            from cellpose import models as cp_models

            self._model = cp_models.CellposeModel(
                model_type=self._model_type,
                gpu=self._gpu,
            )
            logger.info(
                "Cellpose model '%s' loaded (gpu=%s).",
                self._model_type, self._gpu,
            )
        except Exception as e:
            logger.error("Failed to load Cellpose model: %s", e)
            self._model = None

    @staticmethod
    def _masks_to_polygons(
        masks,
    ) -> List[List[Tuple[int, int]]]:
        """Convert a Cellpose label matrix into a list of polygon contours.

        Args:
            masks: 2D numpy array where each unique non-zero label is one object.

        Returns:
            List of polygons, each polygon = [(x, y), ...].
        """
        import numpy as np
        import cv2

        polygons: List[List[Tuple[int, int]]] = []
        if masks is None or masks.size == 0:
            return polygons

        labels = np.unique(masks)
        labels = labels[labels != 0]  # skip background

        for label in labels:
            # Isolate single object
            binary = (masks == label).astype(np.uint8) * 255

            contours, _ = cv2.findContours(
                binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
            )
            if not contours:
                continue

            # Take the largest contour for this label
            largest = max(contours, key=cv2.contourArea)
            if cv2.contourArea(largest) < 4:
                continue  # skip degenerate contours

            poly = [(int(pt[0][0]), int(pt[0][1])) for pt in largest]
            if len(poly) >= 3:
                polygons.append(poly)

        return polygons
