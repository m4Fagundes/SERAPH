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
        gpu: Optional[bool] = None,  # None = usar configuração automática
        flow_threshold: float = DEFAULT_FLOW_THRESHOLD,
        cellprob_threshold: float = DEFAULT_CELLPROB_THRESHOLD,
        min_size: int = DEFAULT_MIN_SIZE,
        config_override: Optional[dict] = None,
    ):
        """
        Args:
            model_type: Cellpose model type ("nuclei", "cyto", "cyto2", etc.).
            gpu: Whether to attempt GPU acceleration. None = auto-detect from config.
            flow_threshold: Flow error threshold for mask quality filtering.
            cellprob_threshold: Cell probability threshold.
            min_size: Minimum mask area in pixels.
            config_override: Override specific config values.
        """
        self._model_type = model_type

        # Carregar configuração de performance
        self._config = get_performance_config()

        # Aplicar overrides se fornecidos
        if config_override:
            # Aqui precisaríamos de uma forma de aplicar overrides
            # Por enquanto, apenas logamos
            logger.info("Config overrides provided: %s", config_override)

        # Decidir se usa GPU (configuração automática ou manual)
        if gpu is None:
            # Usar configuração automática
            self._gpu = self._config.cellpose.use_gpu and not self._config.force_cpu_only
            logger.info("Auto GPU decision: %s (config.use_gpu=%s, force_cpu_only=%s)",
                       self._gpu, self._config.cellpose.use_gpu, self._config.force_cpu_only)
        else:
            # Override manual - Se o usuário pediu explicitamente, respeitamos (mesmo que o detector diga o contrário)
            self._gpu = gpu
            if gpu and self._config.force_cpu_only:
                logger.warning("GPU requested manually despite force_cpu_only recommendation. Attempting to use GPU...")

        self._flow_threshold = flow_threshold
        self._cellprob_threshold = cellprob_threshold
        self._min_size = min_size

        # Configurações de performance
        self._batch_size = self._config.cellpose.batch_size
        self._resample_factor = self._config.cellpose.resample_factor
        self._timeout_seconds = self._config.cellpose.timeout_seconds
        self._max_tile_size = self._config.cellpose.max_tile_size_pixels
        self._memory_limit_mb = self._config.cellpose.memory_limit_mb

        logger.info(
            "CellposeAdapter initialized: model=%s, gpu=%s, batch_size=%d, "
            "resample=%.2f, timeout=%ds, max_tile=%dpx",
            model_type, self._gpu, self._batch_size, self._resample_factor,
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
        """Verifica se o uso de memória está dentro dos limites."""
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

    def _apply_resample_if_needed(self, image):
        """Aplica downsampling se configurado e necessário.

        Args:
            image: PIL Image ou NumPy array

        Returns:
            Imagem redimensionada (mesmo tipo da entrada)
        """
        from PIL import Image as PILImage
        import numpy as np
        import cv2

        if self._resample_factor >= 1.0:
            return image

        # Determinar dimensões baseado no tipo de imagem
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

        new_width = int(width * self._resample_factor)
        new_height = int(height * self._resample_factor)

        if new_width < 100 or new_height < 100:
            logger.warning(
                "Resample factor %.2f would create image too small (%dx%d). Using original.",
                self._resample_factor, new_width, new_height
            )
            return image

        logger.info(
            "Resampling image from %dx%d to %dx%d (factor=%.2f)",
            width, height, new_width, new_height, self._resample_factor
        )

        if is_pil:
            return image.resize((new_width, new_height), PILImage.Resampling.LANCZOS)
        else:
            # Redimensionar NumPy array usando OpenCV
            return cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)

    def _split_large_image(self, image) -> List[tuple]:
        """Divide imagens grandes em tiles menores se necessário.

        Args:
            image: PIL Image ou NumPy array (H, W, 3) ou (H, W)

        Returns:
            Lista de tuplas (tile, offset_x, offset_y)
        """
        from PIL import Image as PILImage
        import numpy as np

        # Determinar dimensões baseado no tipo de imagem
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
                    continue  # Tile muito pequeno

                if is_pil:
                    tile = image.crop((x, y, x + tile_width, y + tile_height))
                else:
                    # NumPy array slicing
                    tile = image[y:y + tile_height, x:x + tile_width]

                tiles.append((tile, x, y))  # Guardar offset para reconstrução

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
            image: PIL Image (RGB) ou NumPy array (H, W, 3) ou (H, W).
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

        # Verificar uso de memória antes de começar
        if not self._check_memory_usage():
            logger.warning("High memory usage detected. Consider reducing image size.")

        # Aplicar resample se configurado
        image = self._apply_resample_if_needed(image)

        # Dividir imagem grande se necessário
        if self._config.cellpose.split_large_tiles:
            tiles_with_offsets = self._split_large_image(image)
            if len(tiles_with_offsets) > 1:
                return self._segment_tiled_image(tiles_with_offsets, diameter,
                                                flow_threshold, cellprob_threshold)

        # Processamento normal (imagem única) com timeout
        import concurrent.futures
        import numpy as np
        import cv2

        # Use runtime overrides or fall back to instance defaults
        _flow = flow_threshold if flow_threshold is not None else self._flow_threshold
        _cellprob = cellprob_threshold if cellprob_threshold is not None else self._cellprob_threshold

        # Log image size based on type
        from PIL import Image as PILImage
        import numpy as np

        if isinstance(image, Image):
            img_size_str = f"{image.size}"
        elif isinstance(image, np.ndarray):
            if len(image.shape) == 3:
                img_size_str = f"({image.shape[1]}x{image.shape[0]}x{image.shape[2]})"
            else:
                img_size_str = f"({image.shape[1]}x{image.shape[0]})"
        else:
            img_size_str = str(type(image))

        logger.info(
            "Running Cellpose (%s) on image %s, diameter=%s, flow=%.2f, cellprob=%.1f (timeout=%ds)",
            self._model_type, img_size_str, diameter, _flow, _cellprob, self._timeout_seconds
        )

        # Executar com timeout usando ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self._segment_single_image,
                image, diameter, _flow, _cellprob
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
                logger.error("Cellpose segmentation failed: %s", e)
                return []

    def _segment_tiled_image(
        self,
        tiles_with_offsets: List[tuple],
        diameter: float | None,
        flow_threshold: float | None,
        cellprob_threshold: float | None,
    ) -> List[List[Tuple[int, int]]]:
        """Segmenta imagem dividida em tiles e combina resultados."""
        logger.info("Segmenting tiled image with %d tiles", len(tiles_with_offsets))

        all_polygons = []
        completed = 0
        failed = 0

        for tile, offset_x, offset_y in tiles_with_offsets:
            try:
                # Segmentar tile individual
                tile_polygons = self.segment(tile, diameter, flow_threshold, cellprob_threshold)

                # Ajustar coordenadas com offset
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
        """Segmenta uma única imagem (método interno sem timeout)."""
        import numpy as np
        import cv2
        from PIL import Image as PILImage

        # 1. Converter para NumPy array se necessário
        if isinstance(image, Image):
            if image.mode != "RGB":
                image = image.convert("RGB")
            img_np = np.asarray(image)
        elif isinstance(image, np.ndarray):
            img_np = image
        else:
            raise TypeError(f"Unsupported image type: {type(image)}. Expected PIL Image or NumPy array.")

        # 2. H&E pre-processing: extract and invert the blue channel
        #    In H&E staining, hematoxylin stains nuclei and absorbs
        #    strongly in the blue channel. Inverting makes nuclei appear
        #    bright on a dark background, which Cellpose detects better.
        if len(img_np.shape) == 3 and img_np.shape[2] >= 3:
            # Imagem colorida (RGB ou RGBA) - extrair canal azul
            blue_channel = img_np[:, :, 2].astype(np.float32)
        elif len(img_np.shape) == 2:
            # Imagem em escala de cinza - usar diretamente
            blue_channel = img_np.astype(np.float32)
        else:
            raise ValueError(f"Unsupported image shape: {img_np.shape}. Expected (H, W, 3), (H, W, 4), or (H, W).")

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
            flow_threshold=flow_threshold,
            cellprob_threshold=cellprob_threshold,
            min_size=self._min_size,
            channels=[0, 0],  # grayscale (already preprocessed)
            batch_size=128,    # Socar carga na GPU (default é 8)
        )

        logger.info("Cellpose detected %d objects.", masks.max() if masks.size else 0)

        # 4. Convert label masks → contour polygons
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

            try:
                self._model = cp_models.CellposeModel(
                    model_type=self._model_type,
                    gpu=self._gpu,
                )
                logger.info(
                    "Cellpose model '%s' loaded (gpu=%s).",
                    self._model_type, self._gpu,
                )
            except Exception as e:
                # Se falhar porque a GPU (MPS no Mac) não suporta BFloat16 do modelo novo, faz um fallback pra CPU
                if self._gpu and ("BFloat16" in str(e) or "MPS" in str(e)):
                    logger.warning("Failed to load Cellpose on GPU (%s). Retrying on CPU (gpu=False)...", e)
                    self._gpu = False
                    self._model = cp_models.CellposeModel(
                        model_type=self._model_type,
                        gpu=False,
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
                # Excluir núcleos que tocam as bordas do tile
                touches_border = any(
                    x <= 0 or y <= 0 or x >= w - 1 or y >= h - 1
                    for x, y in poly
                )
                if touches_border:
                    continue
                polygons.append(poly)

        return polygons
