"""InstanSeg adapter — embedding-based nucleus instance segmentation.

Wraps the InstanSeg model (Goldsborough et al., 2024) as an
IBatchSegmentationModel. Unlike the HoVer-Net / SAM family, InstanSeg learns
per-pixel embeddings and groups them into instances — there is no binary
foreground threshold + watershed step.

Source checkout is expected at SERAPH/external/instanseg (clone of
https://github.com/instanseg/instanseg). Pretrained weights are downloaded
automatically on first use (brightfield_nuclei for H&E).
"""

import logging
from typing import List, Optional, Tuple

import numpy as np

from app.domain.interfaces.batch_segmentation_model import IBatchSegmentationModel
from app.infrastructure.external_repos import add_repo_to_path

logger = logging.getLogger(__name__)


class InstanSegAdapter(IBatchSegmentationModel):
    """Adapter wrapping InstanSeg as an IBatchSegmentationModel.

    Usage:
        adapter = InstanSegAdapter()                    # brightfield_nuclei, 0.25 µm/px
        polygons = adapter.segment(pil_image)
    """

    NAME = "InstanSeg"

    def __init__(
        self,
        model_type: str = "brightfield_nuclei",
        pixel_size: Optional[float] = 0.25,
        device: Optional[str] = None,
        gpu: Optional[bool] = None,
        polygon_epsilon: float = 1.5,
    ) -> None:
        """
        Args:
            model_type: InstanSeg pretrained model name (brightfield_nuclei for H&E).
            pixel_size: Microns per pixel of the input. 0.25 = 40x (dataset default).
                        InstanSeg rescales to its native pixel size internally.
            device: Explicit torch device ("cuda"/"cpu"). None = auto-detect.
            gpu: True/False to force GPU/CPU; None = auto.
            polygon_epsilon: approxPolyDP tolerance (px) to smooth the displayed
                contour. At pixel_size=0.25 the model segments at half resolution and
                nearest-upsamples 2x, giving a 2px staircase ("chifrinhos"); ~1.5 px
                removes it. Cosmetic only — the raw instance_map is unchanged.
        """
        self._model_type = model_type
        self._pixel_size = pixel_size
        self._device = device
        self._gpu = gpu
        self._polygon_epsilon = polygon_epsilon
        self._model = None
        self._load_attempted = False
        self._last_instance_map = None

    # ── IBatchSegmentationModel ──────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self.NAME

    def segment(
        self,
        image,
        diameter: float | None = None,
        flow_threshold: float | None = None,
        cellprob_threshold: float | None = None,
    ) -> List[List[Tuple[int, int]]]:
        """Detect all nuclei and return polygon boundaries.

        diameter/flow_threshold/cellprob_threshold are Cellpose-specific and unused.
        """
        self._ensure_model_loaded()
        if self._model is None:
            logger.warning("InstanSeg model not available — returning empty segmentation.")
            return []

        import torch

        if isinstance(image, np.ndarray):
            img_np = image if image.dtype == np.uint8 else (image * 255).astype(np.uint8)
            if img_np.ndim == 2:
                img_np = np.stack([img_np] * 3, axis=-1)
        else:
            img_np = np.array(image.convert("RGB"), dtype=np.uint8)

        self._last_instance_map = None
        try:
            tensor = torch.from_numpy(img_np).permute(2, 0, 1).float()  # C,H,W
            with torch.inference_mode():
                labels = self._model.eval_small_image(
                    tensor,
                    pixel_size=self._pixel_size,
                    target="nuclei",
                    normalise=True,
                    return_image_tensor=False,
                )
            label_map = np.asarray(labels).squeeze().astype(np.uint32)
            if label_map.ndim != 2:
                logger.warning("InstanSeg returned unexpected shape %s", label_map.shape)
                return []
            self._last_instance_map = label_map
        except Exception as exc:
            logger.error("InstanSeg inference failed: %s", exc, exc_info=True)
            self._last_instance_map = None
            self._clear_cuda_cache()
            return []

        polygons = self._label_map_to_polygons(label_map, self._polygon_epsilon)
        logger.info("InstanSeg detected %d nuclei", len(polygons))
        return polygons

    def probability_map(self):
        # InstanSeg is embedding-based — no foreground probability map.
        return None

    def instance_map(self):
        return self._last_instance_map

    def cleanup_after_segment(self) -> None:
        self._clear_cuda_cache()

    # ── Label map → polygons ──────────────────────────────────────────────────

    @staticmethod
    def _label_map_to_polygons(label_map: np.ndarray, epsilon: float = 1.5) -> List[List[Tuple[int, int]]]:
        try:
            import cv2
        except ImportError:
            logger.error("opencv-python not installed — cannot extract polygons.")
            return []

        polygons: List[List[Tuple[int, int]]] = []
        for uid in np.unique(label_map):
            if uid == 0:
                continue
            mask = (label_map == uid).astype(np.uint8)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            contour = max(contours, key=cv2.contourArea)
            # Smooth the pixel staircase ("chifrinhos") for display. Cosmetic only:
            # the raw instance_map (used by the benchmark/export) is untouched.
            if epsilon and epsilon > 0:
                contour = cv2.approxPolyDP(contour, epsilon, True)
            if len(contour) < 3:
                continue
            polygons.append([(int(pt[0][0]), int(pt[0][1])) for pt in contour])
        return polygons

    # ── Model loading ─────────────────────────────────────────────────────────

    def _ensure_model_loaded(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True
        add_repo_to_path("instanseg")
        try:
            from instanseg import InstanSeg
        except ImportError as exc:
            logger.error(
                "InstanSeg not found. Clone it into SERAPH/external/instanseg "
                "(https://github.com/instanseg/instanseg). Original error: %s", exc
            )
            return
        try:
            device = self._resolve_device()
            self._model = InstanSeg(self._model_type, device=device, verbosity=0)
            logger.info("InstanSeg ready: model=%s device=%s pixel_size=%s",
                        self._model_type, device, self._pixel_size)
        except Exception as exc:
            logger.error("Failed to load InstanSeg model: %s", exc, exc_info=True)
            self._model = None

    def _resolve_device(self) -> Optional[str]:
        if self._device is not None:
            return self._device
        try:
            from app.infrastructure.config.device import select_device_str

            return select_device_str(use_gpu=self._gpu)
        except Exception:
            return None  # let InstanSeg auto-choose

    @staticmethod
    def _clear_cuda_cache() -> None:
        try:
            import gc

            from app.infrastructure.config.device import empty_cache

            gc.collect()
            empty_cache()
        except Exception:
            pass
