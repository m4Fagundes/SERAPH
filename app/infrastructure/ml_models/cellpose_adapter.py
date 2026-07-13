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
import time
from typing import List, Tuple, Optional

from PIL.Image import Image

from app.domain.interfaces.batch_segmentation_model import IBatchSegmentationModel
from app.infrastructure.config.performance_config import get_performance_config

logger = logging.getLogger(__name__)


class CellposeAdapter(IBatchSegmentationModel):
    """
    Adapter that wraps the Cellpose library to provide batch
    nucleus segmentation through the IBatchSegmentationModel port.

    Usage:
        adapter = CellposeAdapter(model_type="cpsam")
        polygons = adapter.segment(pil_image, diameter=30.0)
    """

    # Default Cellpose parameters (tunable per-instance)
    DEFAULT_FLOW_THRESHOLD = 0.4
    DEFAULT_CELLPROB_THRESHOLD = 0.0
    DEFAULT_MIN_SIZE = 15

    def __init__(
        self,
        model_type: str = "cpsam",
        gpu: Optional[bool] = None,  # None = use auto-detect configuration
        flow_threshold: float = DEFAULT_FLOW_THRESHOLD,
        cellprob_threshold: float = DEFAULT_CELLPROB_THRESHOLD,
        min_size: int = DEFAULT_MIN_SIZE,
        config_override: Optional[dict] = None,
        device_id: Optional[int] = None,
    ):
        """
        Args:
            model_type: Cellpose model type ("cpsam", "nuclei", "cyto", "cyto2", etc.).
            gpu: Whether to attempt GPU acceleration. None = auto-detect from config.
            flow_threshold: Flow error threshold for mask quality filtering.
            cellprob_threshold: Cell probability threshold.
            min_size: Minimum mask area in pixels.
            config_override: Override specific config values.
            device_id: Optional CUDA device index to pin this adapter to.
        """
        self._model_type = model_type
        self._device_id = device_id

        # Load performance configuration
        self._config = get_performance_config()

        # Apply overrides if provided
        if config_override:
            # We would need a way to apply overrides here
            # For now, just log them
            logger.info("Config overrides provided: %s", config_override)

        def _runtime_gpu_available() -> bool:
            if self._config.disable_gpu or self._config.force_cpu_only:
                return False

            from app.infrastructure.config.device import gpu_available

            return gpu_available()

        # Decide whether to use GPU (automatic or manual configuration)
        if gpu is None:
            # Use automatic configuration
            self._gpu = self._config.cellpose.use_gpu and not self._config.force_cpu_only
            logger.info("Auto GPU decision: %s (config.use_gpu=%s, force_cpu_only=%s)",
                       self._gpu, self._config.cellpose.use_gpu, self._config.force_cpu_only)
        else:
            # Manual override - If the user explicitly requested, we respect it (even if the detector says otherwise)
            self._gpu = gpu
            if gpu and self._config.force_cpu_only:
                logger.warning("GPU requested manually despite force_cpu_only recommendation. Attempting to use GPU...")

        if self._gpu and not _runtime_gpu_available():
            logger.warning(
                "GPU was requested, but the current PyTorch runtime does not expose CUDA/MPS. Falling back to CPU."
            )
            self._gpu = False

        self._flow_threshold = flow_threshold
        self._cellprob_threshold = cellprob_threshold
        self._min_size = min_size
        self._last_probability_map = None
        self._last_instance_map = None

        # Performance settings
        self._batch_size = self._config.cellpose.batch_size
        self._timeout_seconds = self._config.cellpose.timeout_seconds
        self._max_tile_size = self._config.cellpose.max_tile_size_pixels
        self._memory_limit_mb = self._config.cellpose.memory_limit_mb

        logger.info(
            "CellposeAdapter initialized: model=%s, gpu=%s, batch_size=%d, "
            "timeout=%ds, max_tile=%dpx",
            model_type, self._gpu, self._batch_size,
            self._timeout_seconds, self._max_tile_size
        )

        # Lazy-loaded model instance
        self._model = None
        self._load_attempted = False

    # ── Domain Port Implementation ──────────────────────────────────────────

    @property
    def name(self) -> str:
        return f"Cellpose ({self._model_type})"

    def _check_memory_usage(self) -> bool:
        """Checks if memory usage is within limits."""
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)

            if memory_mb > self._memory_limit_mb:
                logger.warning(
                    "Memory usage %.1f MB exceeds limit %d MB. Consider reducing tile size.",
                    memory_mb, self._memory_limit_mb
                )
                return False
            return True
        except ImportError:
            logger.debug("psutil not available, skipping memory check")
            return True
        except Exception as e:
            logger.warning("Failed to check memory usage: %s", e)
            return True

    def _split_large_image(self, image) -> List[tuple]:
        """
        Splits a large image into smaller tiles for Cellpose processing.

        Returns:
            List of tuples (tile, offset_x, offset_y)
        """
        from PIL import Image as PILImage
        import numpy as np

        # Determine dimensions based on image type
        if isinstance(image, Image):
            width, height = image.size
            is_pil = True
        elif isinstance(image, np.ndarray):
            # NumPy array: (height, width, channels) ou (height, width)
            if len(image.shape) == 3:
                height, width = image.shape[:2]
            else:
                height, width = image.shape
            is_pil = False
        else:
            raise TypeError(f"Unsupported image type: {type(image)}. Expected PIL Image or NumPy array.")

        max_size = self._max_tile_size

        if width <= max_size and height <= max_size:
            return [(image, 0, 0)]

        logger.info(
            "Splitting large image %dx%d (max tile size: %dpx)",
            width, height, max_size
        )

        tiles = []
        for y in range(0, height, max_size):
            for x in range(0, width, max_size):
                tile_width = min(max_size, width - x)
                tile_height = min(max_size, height - y)

                if tile_width < 50 or tile_height < 50:
                    continue  # Very small tile

                if is_pil:
                    tile = image.crop((x, y, x + tile_width, y + tile_height))
                else:
                    # NumPy array slicing
                    tile = image[y:y + tile_height, x:x + tile_width]

                tiles.append((tile, x, y))  # Save offset for reconstruction

        logger.info("Split into %d tiles", len(tiles))
        return tiles

    def segment(
        self,
        image,
        diameter: float | None = None,
        flow_threshold: float | None = None,
        cellprob_threshold: float | None = None,
    ) -> List[List[Tuple[int, int]]]:
        """
        Run Cellpose inference on the full image, returning polygons
        for every detected object.

        Args:
            image: PIL Image (RGB) or NumPy array (H, W, 3) or (H, W).
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

        # Check memory usage before starting
        if not self._check_memory_usage():
            logger.warning("High memory usage detected. Consider reducing tile size.")

        # Use runtime overrides or fall back to instance defaults
        _flow = flow_threshold if flow_threshold is not None else self._flow_threshold
        _cellprob = cellprob_threshold if cellprob_threshold is not None else self._cellprob_threshold

        # ── Tiled path (calls _segment_single_image directly) ───────────
        if self._config.cellpose.split_large_tiles:
            tiles_with_offsets = self._split_large_image(image)
            if len(tiles_with_offsets) > 1:
                return self._segment_tiled_image(
                    tiles_with_offsets, diameter, _flow, _cellprob,
                )

        # ── Single-image path ───────────────────────────────────────────
        import concurrent.futures

        # Log image size
        img_size_str = self._format_image_size(image)
        logger.info(
            "Running Cellpose (%s) on image %s, diameter=%s, flow=%.2f, cellprob=%.1f (timeout=%ds)",
            self._model_type, img_size_str, diameter, _flow, _cellprob, self._timeout_seconds,
        )

        # Clear CUDA cache proactively to maximise available VRAM
        self._clear_cuda_cache()

        # Execute with timeout using ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self._segment_single_image,
                image, diameter, _flow, _cellprob,
            )
            try:
                polygons = future.result(timeout=self._timeout_seconds)
                logger.info("Cellpose completed successfully in time")
                return polygons
            except concurrent.futures.TimeoutError:
                logger.error("Cellpose segmentation timed out after %d seconds", self._timeout_seconds)
                future.cancel()
                return []
            except Exception as e:
                # Check if it is a GPU failure (CUDA OOM or MPS unsupported op) — retry on CPU if so
                if self._gpu and self._is_gpu_failure(e):
                    return self._retry_on_cpu(
                        image, diameter, _flow, _cellprob, original_error=e,
                    )
                logger.error("Cellpose segmentation failed: %s", e)
                return []

    def _segment_tiled_image(
        self,
        tiles_with_offsets: List[tuple],
        diameter: float | None,
        flow_threshold: float,
        cellprob_threshold: float,
    ) -> List[List[Tuple[int, int]]]:
        """Segments an image split into tiles and combines results.

        IMPORTANT: calls ``_segment_single_image`` directly to avoid
        re-applying resampling or re-splitting (which ``segment()``
        would do).
        """
        logger.info("Segmenting tiled image with %d tiles", len(tiles_with_offsets))

        all_polygons = []
        completed = 0
        failed = 0

        for tile, offset_x, offset_y in tiles_with_offsets:
            try:
                self._clear_cuda_cache()

                try:
                    tile_polygons = self._segment_single_image(
                        tile, diameter, flow_threshold, cellprob_threshold,
                    )
                except Exception as e:
                    if self._gpu and self._is_gpu_failure(e):
                        tile_polygons = self._retry_on_cpu(
                            tile, diameter, flow_threshold, cellprob_threshold,
                            original_error=e,
                        )
                    else:
                        raise

                # Adjust coordinates with tile offset
                for polygon in tile_polygons:
                    adjusted_polygon = [(x + offset_x, y + offset_y) for (x, y) in polygon]
                    all_polygons.append(adjusted_polygon)

                completed += 1
                logger.debug("Tile at (%d, %d) completed: %d polygons", offset_x, offset_y, len(tile_polygons))

            except Exception as e:
                failed += 1
                logger.warning("Failed to segment tile at (%d, %d): %s", offset_x, offset_y, e)

        logger.info("Tiled segmentation complete: %d tiles succeeded, %d failed, %d total polygons",
                   completed, failed, len(all_polygons))
        return all_polygons

    def _segment_single_image(
        self,
        image,
        diameter: float | None,
        flow_threshold: float,
        cellprob_threshold: float,
    ) -> List[List[Tuple[int, int]]]:
        """Segments a single image (internal method without timeout)."""
        import numpy as np
        import cv2
        from PIL import Image as PILImage

        # 1. Convert to NumPy array if necessary
        if isinstance(image, Image):
            if image.mode != "RGB":
                image = image.convert("RGB")
            img_np = np.asarray(image)
        elif isinstance(image, np.ndarray):
            img_np = image
        else:
            raise TypeError(f"Unsupported image type: {type(image)}. Expected PIL Image or NumPy array.")

        # 2. Pass the original RGB image to Cellpose.
        #    For H&E images, Cellpose officially recommends using the 'cpsam' model 
        #    with channels=[3,0] (which tells it to use the Blue channel, where hematoxylin 
        #    is most prominent). Custom per-tile min-max normalization causes severe 
        #    artifacts (like segmenting whole cells) because it stretches the contrast 
        #    unpredictably depending on the tile's content.
        internal_batch = 8
        
        # Determine channels based on image shape
        if len(img_np.shape) == 3 and img_np.shape[2] >= 3:
            # Color image: Blue channel (3) for nuclei, 0 for secondary
            channels = [3, 0]
        else:
            # Grayscale image
            channels = [0, 0]
        
        masks, flows, styles = self._model.eval(
            img_np,
            channels=channels,
            diameter=diameter,
            flow_threshold=flow_threshold,
            cellprob_threshold=cellprob_threshold,
            min_size=self._min_size,
            batch_size=internal_batch,
        )

        try:
            import numpy as _np
            self._last_instance_map = _np.asarray(masks).astype(_np.uint32, copy=False)
            cprob = _np.asarray(flows[2], dtype=_np.float32)
            self._last_probability_map = cprob if cprob.ndim == 2 else None
            logger.info(
                "Cellpose probability map captured: shape=%s dtype=%s",
                cprob.shape, cprob.dtype,
            )
        except Exception as _e:
            logger.warning("Could not capture Cellpose probability map: %s", _e)
            self._last_probability_map = None
            self._last_instance_map = None

        logger.info("Cellpose detected %d objects.", masks.max() if masks.size else 0)

        # 4. Convert label masks → contour polygons
        polygons = self._masks_to_polygons(masks)

        logger.info("Extracted %d polygons from masks.", len(polygons))
        return polygons

    def probability_map(self):
        return self._last_probability_map

    def instance_map(self):
        return self._last_instance_map

    # ── Private Methods ─────────────────────────────────────────────────────

    @staticmethod
    def _is_gpu_failure(exc: Exception) -> bool:
        """Returns True if exc is a GPU error that should trigger CPU fallback.

        Covers:
        - CUDA and MPS out-of-memory errors
        - cuDNN errors
        - MPS NotImplementedError for unsupported ops (e.g., sparse tensors in
          Cellpose 4.x mask creation on Apple Silicon — see Cellpose issue #1063)
        """
        from app.infrastructure.config.device import is_gpu_failure

        return is_gpu_failure(exc)

    @staticmethod
    def _clear_cuda_cache() -> None:
        """Frees unused GPU memory (CUDA or MPS) so the next allocation has headroom."""
        try:
            import gc

            from app.infrastructure.config.device import empty_cache

            empty_cache()
            gc.collect()
        except Exception:  # pragma: no cover
            pass

    def _retry_on_cpu(
        self,
        image,
        diameter: float | None,
        flow_threshold: float,
        cellprob_threshold: float,
        *,
        original_error: Exception,
    ) -> list:
        """Fallback: reload the model on CPU and re-run the segmentation."""
        logger.warning(
            "GPU failure detected (%s). Clearing GPU memory and retrying on CPU…",
            original_error,
        )
        self._clear_cuda_cache()

        # Reload model on CPU
        try:
            from cellpose import models as cp_models
            import torch

            self._gpu = False
            self._model = cp_models.CellposeModel(
                pretrained_model=self._model_type,
                gpu=False,
                device=torch.device("cpu"),
                use_bfloat16=False,
            )
            logger.warning(
                "Cellpose model permanently reloaded on CPU for OOM fallback. "
                "Subsequent processing will be very slow."
            )
        except Exception as reload_err:
            logger.error("Failed to reload Cellpose on CPU: %s", reload_err)
            return []

        # Re-run segmentation (no timeout wrapper — CPU is slower but won't OOM)
        try:
            polygons = self._segment_single_image(
                image, diameter, flow_threshold, cellprob_threshold
            )
            logger.info(
                "CPU fallback succeeded: %d polygons detected.", len(polygons)
            )
            return polygons
        except Exception as cpu_err:
            logger.error("CPU fallback also failed: %s", cpu_err)
            return []

    @staticmethod
    def _format_image_size(image) -> str:
        """Returns a human-readable size string for logging."""
        import numpy as np
        if isinstance(image, Image):
            return f"{image.size}"
        elif isinstance(image, np.ndarray):
            if len(image.shape) == 3:
                return f"({image.shape[1]}x{image.shape[0]}x{image.shape[2]})"
            else:
                return f"({image.shape[1]}x{image.shape[0]})"
        return str(type(image))

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
            import torch
            from app.infrastructure.config.device import describe_device, select_device

            # Pass the device explicitly rather than letting Cellpose guess from
            # gpu=True: on Apple Silicon its own probe is what used to leave the
            # model on the CPU.
            device = select_device(use_gpu=self._gpu, device_id=self._device_id)
            if device.type != "cpu":
                logger.info("Using explicit device for Cellpose: %s", describe_device(device))

            try:
                self._model = cp_models.CellposeModel(
                    pretrained_model=self._model_type,
                    gpu=self._gpu,
                    device=device,
                    use_bfloat16=False,
                )
                logger.info(
                    "Cellpose model '%s' loaded (gpu=%s).",
                    self._model_type, self._gpu,
                )
            except Exception as e:
                # If GPU loading fails, retry on CPU so the app still works.
                if self._gpu:
                    logger.warning("Failed to load Cellpose on GPU (%s). Retrying on CPU (gpu=False)...", e)
                    self._gpu = False
                    self._model = cp_models.CellposeModel(
                        pretrained_model=self._model_type,
                        gpu=False,
                        device=torch.device("cpu"),
                        use_bfloat16=False,
                    )
                    logger.info("Cellpose model '%s' loaded successfully using CPU fallback.", self._model_type)
                else:
                    raise e
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
        import scipy.ndimage as ndi

        polygons: List[List[Tuple[int, int]]] = []
        if masks is None or masks.size == 0:
            return polygons

        h, w = masks.shape

        # Optimize: instead of checking masks == label on the entire 2D image
        # for every single label (which takes O(N * W * H) and freezes the CPU),
        # we find the tight bounding box for each label first.
        slices = ndi.find_objects(masks)

        for i, slc in enumerate(slices):
            if slc is None:
                continue
            
            label = i + 1
            # slc is a tuple: (slice(y1, y2), slice(x1, x2))
            min_y = slc[0].start
            min_x = slc[1].start

            # Isolate single object ONLY within its bounding box
            crop = masks[slc]
            binary = (crop == label).astype(np.uint8) * 255

            contours, _ = cv2.findContours(
                binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
            )
            if not contours:
                continue

            # Take the largest contour for this label
            largest = max(contours, key=cv2.contourArea)
            if cv2.contourArea(largest) < 4:
                continue  # skip degenerate contours

            # Re-add the bounding box offset to the contour coordinates
            poly = [(int(pt[0][0]) + min_x, int(pt[0][1]) + min_y) for pt in largest]

            if len(poly) >= 3:
                # Exclude nuclei that touch the tile edges
                touches_border = any(
                    x <= 0 or y <= 0 or x >= w - 1 or y >= h - 1
                    for x, y in poly
                )
                if touches_border:
                    continue
                polygons.append(poly)

        return polygons
