"""
PathoSAMAdapter — Infrastructure adapter for Patho-SAM nucleus segmentation.

Implements IBatchSegmentationModel using micro_sam's automatic instance
segmentation (AIS) with histopathology-specific SAM models.

Model weights are downloaded automatically to the micro_sam cache directory
(~/.cache/micro_sam/ or equivalent) on first use — no manual download needed.

Supported model types:
    vit_b_histopathology — ViT-Base  (~375 MB, fastest)
    vit_l_histopathology — ViT-Large (~1.2 GB, balanced)
    vit_h_histopathology — ViT-Huge  (~2.5 GB, best quality)

Inference pipeline:
    1. Input image normalised to uint8 numpy HxWx3.
    2. micro_sam computes SAM image embeddings with tiling (384×384 + 64px halo).
    3. AIS (Automatic Instance Segmentation) decodes embeddings → integer label map.
    4. Each unique label ID extracted as a binary mask; cv2.findContours extracts polygon.
    5. Polygons returned in input-image-local coordinates.
"""

import logging
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from app.domain.interfaces.batch_segmentation_model import IBatchSegmentationModel

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PATHO_SAM_REPO = _ROOT / "patho-sam"
_MICRO_SAM_REPO = _ROOT / "micro-sam"
_TORCH_EM_REPO  = _ROOT / "torch-em"
_ELF_REPO       = _ROOT / "elf"

_MODEL_DISPLAY_NAMES = {
    "vit_b_histopathology": "PathoSAM (ViT-B)",
    "vit_l_histopathology": "PathoSAM (ViT-L)",
    "vit_h_histopathology": "PathoSAM (ViT-H)",
}


def _add_patho_sam_to_path() -> None:
    # elf and torch-em first — micro-sam imports from both at module level
    for repo in (_ELF_REPO, _TORCH_EM_REPO, _MICRO_SAM_REPO, _PATHO_SAM_REPO):
        if repo.exists():
            repo_str = str(repo)
            if repo_str not in sys.path:
                sys.path.insert(0, repo_str)
        else:
            logger.warning(
                "PathoSAM: expected repo not found at '%s' — "
                "run: git clone <url> from the SERAPH root", repo
            )


class PathoSAMAdapter(IBatchSegmentationModel):
    """
    Adapter wrapping micro_sam Patho-SAM AIS as an IBatchSegmentationModel.

    Usage:
        adapter = PathoSAMAdapter()                          # ViT-B (default)
        adapter = PathoSAMAdapter("vit_l_histopathology")    # ViT-L
        polygons = adapter.segment(pil_image)
    """

    def __init__(
        self,
        model_type: str = "vit_b_histopathology",
        checkpoint_path: Optional[str] = None,
        tile_shape: Tuple[int, int] = (384, 384),
        halo: Tuple[int, int] = (64, 64),
        gpu: Optional[bool] = None,
        batch_size: Optional[int] = None,
    ) -> None:
        """
        Args:
            model_type: One of the vit_{b,l,h}_histopathology variants.
            checkpoint_path: Explicit .pt checkpoint path. None = micro_sam auto-download.
            tile_shape: Tile size for tiled SAM embedding. (384, 384) per Patho-SAM defaults.
            halo: Overlap between tiles. (64, 64) per Patho-SAM defaults.
            gpu: True = force GPU, False = force CPU, None = auto-detect.
            batch_size: Patches per embedding batch. None = auto from VRAM.
        """
        self._model_type = model_type
        self._checkpoint_path = checkpoint_path
        self._tile_shape = tile_shape
        self._halo = halo
        self._batch_size = batch_size

        if gpu is None:
            self._use_gpu = self._runtime_gpu_available()
        else:
            self._use_gpu = gpu

        self._predictor = None
        self._segmenter = None
        self._device: Optional[str] = None
        self._load_attempted = False
        self._last_probability_map = None

        self._display_name = _MODEL_DISPLAY_NAMES.get(model_type, f"PathoSAM ({model_type})")

    # ── IBatchSegmentationModel ──────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._display_name

    def segment(
        self,
        image,
        diameter: float | None = None,
        flow_threshold: float | None = None,
        cellprob_threshold: float | None = None,
    ) -> List[List[Tuple[int, int]]]:
        """
        Detect all nuclei and return polygon boundaries.

        diameter/flow_threshold/cellprob_threshold are Cellpose-specific and unused.
        """
        self._ensure_model_loaded()
        if self._predictor is None or self._segmenter is None:
            logger.warning("PathoSAM model not available — returning empty segmentation.")
            return []

        if isinstance(image, np.ndarray):
            img_np = image if image.dtype == np.uint8 else (image * 255).astype(np.uint8)
        else:
            img_np = np.array(image.convert("RGB"), dtype=np.uint8)

        H, W = img_np.shape[:2]
        logger.info(
            "PathoSAM.segment: image=%dx%d  tile=%s  halo=%s  device=%s",
            W, H, self._tile_shape, self._halo, self._device,
        )
        self._last_probability_map = None

        try:
            from micro_sam.automatic_segmentation import automatic_instance_segmentation

            batch_size = self._batch_size or self._auto_batch_size()

            result = automatic_instance_segmentation(
                predictor=self._predictor,
                segmenter=self._segmenter,
                input_path=img_np,
                output_path=None,
                embedding_path=None,
                ndim=2,
                tile_shape=self._tile_shape,
                halo=self._halo,
                verbose=False,
                output_mode="instance_segmentation",
                return_embeddings=False,
                batch_size=batch_size,
            )

            # micro_sam versions differ: some return (masks, embeddings), others just masks
            label_map = result[0] if isinstance(result, tuple) else result
            self._capture_probability_map()

        except Exception as exc:
            logger.error("PathoSAM inference failed: %s", exc, exc_info=True)
            self._last_probability_map = None
            return []

        polygons = self._label_map_to_polygons(label_map)
        logger.info("PathoSAM detected %d nuclei", len(polygons))
        return polygons

    def probability_map(self):
        return self._last_probability_map

    def _capture_probability_map(self) -> None:
        """Capture micro_sam AIS foreground probabilities from the last run."""
        if self._segmenter is None:
            self._last_probability_map = None
            return

        try:
            state = self._segmenter.get_state()
            foreground = state.get("foreground")
            if foreground is None:
                self._last_probability_map = None
                return

            prob = np.asarray(foreground, dtype=np.float32)
            if prob.ndim != 2:
                logger.warning("PathoSAM probability map has unexpected shape: %s", prob.shape)
                self._last_probability_map = None
                return

            self._last_probability_map = np.clip(prob, 0.0, 1.0)
            logger.info(
                "PathoSAM probability map captured: shape=%s dtype=%s",
                self._last_probability_map.shape,
                self._last_probability_map.dtype,
            )
        except Exception as exc:
            logger.warning("Could not capture PathoSAM probability map: %s", exc)
            self._last_probability_map = None

    # ── Label map → polygons ──────────────────────────────────────────────────

    @staticmethod
    def _label_map_to_polygons(label_map: np.ndarray) -> List[List[Tuple[int, int]]]:
        """Convert an integer instance label map to a list of (x, y) polygon contours."""
        try:
            import cv2
        except ImportError:
            logger.error(
                "opencv-python not installed — cannot extract polygons. "
                "Install with: pip install opencv-python-headless"
            )
            return []

        unique_ids = np.unique(label_map)
        unique_ids = unique_ids[unique_ids > 0]

        polygons: List[List[Tuple[int, int]]] = []
        for uid in unique_ids:
            mask = (label_map == uid).astype(np.uint8)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            contour = max(contours, key=cv2.contourArea)
            if len(contour) < 3:
                continue
            polygon = [(int(pt[0][0]), int(pt[0][1])) for pt in contour]
            polygons.append(polygon)

        return polygons

    # ── Model loading ─────────────────────────────────────────────────────────

    def _ensure_model_loaded(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True
        _add_patho_sam_to_path()
        self._load_model()

    def _load_model(self) -> None:
        # micro-sam imports conda-only helper stacks at module import time.
        # Keep the app on the inference-only path supported by pip/Windows.
        from app.infrastructure.ml_models._patho_sam_compat import inject as _inject_patho_sam_compat
        _inject_patho_sam_compat(_TORCH_EM_REPO)

        try:
            from micro_sam.automatic_segmentation import get_predictor_and_segmenter
        except ImportError as exc:
            logger.error(
                "micro_sam is not installed. Install with: pip install micro-sam\n"
                "Original error: %s", exc,
            )
            return

        try:
            self._device = self._select_device()
            logger.info("PathoSAM: loading %s on %s", self._model_type, self._device)

            self._predictor, self._segmenter = get_predictor_and_segmenter(
                model_type=self._model_type,
                checkpoint=self._checkpoint_path,
                device=self._device,
                segmentation_mode="ais",
                is_tiled=True,
            )

            logger.info(
                "PathoSAM ready: model=%s  device=%s", self._model_type, self._device
            )
        except Exception as exc:
            logger.error("Failed to load PathoSAM model: %s", exc, exc_info=True)
            self._predictor = None
            self._segmenter = None

    # ── Device helpers ────────────────────────────────────────────────────────

    def _select_device(self) -> str:
        import torch

        try:
            from app.infrastructure.config.gpu_selector import get_best_cuda_device
            if self._use_gpu and torch.cuda.is_available():
                idx = get_best_cuda_device()
                if idx is not None:
                    logger.info("PathoSAM using CUDA device %d", idx)
                    # micro_sam only accepts "cuda", not indexed strings like "cuda:0".
                    # The app's GPU selector has already isolated the chosen GPU.
                    return "cuda"
        except Exception:
            pass

        if self._use_gpu and torch.cuda.is_available():
            return "cuda"

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"

        return "cpu"

    @staticmethod
    def _runtime_gpu_available() -> bool:
        try:
            import torch
            if torch.cuda.is_available() and torch.cuda.device_count() > 0:
                return True
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return True
        except ImportError:
            pass
        return False

    @staticmethod
    def _auto_batch_size() -> int:
        try:
            import torch
            if torch.cuda.is_available():
                _, vram = torch.cuda.mem_get_info()
                vram_gb = vram / 1e9
                if vram_gb > 80:
                    return 30
                elif vram_gb > 30:
                    return 10
                elif vram_gb > 14:
                    return 5
                elif vram_gb > 8:
                    return 3
        except Exception:
            pass
        return 1
