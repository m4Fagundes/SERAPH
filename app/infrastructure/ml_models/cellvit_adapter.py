"""
CellViTAdapter — Infrastructure adapter for CellViT nucleus segmentation.

Implements IBatchSegmentationModel, following the same lazy-loading and GPU-fallback
pattern as CellposeAdapter.

The CellViT repository must be present at external/CellViT/ (cloned from
github.com/TIO-IKIM/CellViT). A pre-trained checkpoint (.pth) is expected in
~/.grid-analyzer/models/ (auto-detected) or supplied explicitly via model_path.

Inference pipeline:
    1. Input image is tiled into 1024×1024 patches with 64px overlap (960px stride).
    2. Each patch is normalised: mean=(0.5,0.5,0.5), std=(0.5,0.5,0.5).
    3. Forward pass through CellViT → nuclei_binary_map, hv_map, nuclei_type_map.
    4. Softmax applied; pred_map assembled as [type_argmax, binary_argmax, hv_x, hv_y].
    5. HoVer-Net watershed postprocessing per patch.
    6. Cells assigned to patches by centroid ownership (non-overlapping zone).
    7. Contours translated to input image coordinates and returned as polygons.

Supported architectures (determined from checkpoint "arch" key):
    CellViTSAM, CellViTSAMShared — SAM-H backbone (best accuracy, ~2.5 GB)
    CellViT256, CellViT256Shared — HIPT ViT-256 backbone (faster, ~0.9 GB)
    CellViT, CellViTShared       — vanilla ViT backbone
"""

import logging
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from app.domain.interfaces.batch_segmentation_model import IBatchSegmentationModel
from app.infrastructure.external_repos import repo_path
from app.infrastructure.ml_models.cellvit.postprocess import DetectionCellPostProcessor

logger = logging.getLogger(__name__)

# Path to the cloned CellViT repository.
_CELLVIT_REPO = repo_path("CellViT")

# Default directory for CellViT checkpoints
_CHECKPOINT_DIR = Path.home() / ".grid-analyzer" / "models"

# Preferred checkpoint name fragments (highest priority first)
_CHECKPOINT_PREFERENCE = ["SAM-H-x40", "SAM-H-x20", "SAM-H", "256-x40", "256-x20", "256"]

# Cell-type names for PanNuke (index 0 = background)
TYPE_NUCLEI_DICT = {
    0: "Background",
    1: "Neoplastic",
    2: "Inflammatory",
    3: "Connective",
    4: "Dead",
    5: "Epithelial",
}


def _add_cellvit_to_path() -> bool:
    """Insert CellViT repo root into sys.path so model classes can be imported."""
    if getattr(sys, "frozen", False):
        return True  # Under PyInstaller, hidden imports are already compiled/available

    if not _CELLVIT_REPO.exists():
        logger.error(
            "CellViT repository not found at '%s'. "
            "Clone it with: git clone https://github.com/TIO-IKIM/CellViT",
            _CELLVIT_REPO,
        )
        return False
    repo_str = str(_CELLVIT_REPO)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)
    return True


def _unflatten_dict(flat: dict, sep: str = ".") -> dict:
    """Convert {'a.b.c': v} → {'a': {'b': {'c': v}}}."""
    result: dict = {}
    for key, value in flat.items():
        parts = key.split(sep)
        d = result
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value
    return result


class CellViTAdapter(IBatchSegmentationModel):
    """
    Adapter wrapping the CellViT library as an IBatchSegmentationModel.

    Usage:
        adapter = CellViTAdapter()                          # auto-detect checkpoint
        adapter = CellViTAdapter(model_path="path/to.pth") # explicit checkpoint
        polygons = adapter.segment(pil_image)
    """

    PATCH_SIZE = 1024
    OVERLAP = 64
    STEP = PATCH_SIZE - OVERLAP  # 960 px stride

    def __init__(
        self,
        model_path: Optional[str] = None,
        magnification: int = 40,
        gpu: Optional[bool] = None,
        batch_size: int = 1,
        device_id: Optional[int] = None,
    ) -> None:
        """
        Args:
            model_path: Explicit path to a CellViT .pth checkpoint.
                        None = auto-search ~/.grid-analyzer/models/ for CellViT*.pth.
            magnification: Tissue magnification (20 or 40). Affects postprocessing.
            gpu: True = force GPU, False = force CPU, None = auto-detect.
            batch_size: Patches per forward pass. Keep at 1 for 6 GB VRAM.
            device_id: Optional CUDA device index to pin this adapter to.
        """
        self._explicit_model_path = Path(model_path) if model_path else None
        self._magnification = magnification
        self._batch_size = batch_size
        self._device_id = device_id
        self._model = None
        self._run_conf = None
        self._model_arch = "unknown"
        self._mixed_precision = False
        self._device = None
        self._load_attempted = False

        if gpu is None:
            self._use_gpu = self._runtime_gpu_available()
        else:
            self._use_gpu = gpu

        # Postprocessor — updated after loading to reflect checkpoint nr_types
        self._postprocessor = DetectionCellPostProcessor(
            nr_types=6, magnification=magnification
        )

        # Resolve display name at init from checkpoint filename (no torch import needed)
        self._display_name = self._infer_display_name()
        self._last_probability_map = None
        self._last_instance_map = None

    # ── IBatchSegmentationModel ──────────────────────────────────────────────

    # Fixed registration key — must match the entry in macro_pipeline_panel._KNOWN_MODELS.
    # The adapter's human-readable label (_display_name) is separate and used only for logs.
    NAME = "CellViT-SAM"

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
        """
        Detect all nuclei in the image and return their polygon boundaries.

        Args:
            image: PIL Image (RGB) or numpy array uint8 (H, W, 3).
            diameter, flow_threshold, cellprob_threshold: Not used by CellViT.

        Returns:
            List of polygons [(x, y), ...] in input-image-local coordinates.
        """
        self._ensure_model_loaded()
        if self._model is None:
            logger.warning("CellViT model not available — returning empty segmentation.")
            return []

        # Detection threshold: reuse cellprob_threshold as the foreground
        # probability cutoff (CellViT's [0,1] scale). None keeps the default 0.5.
        if cellprob_threshold is not None and self._postprocessor is not None:
            self._postprocessor.fg_threshold = float(min(max(cellprob_threshold, 0.0), 1.0))

        import torch

        # Normalise input to uint8 numpy HxWx3
        if isinstance(image, np.ndarray):
            img_np = image if image.dtype == np.uint8 else (image * 255).astype(np.uint8)
        else:
            img_np = np.array(image.convert("RGB"), dtype=np.uint8)

        H, W = img_np.shape[:2]
        logger.info(
            "CellViT.segment: image=%dx%d  patch=%d  step=%d  device=%s",
            W, H, self.PATCH_SIZE, self.STEP, self._device,
        )

        patch_list = list(self._iter_patches(img_np, H, W))
        logger.info("CellViT: %d patches to process", len(patch_list))

        all_polygons: List[List[Tuple[int, int]]] = []
        prob_canvas = np.full((H, W), -np.inf, dtype=np.float32)
        inst_canvas = np.zeros((H, W), dtype=np.uint32)
        next_instance_id = 1

        for batch_start in range(0, len(patch_list), self._batch_size):
            batch = patch_list[batch_start: batch_start + self._batch_size]
            patches_tensor = None
            predictions = None

            try:
                patches_tensor = torch.stack(
                    [self._preprocess_patch(p["patch"]) for p in batch]
                )
                predictions = self._forward(patches_tensor)
            except RuntimeError as exc:
                if self._is_cuda_oom(exc) and self._use_gpu:
                    predictions = self._retry_after_cuda_oom(patches_tensor, exc)
                else:
                    logger.error("CellViT forward pass failed: %s", exc)
                    continue

            try:
                for i, patch_info in enumerate(batch):
                    _rs = patch_info["row_start"]
                    _cs = patch_info["col_start"]
                    _ah = patch_info["actual_h"]
                    _aw = patch_info["actual_w"]
                    # Store the raw foreground evidence before softmax saturation.
                    # The probability softmax often collapses visually to 0/1 for CellViT,
                    # while the logit margin keeps continuous model confidence.
                    _logits = predictions["nuclei_binary_logits"][i].numpy()
                    _pprob = (_logits[1] - _logits[0]).astype(np.float32)
                    np.maximum(
                        prob_canvas[_rs:_rs + _ah, _cs:_cs + _aw],
                        _pprob[:_ah, :_aw],
                        out=prob_canvas[_rs:_rs + _ah, _cs:_cs + _aw],
                    )
                    pred_map = self._assemble_pred_map(predictions, idx=i)
                    try:
                        instance_map, inst_info = self._postprocessor.post_process_cell_segmentation(pred_map)
                    except Exception as exc:
                        logger.warning("CellViT postprocessing failed for patch: %s", exc)
                        continue

                    row_start = patch_info["row_start"]
                    col_start = patch_info["col_start"]
                    actual_h = patch_info["actual_h"]
                    actual_w = patch_info["actual_w"]

                    for inst_id, info in inst_info.items():
                        cx, cy = float(info["centroid"][0]), float(info["centroid"][1])

                        # Skip detections in the zero-padded margin (beyond actual crop)
                        if cx >= actual_w or cy >= actual_h:
                            continue

                        # Only keep cells whose centroid falls in this patch's ownership zone
                        if not self._owns_cell(cx, cy, patch_info):
                            continue

                        contour = info["contour"]  # (N, 2): col 0 = X, col 1 = Y
                        polygon = self._clip_contour_to_image(
                            contour,
                            col_start=col_start,
                            row_start=row_start,
                            width=W,
                            height=H,
                        )
                        if len(polygon) >= 3:
                            all_polygons.append(polygon)
                            local_mask = instance_map[:actual_h, :actual_w] == inst_id
                            if np.any(local_mask):
                                target = inst_canvas[
                                    row_start:row_start + actual_h,
                                    col_start:col_start + actual_w,
                                ]
                                target[local_mask] = next_instance_id
                                next_instance_id += 1
            finally:
                del patches_tensor, predictions

        logger.info("CellViT detected %d nuclei", len(all_polygons))
        prob_canvas[~np.isfinite(prob_canvas)] = 0.0
        self._last_probability_map = prob_canvas.astype(np.float32, copy=False)
        self._last_instance_map = inst_canvas
        self._log_probability_map_stats(self._last_probability_map)
        return all_polygons

    @staticmethod
    def _clip_contour_to_image(
        contour: np.ndarray,
        *,
        col_start: int,
        row_start: int,
        width: int,
        height: int,
    ) -> List[Tuple[int, int]]:
        """Translate a patch contour to image coordinates and clip it to bounds."""
        polygon: List[Tuple[int, int]] = []
        for x, y in contour:
            gx = int(round(float(x) + col_start))
            gy = int(round(float(y) + row_start))
            gx = max(0, min(width - 1, gx))
            gy = max(0, min(height - 1, gy))
            point = (gx, gy)
            if not polygon or polygon[-1] != point:
                polygon.append(point)

        if len(polygon) > 1 and polygon[0] == polygon[-1]:
            polygon.pop()

        # Clipping can collapse edge artifacts into a line or a point.
        if len(set(polygon)) < 3:
            return []
        return polygon

    def probability_map(self):
        return self._last_probability_map

    def instance_map(self):
        return self._last_instance_map

    def cleanup_after_segment(self) -> None:
        """Release transient CUDA cache after CellViT inference."""
        try:
            import gc
            import torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass

    def current_device_label(self) -> str:
        if self._device is None:
            return "unknown"
        return str(self._device)

    def current_cuda_device_id(self) -> int | None:
        if self._device is None or getattr(self._device, "type", None) != "cuda":
            return None
        return int(self._device.index or 0)

    def release_gpu_memory(self) -> bool:
        """Unload CellViT weights from CUDA when another model is about to run."""
        if self._model is None or self._device is None:
            return False
        if getattr(self._device, "type", None) != "cuda":
            return False

        logger.info("CellViT: releasing GPU model weights")
        self._model = None
        self._device = None
        self._load_attempted = False
        self._mixed_precision = False
        self._last_probability_map = None

        try:
            import gc
            import torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass
        return True

    @staticmethod
    def _log_probability_map_stats(prob_map: np.ndarray) -> None:
        try:
            finite = prob_map[np.isfinite(prob_map)]
            if finite.size == 0:
                logger.info("CellViT probability map captured: empty/non-finite")
                return
            q = np.quantile(finite, [0.01, 0.05, 0.5, 0.95, 0.99])
            near_binary = float(np.mean((finite <= 1e-6) | (finite >= 1.0 - 1e-6)))
            logger.info(
                "CellViT probability map captured: shape=%s dtype=%s min=%.6f p01=%.6f "
                "p05=%.6f p50=%.6f p95=%.6f p99=%.6f max=%.6f near_binary=%.2f%%",
                prob_map.shape,
                prob_map.dtype,
                float(finite.min()),
                float(q[0]),
                float(q[1]),
                float(q[2]),
                float(q[3]),
                float(q[4]),
                float(finite.max()),
                near_binary * 100.0,
            )
        except Exception as exc:
            logger.warning("Could not summarize CellViT probability map: %s", exc)

    # ── Patch tiling ─────────────────────────────────────────────────────────

    def _iter_patches(self, img_np: np.ndarray, H: int, W: int):
        """
        Yield patch dicts covering the full image.

        Each patch is exactly PATCH_SIZE×PATCH_SIZE; edge patches are padded with
        reflected pixels so the model never sees hard black borders.
        """
        row_starts = list(range(0, max(1, H - self.OVERLAP), self.STEP))
        col_starts = list(range(0, max(1, W - self.OVERLAP), self.STEP))
        n_rows, n_cols = len(row_starts), len(col_starts)

        for r_i, row_start in enumerate(row_starts):
            for c_i, col_start in enumerate(col_starts):
                row_end = min(row_start + self.PATCH_SIZE, H)
                col_end = min(col_start + self.PATCH_SIZE, W)
                crop = img_np[row_start:row_end, col_start:col_end]
                actual_h, actual_w = crop.shape[:2]

                pad_h = self.PATCH_SIZE - actual_h
                pad_w = self.PATCH_SIZE - actual_w
                if pad_h > 0 or pad_w > 0:
                    crop = np.pad(
                        crop,
                        ((0, pad_h), (0, pad_w), (0, 0)),
                        mode="reflect",
                    )

                yield {
                    "patch": crop,
                    "row_start": row_start,
                    "col_start": col_start,
                    "actual_h": actual_h,
                    "actual_w": actual_w,
                    "is_first_row": r_i == 0,
                    "is_last_row": r_i == n_rows - 1,
                    "is_first_col": c_i == 0,
                    "is_last_col": c_i == n_cols - 1,
                }

    def _owns_cell(self, local_cx: float, local_cy: float, patch_info: dict) -> bool:
        """
        Returns True if this patch owns the cell at local (cx, cy).

        Each patch owns the non-overlapping strip:
            [OVERLAP//2, PATCH_SIZE - OVERLAP//2)  in each direction,
        adjusted to [0, PATCH_SIZE) at image boundaries.
        """
        half = self.OVERLAP // 2

        row_own_start = 0 if patch_info["is_first_row"] else half
        row_own_end = self.PATCH_SIZE if patch_info["is_last_row"] else (self.PATCH_SIZE - half)

        col_own_start = 0 if patch_info["is_first_col"] else half
        col_own_end = self.PATCH_SIZE if patch_info["is_last_col"] else (self.PATCH_SIZE - half)

        return (
            row_own_start <= local_cy < row_own_end
            and col_own_start <= local_cx < col_own_end
        )

    # ── Preprocessing and forward ─────────────────────────────────────────────

    def _preprocess_patch(self, patch_np: np.ndarray):
        """Convert uint8 HxWx3 numpy patch to normalised [3, H, W] float tensor."""
        import torch
        import torchvision.transforms.functional as TF
        from PIL import Image as PILImage

        pil = PILImage.fromarray(patch_np)
        tensor = TF.to_tensor(pil)                              # [3, H, W] in [0, 1]
        tensor = TF.normalize(tensor, [0.5, 0.5, 0.5], [0.5, 0.5, 0.5])  # → [-1, 1]
        return tensor

    def _forward(self, batch: "torch.Tensor") -> dict:
        """
        Run one forward pass and return predictions on CPU.

        Softmax is applied here to match the official CellViT inference pipeline
        (cell_detection.py), which applies it before calling calculate_instance_map.
        The raw binary logits are kept separately for exporting a non-saturated
        CellViT confidence map.
        """
        import torch
        import torch.nn.functional as F

        batch = batch.to(self._device)

        with torch.no_grad():
            if self._mixed_precision and self._device.type == "cuda":
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    preds = self._model(batch)
            else:
                preds = self._model(batch)

        raw_binary_logits = preds["nuclei_binary_map"].float()
        preds["nuclei_binary_logits"] = raw_binary_logits
        preds["nuclei_binary_map"] = F.softmax(raw_binary_logits, dim=1)
        preds["nuclei_type_map"] = F.softmax(preds["nuclei_type_map"].float(), dim=1)

        return {
            k: v.detach().cpu() if isinstance(v, torch.Tensor) else v
            for k, v in preds.items()
        }

    def _assemble_pred_map(self, predictions: dict, idx: int = 0) -> np.ndarray:
        """
        Build the [H, W, 4] pred_map consumed by DetectionCellPostProcessor.

        Layout (matches official cellvit.py::calculate_instance_map):
            [..., 0] — argmax(type_map)   per pixel  (int)
            [..., 1] — argmax(binary_map) per pixel  (0 = bg, 1 = nucleus)
            [..., 2] — hv_map horizontal channel     (float32)
            [..., 3] — hv_map vertical channel       (float32)
        """
        import torch

        type_map = (
            torch.argmax(predictions["nuclei_type_map"][idx], dim=0)
            .numpy()
            .astype(np.float32)
        )
        # Foreground (nucleus) probability — softmax channel 1, NOT the argmax.
        # The postprocessor thresholds this at fg_threshold (default 0.5, which
        # reproduces the old argmax behaviour). Passing the probability is what
        # makes the detection threshold tunable for precision-recall sweeps.
        binary_map = (
            predictions["nuclei_binary_map"][idx, 1]
            .numpy()
            .astype(np.float32)
        )
        hv_x = predictions["hv_map"][idx, 0].numpy().astype(np.float32)
        hv_y = predictions["hv_map"][idx, 1].numpy().astype(np.float32)

        return np.stack([type_map, binary_map, hv_x, hv_y], axis=-1)  # [H, W, 4]

    # ── Model loading ─────────────────────────────────────────────────────────

    def _ensure_model_loaded(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True
        self._load_model()

    def _load_model(self) -> None:
        import sys, types, torch

        # numba is imported at module level in CellViT's tools.py (used by post_proc_cellvit.py,
        # which is imported by cellvit.py). Provide a shim so the app works even when numba
        # is not installed — the only numba-decorated function (cropping_center) is unused
        # during inference.
        if "numba" not in sys.modules:
            try:
                import numba  # noqa: F401
            except ImportError:
                _shim = types.ModuleType("numba")
                _shim.njit = lambda *a, **kw: (a[0] if a and callable(a[0]) else lambda f: f)
                _shim.prange = range
                sys.modules["numba"] = _shim
                logger.info("numba not found — installed shim for CellViT tools.py compatibility")

        if not _add_cellvit_to_path():
            return

        checkpoint_path = self._find_checkpoint()
        if checkpoint_path is None:
            return

        logger.info("CellViT: loading checkpoint %s", checkpoint_path)
        try:
            checkpoint = torch.load(
                checkpoint_path, map_location="cpu", weights_only=False
            )
            self._run_conf = _unflatten_dict(checkpoint["config"], ".")
            arch = checkpoint["arch"]
            self._model_arch = arch

            model = self._instantiate_model(arch)
            result = model.load_state_dict(checkpoint["model_state_dict"], strict=True)
            if result.missing_keys:
                logger.warning("Missing state_dict keys: %s", result.missing_keys[:5])
            if result.unexpected_keys:
                logger.warning("Unexpected state_dict keys: %s", result.unexpected_keys[:5])

            model.eval()

            self._device = self._select_device()
            self._model = model.to(self._device)
            checkpoint_amp = bool(
                self._run_conf.get("training", {}).get("mixed_precision", False)
            )
            # Inference does not need to preserve the checkpoint's training
            # precision. Autocast on CUDA cuts CellViT-SAM-H activation memory
            # substantially and keeps smaller GPUs from falling back to CPU.
            self._mixed_precision = checkpoint_amp or self._device.type == "cuda"

            nr_types = self._run_conf.get("data", {}).get("num_nuclei_classes", 6)
            self._postprocessor = DetectionCellPostProcessor(
                nr_types=nr_types, magnification=self._magnification
            )

            # Update display name now that we know the arch
            self._display_name = self._arch_to_display_name(arch)

            logger.info(
                "CellViT ready: arch=%s  nr_types=%d  device=%s  amp=%s",
                arch, nr_types, self._device, self._mixed_precision,
            )
        except Exception as exc:
            logger.error("Failed to load CellViT model: %s", exc, exc_info=True)
            self._model = None

    def _find_checkpoint(self) -> Optional[Path]:
        """Return the checkpoint path to use, or None if not found."""
        if self._explicit_model_path is not None:
            if self._explicit_model_path.exists():
                return self._explicit_model_path
            logger.error("CellViT checkpoint not found: %s", self._explicit_model_path)
            return None

        if not _CHECKPOINT_DIR.exists():
            logger.warning(
                "CellViT checkpoint directory not found: %s\n"
                "Download a checkpoint from github.com/TIO-IKIM/CellViT and place it there.",
                _CHECKPOINT_DIR,
            )
            return None

        candidates = sorted(_CHECKPOINT_DIR.glob("CellViT*.pth"))
        if not candidates:
            logger.warning(
                "No CellViT*.pth found in %s.\n"
                "Download CellViT-SAM-H-x40.pth from the CellViT GitHub releases.",
                _CHECKPOINT_DIR,
            )
            return None

        for pref in _CHECKPOINT_PREFERENCE:
            for c in candidates:
                if pref in c.name:
                    logger.info("CellViT auto-selected checkpoint: %s", c.name)
                    return c

        logger.info("CellViT auto-selected checkpoint: %s", candidates[0].name)
        return candidates[0]

    def _instantiate_model(self, arch: str):
        """Instantiate the correct CellViT model class based on the checkpoint arch."""
        try:
            from models.segmentation.cell_segmentation.cellvit import (
                CellViT,
                CellViT256,
                CellViTSAM,
            )
            from models.segmentation.cell_segmentation.cellvit_shared import (
                CellViT256Shared,
                CellViTSAMShared,
                CellViTShared,
            )
        except ImportError as exc:
            raise ImportError(
                f"Cannot import CellViT model classes from '{_CELLVIT_REPO}'.\n"
                f"Make sure the CellViT repo is present and its dependencies installed "
                f"(pip install segment-anything einops). Original error: {exc}"
            ) from exc

        rc = self._run_conf
        data = rc.get("data", {})
        model_conf = rc.get("model", {})

        num_nuclei = data.get("num_nuclei_classes", 6)
        num_tissue = data.get("num_tissue_classes", 19)

        class_map = {
            "CellViT": CellViT,
            "CellViTShared": CellViTShared,
            "CellViT256": CellViT256,
            "CellViT256Shared": CellViT256Shared,
            "CellViTSAM": CellViTSAM,
            "CellViTSAMShared": CellViTSAMShared,
        }
        if arch not in class_map:
            raise ValueError(
                f"Unknown CellViT arch '{arch}'. Supported: {list(class_map)}"
            )

        if arch in ("CellViT", "CellViTShared"):
            return class_map[arch](
                num_nuclei_classes=num_nuclei,
                num_tissue_classes=num_tissue,
                embed_dim=model_conf["embed_dim"],
                input_channels=model_conf.get("input_channels", 3),
                depth=model_conf["depth"],
                num_heads=model_conf["num_heads"],
                extract_layers=model_conf["extract_layers"],
                regression_loss=model_conf.get("regression_loss", False),
            )
        elif arch in ("CellViT256", "CellViT256Shared"):
            return class_map[arch](
                model256_path=None,
                num_nuclei_classes=num_nuclei,
                num_tissue_classes=num_tissue,
                regression_loss=model_conf.get("regression_loss", False),
            )
        elif arch in ("CellViTSAM", "CellViTSAMShared"):
            return class_map[arch](
                model_path=None,
                num_nuclei_classes=num_nuclei,
                num_tissue_classes=num_tissue,
                vit_structure=model_conf["backbone"],
                regression_loss=model_conf.get("regression_loss", False),
            )

    # ── Device helpers ────────────────────────────────────────────────────────

    def _select_device(self):
        import torch

        try:
            from app.infrastructure.config.gpu_selector import get_best_cuda_device
            if self._use_gpu and torch.cuda.is_available():
                idx = self._device_id
                if idx is None:
                    idx = get_best_cuda_device()
                if idx is not None:
                    logger.info("CellViT using CUDA device %d", idx)
                    return torch.device(f"cuda:{idx}")
        except Exception:
            pass

        if self._use_gpu and torch.cuda.is_available():
            return torch.device("cuda:0")

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")

        return torch.device("cpu")

    def _move_to_cpu(self) -> None:
        """Permanently move model to CPU after CUDA OOM."""
        import torch
        self._use_gpu = False
        self._device = torch.device("cpu")
        if self._model is not None:
            self._model = self._model.to(self._device)
        logger.warning("CellViT permanently moved to CPU (CUDA OOM fallback)")

    @staticmethod
    def _is_cuda_oom(exc: RuntimeError) -> bool:
        text = str(exc).lower()
        return "out of memory" in text or "cuda error: out of memory" in text

    def _retry_after_cuda_oom(self, patches_tensor, exc: RuntimeError) -> dict:
        import gc
        import torch

        failed_device = self.current_cuda_device_id()
        logger.warning(
            "CellViT CUDA OOM on %s: %s",
            self.current_device_label(),
            str(exc).splitlines()[0],
        )
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()

        alternate = self._select_alternate_cuda_device(exclude=failed_device)
        if alternate is not None:
            try:
                self._move_to_cuda_device(alternate)
                logger.warning("CellViT retrying on CUDA device %d after OOM", alternate)
                return self._forward(patches_tensor)
            except RuntimeError as retry_exc:
                if not self._is_cuda_oom(retry_exc):
                    raise
                logger.warning(
                    "CellViT retry also OOM on cuda:%d: %s",
                    alternate,
                    str(retry_exc).splitlines()[0],
                )
                gc.collect()
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()

        logger.warning("CellViT falling back to CPU after CUDA OOM recovery failed")
        self._move_to_cpu()
        return self._forward(patches_tensor)

    def _select_alternate_cuda_device(self, exclude: int | None = None) -> int | None:
        try:
            import torch

            if not torch.cuda.is_available() or torch.cuda.device_count() < 2:
                return None

            candidates = []
            for idx in range(torch.cuda.device_count()):
                if exclude is not None and idx == exclude:
                    continue
                try:
                    free, total = torch.cuda.mem_get_info(idx)
                    candidates.append((free, total, idx))
                except Exception:
                    continue
            if not candidates:
                return None

            candidates.sort(reverse=True)
            free, total, idx = candidates[0]
            logger.info(
                "CellViT alternate CUDA candidate: device=%d free=%.2fGB total=%.2fGB",
                idx,
                free / 1e9,
                total / 1e9,
            )
            return idx
        except Exception as select_exc:
            logger.debug("CellViT alternate CUDA selection skipped: %s", select_exc)
            return None

    def _move_to_cuda_device(self, device_id: int) -> None:
        import torch

        self._use_gpu = True
        self._device_id = int(device_id)
        self._device = torch.device(f"cuda:{self._device_id}")
        if self._model is not None:
            self._model = self._model.to(self._device)

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

    # ── Display name helpers ──────────────────────────────────────────────────

    def _infer_display_name(self) -> str:
        """Best-effort display name before the model is loaded."""
        path = self._explicit_model_path or self._peek_checkpoint_path()
        if path is not None:
            return self._arch_to_display_name_from_filename(path.name)
        return "CellViT"

    def _peek_checkpoint_path(self) -> Optional[Path]:
        """Return checkpoint path without loading the model (no torch import)."""
        if not _CHECKPOINT_DIR.exists():
            return None
        candidates = sorted(_CHECKPOINT_DIR.glob("CellViT*.pth"))
        for pref in _CHECKPOINT_PREFERENCE:
            for c in candidates:
                if pref in c.name:
                    return c
        return candidates[0] if candidates else None

    @staticmethod
    def _arch_to_display_name(arch: str) -> str:
        mapping = {
            "CellViTSAM": "CellViT (SAM-H)",
            "CellViTSAMShared": "CellViT (SAM-H)",
            "CellViT256": "CellViT (256)",
            "CellViT256Shared": "CellViT (256)",
            "CellViT": "CellViT (ViT)",
            "CellViTShared": "CellViT (ViT)",
        }
        return mapping.get(arch, f"CellViT ({arch})")

    @staticmethod
    def _arch_to_display_name_from_filename(filename: str) -> str:
        if "SAM" in filename:
            return "CellViT (SAM-H)"
        if "256" in filename:
            return "CellViT (256)"
        return "CellViT"
