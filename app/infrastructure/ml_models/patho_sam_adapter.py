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
from contextlib import nullcontext
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from app.domain.interfaces.batch_segmentation_model import IBatchSegmentationModel
from app.infrastructure.external_repos import repo_path

logger = logging.getLogger(__name__)

_PATHO_SAM_REPO = repo_path("patho-sam")
_MICRO_SAM_REPO = repo_path("micro-sam")
_TORCH_EM_REPO  = repo_path("torch-em")
_ELF_REPO       = repo_path("elf")

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
                "clone the dependency into SERAPH/external/", repo
            )


class PathoSAMAdapter(IBatchSegmentationModel):
    """
    Adapter wrapping micro_sam Patho-SAM AIS as an IBatchSegmentationModel.

    Usage:
        adapter = PathoSAMAdapter()                          # ViT-L (default)
        adapter = PathoSAMAdapter("vit_b_histopathology")    # ViT-B
        polygons = adapter.segment(pil_image)
    """

    def __init__(
        self,
        model_type: str = "vit_l_histopathology",
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
        self._last_instance_map = None

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
            batch_sizes = [batch_size]
            if batch_size != 1:
                batch_sizes.append(1)

            result = None
            last_exc = None
            for attempt, current_batch_size in enumerate(batch_sizes, start=1):
                self._clear_cuda_cache()
                logger.info(
                    "PathoSAM.segment: using batch_size=%d%s",
                    current_batch_size,
                    " (OOM retry)" if attempt > 1 else "",
                )
                try:
                    with self._inference_context():
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
                            batch_size=current_batch_size,
                        )
                    break
                except Exception as exc:
                    last_exc = exc
                    if not self._is_cuda_oom(exc) or current_batch_size == 1:
                        raise
                    logger.warning(
                        "PathoSAM CUDA OOM with batch_size=%d. Clearing CUDA cache and retrying with batch_size=1.",
                        current_batch_size,
                    )
                    self.cleanup_after_segment()
                    self._clear_cuda_cache()

            if result is None:
                raise RuntimeError("PathoSAM inference returned no result") from last_exc

            # micro_sam versions differ: some return (masks, embeddings), others just masks
            label_map = result[0] if isinstance(result, tuple) else result
            self._last_instance_map = np.asarray(label_map).astype(np.uint32, copy=False)
            self._capture_probability_map()

        except Exception as exc:
            logger.error("PathoSAM inference failed: %s", exc, exc_info=True)
            self._last_probability_map = None
            self._last_instance_map = None
            self.cleanup_after_segment()
            self._clear_cuda_cache()
            return []

        polygons = self._label_map_to_polygons(label_map)
        logger.info("PathoSAM detected %d nuclei", len(polygons))
        return polygons

    def probability_map(self):
        return self._last_probability_map

    def instance_map(self):
        return self._last_instance_map

    def cleanup_after_segment(self) -> None:
        """Release per-image micro-sam state after SERAPH has copied outputs."""
        try:
            if self._segmenter is not None and hasattr(self._segmenter, "clear_state"):
                self._segmenter.clear_state()
        except Exception as exc:
            logger.debug("PathoSAM segmenter state cleanup skipped: %s", exc)

        try:
            if self._predictor is not None and hasattr(self._predictor, "reset_image"):
                self._predictor.reset_image()
        except Exception as exc:
            logger.debug("PathoSAM predictor image cleanup skipped: %s", exc)

        self._clear_cuda_cache()

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
            self._configure_runtime()
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

    def _configure_runtime(self) -> None:
        """Enable faster inference defaults for the selected PyTorch backend."""
        try:
            import torch
        except ImportError:
            return

        if self._device == "cuda" and torch.cuda.is_available():
            try:
                torch.backends.cudnn.benchmark = True
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True
                if hasattr(torch, "set_float32_matmul_precision"):
                    torch.set_float32_matmul_precision("high")
                free_vram, total_vram = torch.cuda.mem_get_info()
                logger.info(
                    "PathoSAM CUDA runtime tuned: free=%.1fGB total=%.1fGB",
                    free_vram / 1e9,
                    total_vram / 1e9,
                )
            except Exception as exc:
                logger.warning("PathoSAM CUDA runtime tuning skipped: %s", exc)

    def _inference_context(self):
        """Use torch inference mode where available without coupling callers to torch."""
        try:
            import torch
            return torch.inference_mode()
        except Exception:
            return nullcontext()

    # ── Device helpers ────────────────────────────────────────────────────────

    def _select_device(self) -> str:
        from app.infrastructure.config.device import select_device

        device = select_device(use_gpu=self._use_gpu)

        # micro_sam only accepts a bare "cuda", not an indexed string like
        # "cuda:0" — the GPU selector has already isolated the chosen GPU.
        if device.type == "cuda":
            logger.info("PathoSAM using CUDA device %s", device.index if device.index is not None else 0)
            return "cuda"
        return device.type

    @staticmethod
    def _runtime_gpu_available() -> bool:
        from app.infrastructure.config.device import gpu_available

        return gpu_available()

    def _auto_batch_size(self) -> int:
        """Pick a batch size from the memory actually available on this backend."""
        try:
            import torch

            if self._device == "cuda" and torch.cuda.is_available():
                free_gb = torch.cuda.mem_get_info()[0] / 1e9
                for threshold, batch in ((40, 32), (24, 16), (14, 10), (12, 6), (9, 3)):
                    if free_gb > threshold:
                        return batch
                return 1

            if self._device == "mps":
                # Apple Silicon shares one memory pool with the OS, so there is no
                # free-VRAM figure to read. Stay well below the recommended ceiling.
                budget_gb = 0.0
                mps_module = getattr(torch, "mps", None)
                if mps_module is not None and hasattr(mps_module, "recommended_max_memory"):
                    budget_gb = mps_module.recommended_max_memory() / 1e9
                if budget_gb > 40:
                    return 8
                if budget_gb > 20:
                    return 4
                if budget_gb > 10:
                    return 2
        except Exception:
            pass
        return 1

    @staticmethod
    def _is_cuda_oom(exc: Exception) -> bool:
        """True on an out-of-memory error from any backend (CUDA or MPS)."""
        from app.infrastructure.config.device import is_oom_error

        return is_oom_error(exc)

    @staticmethod
    def _clear_cuda_cache() -> None:
        try:
            import gc

            from app.infrastructure.config.device import empty_cache

            gc.collect()
            empty_cache()
        except Exception:
            pass
