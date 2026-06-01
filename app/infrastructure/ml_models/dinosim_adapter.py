"""
DINOSimAdapter — Infrastructure adapter for DINOSim zero-shot segmentation.

DINOSim uses DINOv2 vision-transformer embeddings to perform zero-shot
similarity-based segmentation. Unlike Cellpose/CellViT which are fully
automatic, DINOSim requires a set of reference pixel coordinates (clicked on
representative objects) before it can segment.

Workflow:
    1. Call set_reference_points(coords, reference_image) once to encode the
       visual prototype of the objects you want to find.
    2. Call segment(image) for each tile — embeddings are recomputed per tile
       but the reference vectors persist until explicitly cleared.

Repository requirement:
    napari-dinoSim must be present at external/napari-dinoSim/ (already
    cloned). DINOv2 weights are downloaded on first use via torch.hub
    (~87 MB small / ~330 MB large).
"""

import logging
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from app.domain.interfaces.batch_segmentation_model import IBatchSegmentationModel
from app.infrastructure.external_repos import repo_path

logger = logging.getLogger(__name__)

_DINOSIM_SRC = repo_path("napari-dinoSim", "src")

_MODEL_DIMS = {"small": 384, "base": 768, "large": 1024, "giant": 1536}
_MODEL_LETTERS = {"small": "s", "base": "b", "large": "l", "giant": "g"}


def _add_dinosim_to_path() -> bool:
    if getattr(sys, "frozen", False):
        return True
    if not _DINOSIM_SRC.exists():
        logger.error(
            "napari-dinoSim source not found at '%s'. "
            "Clone into external/: git clone https://github.com/AAitorG/napari-dinoSim",
            _DINOSIM_SRC,
        )
        return False
    src_str = str(_DINOSIM_SRC)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
    return True


class DINOSimAdapter(IBatchSegmentationModel):
    """
    Adapter wrapping DINOSim as an IBatchSegmentationModel.

    DINOSim is zero-shot and similarity-based — it needs at least one call to
    set_reference_points() before segment() can produce results. The reference
    persists across tiles; subsequent segment() calls on new tiles reuse the
    stored reference embeddings.

    Usage:
        adapter = DINOSimAdapter(model_size="small")
        adapter.set_reference_points([(x1, y1), (x2, y2)], reference_image=tile)
        polygons = adapter.segment(another_tile)
    """

    DINO_IMAGE_SIZE = 518
    CROP_SHAPE_SIZE = 518
    # The adapter resizes each SERAPH tile to one DINO crop. Using overlap here
    # makes the BiaPy cropper produce a 2x2 grid even for a 518x518 image, while
    # DINOSim's merge step derives a different expected crop count from the
    # low-resolution embedding grid.
    OVERLAP = (0.0, 0.0)

    def __init__(
        self,
        model_size: str = "small",
        threshold: float = 0.5,
        gpu: Optional[bool] = None,
    ) -> None:
        self._model_size = model_size if model_size in _MODEL_DIMS else "small"
        self._threshold = threshold
        self._model = None
        self._pipeline = None
        self._filter = None
        self._device = None
        self._load_attempted = False
        self._last_probability_map: Optional[np.ndarray] = None
        self._pending_reference_coords: List[Tuple[int, int]] = []
        self._use_gpu = self._runtime_gpu_available() if gpu is None else gpu

    # ── IBatchSegmentationModel ──────────────────────────────────────────────

    @property
    def name(self) -> str:
        return f"DINOSim ({self._model_size})"

    def segment(
        self,
        image,
        diameter: float | None = None,
        flow_threshold: float | None = None,
        cellprob_threshold: float | None = None,
    ) -> List[List[Tuple[int, int]]]:
        """
        Segment objects in the image using DINOSim similarity matching.

        Requires a prior call to set_reference_points(). If pending reference
        coords exist (no reference_image was given at set time), they are applied
        against this image's embeddings on this first call.

        Args:
            image: PIL Image (RGB) or numpy uint8 (H, W, 3).
            diameter: Minimum nucleus diameter (px) for size filtering.
            flow_threshold: Unused (Cellpose-specific).
            cellprob_threshold: Foreground similarity threshold override
                                (0–1). Values <= 0 use DINOSim's default 0.5.

        Returns:
            List of polygon boundaries [(x, y), ...] in local image coordinates.
        """
        self._ensure_model_loaded()
        if self._pipeline is None:
            logger.warning("DINOSim model unavailable — returning empty segmentation.")
            return []

        img_np = self._to_nhwc(image)
        orig_H, orig_W = img_np.shape[1], img_np.shape[2]

        # Resize to a single DINO crop for inference — mirrors the reference-image
        # processing and avoids the crop-count mismatch bug in the pipeline's
        # merge_data_with_overlap when sliding-window crops != merge expected crops.
        infer_np = self._resize_to_single_crop(img_np)
        crop_shape = (self.DINO_IMAGE_SIZE, self.DINO_IMAGE_SIZE, 3)

        self._pipeline.pre_compute_embeddings(
            infer_np,
            overlap=self.OVERLAP,
            crop_shape=crop_shape,
            verbose=False,
        )

        # Apply deferred reference points against this image's embeddings
        if self._pending_reference_coords and not self._pipeline.exist_reference:
            list_coords = self._coords_to_dino_pixels(
                self._pending_reference_coords, orig_W, orig_H
            )
            try:
                self._set_reference_vector_from_dino_pixels(list_coords)
                self._pending_reference_coords = []
                logger.info("DINOSim: reference set from %d deferred point(s)", len(list_coords))
            except Exception as exc:
                import traceback as _tb
                logger.error(
                    "DINOSim: failed to set deferred reference: %s\n%s",
                    exc, _tb.format_exc(),
                )
                return []

        if not self._pipeline.exist_reference:
            logger.warning("DINOSim: no reference set — call set_reference_points() first.")
            return []

        try:
            distances = self._pipeline.get_ds_distances_sameRef(verbose=False)
            pred = self._pipeline.distance_post_processing(
                distances, self._filter, upsampling_mode="bilinear"
            )  # (1, DINO_IMAGE_SIZE, DINO_IMAGE_SIZE, 1)
        except Exception as exc:
            import traceback as _tb
            logger.error("DINOSim inference failed: %s\n%s", exc, _tb.format_exc())
            return []

        similarity_map = pred[0, :, :, 0]  # low = high similarity to reference
        foreground_map = 1.0 - similarity_map
        self._last_probability_map = self._resize_probability_to_original(
            foreground_map, orig_W, orig_H
        )

        dino_diameter = None
        if diameter is not None and diameter > 0:
            dino_diameter = diameter * self.DINO_IMAGE_SIZE / max(orig_W, orig_H)

        thresholds = self._candidate_probability_thresholds(
            cellprob_threshold, foreground_map
        )
        polygons: List[List[Tuple[int, int]]] = []
        best_score = -1.0
        selected_threshold = thresholds[-1]
        for threshold in thresholds:
            candidate_polygons = self._extract_polygons(
                foreground_map, threshold, dino_diameter, infer_np[0]
            )
            candidate_score = self._polygon_set_score(candidate_polygons)
            if candidate_score > best_score:
                polygons = candidate_polygons
                selected_threshold = threshold
                best_score = candidate_score

        logger.info(
            "DINOSim.segment: image=%dx%d  probability_threshold=%.3f  prob range=[%.3f, %.3f]  polygons=%d",
            orig_W, orig_H, selected_threshold,
            float(self._last_probability_map.min()),
            float(self._last_probability_map.max()),
            len(polygons),
        )

        # Scale polygon coordinates from DINO_IMAGE_SIZE space back to original tile.
        if polygons and (orig_W != self.DINO_IMAGE_SIZE or orig_H != self.DINO_IMAGE_SIZE):
            sx = orig_W / self.DINO_IMAGE_SIZE
            sy = orig_H / self.DINO_IMAGE_SIZE
            polygons = [
                [(int(x * sx), int(y * sy)) for x, y in poly]
                for poly in polygons
            ]

        return polygons

    def probability_map(self) -> Optional[np.ndarray]:
        return self._last_probability_map

    # ── DINOSim-specific public API ──────────────────────────────────────────

    def set_reference_points(
        self,
        coords: List[Tuple[int, int]],
        reference_image=None,
    ) -> None:
        """
        Define the visual prototype of objects to find.

        Args:
            coords: (x, y) pixel coordinates in the reference image.
            reference_image: Optional PIL Image or numpy array. When provided,
                             embeddings are computed immediately and the reference
                             vectors are stored — subsequent segment() calls on
                             other tiles reuse them without re-clicking.
                             When None, reference is applied on the next segment().
        """
        if not coords:
            return

        self._ensure_model_loaded()

        if self._pipeline is None:
            logger.warning("DINOSim model not yet loaded; reference stored as pending.")
            self._pending_reference_coords = list(coords)
            return

        if reference_image is not None:
            img_np = self._to_nhwc(reference_image)
            orig_H, orig_W = img_np.shape[1], img_np.shape[2]
            # Resize to a single DINO crop (DINO_IMAGE_SIZE × DINO_IMAGE_SIZE).
            # With exactly one crop: emb_id=0 is unambiguous, no sliding-window
            # grid is produced, and the merge_data_with_overlap path in
            # distance_post_processing cannot miscount expected vs actual crops.
            ref_np = self._resize_to_single_crop(img_np)
            crop_shape = (self.DINO_IMAGE_SIZE, self.DINO_IMAGE_SIZE, 3)
            try:
                self._pipeline.pre_compute_embeddings(
                    ref_np, overlap=self.OVERLAP, crop_shape=crop_shape, verbose=False
                )
                # The DINOSim pipeline expects pixel coordinates in the image
                # space used for embedding precomputation. We precompute on the
                # resized DINO crop, so original tile coordinates must be scaled.
                list_coords = self._coords_to_dino_pixels(coords, orig_W, orig_H)
                self._set_reference_vector_from_dino_pixels(list_coords)
                self._pending_reference_coords = []
                logger.info(
                    "DINOSim: reference set from %d point(s) on provided image.", len(coords)
                )
            except Exception as exc:
                import traceback as _tb
                logger.error(
                    "DINOSim: failed to set reference from image: %s\n%s",
                    exc, _tb.format_exc(),
                )
                self._pending_reference_coords = list(coords)
        else:
            # Defer — will be applied on the first segment() call
            self._pending_reference_coords = list(coords)
            if self._pipeline is not None and self._pipeline.exist_reference:
                self._pipeline.delete_references()

    def clear_reference(self) -> None:
        """Clear stored reference vectors. A new set_reference_points() call is required."""
        self._pending_reference_coords = []
        if self._pipeline is not None:
            self._pipeline.delete_references()

    @property
    def has_reference(self) -> bool:
        """True when reference vectors are ready or pending."""
        pipeline_ready = self._pipeline is not None and self._pipeline.exist_reference
        return pipeline_ready or bool(self._pending_reference_coords)

    def _set_reference_vector_from_dino_pixels(
        self,
        list_coords: List[Tuple[int, float, float]],
    ) -> None:
        """Set reference from many prompt pixels without duplicating embeddings per point."""
        if self._pipeline is None:
            return

        import torch

        self._pipeline.delete_references()
        embedding_size = int(self._pipeline.embedding_size)
        crop_h, crop_w = self._pipeline.crop_shape[:2]

        ref_colors = []
        ref_embeddings = []
        used_embedding_ids = set()

        for n, x, y in list_coords:
            emb_id = int(n)
            if emb_id >= len(self._pipeline.embeddings):
                raise ValueError(
                    f"Invalid DINOSim embedding index {emb_id} for reference coordinate ({n}, {x}, {y})"
                )

            emb_slice = self._pipeline.embeddings[emb_id]
            if self._pipeline.embeddings_on_cpu:
                emb_slice = emb_slice.to(self._device)

            x_coord = min(max(round((float(x) / crop_w) * embedding_size), 0), embedding_size - 1)
            y_coord = min(max(round((float(y) / crop_h) * embedding_size), 0), embedding_size - 1)
            ref_colors.append(emb_slice[y_coord, x_coord])

            if emb_id not in used_embedding_ids:
                ref_embeddings.append(emb_slice)
                used_embedding_ids.add(emb_id)

        if not ref_colors or not ref_embeddings:
            raise ValueError("No DINOSim reference vectors could be extracted.")

        self._pipeline.reference_color = torch.mean(torch.stack(ref_colors), dim=0)
        self._pipeline.reference_emb = torch.stack(ref_embeddings)
        self._pipeline.generate_pseudolabels(self._filter)
        self._pipeline.exist_reference = True

    # ── Polygon extraction ───────────────────────────────────────────────────

    def _extract_polygons(
        self,
        foreground_map: np.ndarray,
        threshold: float,
        diameter: Optional[float],
        image_np: Optional[np.ndarray] = None,
    ) -> List[List[Tuple[int, int]]]:
        try:
            import cv2
            from scipy import ndimage as ndi
            from skimage.feature import peak_local_max
            from skimage.measure import label
            from skimage.morphology import (
                disk,
                opening,
                remove_small_holes,
                remove_small_objects,
            )
            from skimage.segmentation import watershed
        except ImportError:
            logger.error("opencv-python, scipy and scikit-image are required for DINOSim polygon extraction.")
            return []

        foreground_map = np.asarray(foreground_map, dtype=np.float32)
        semantic_mask = foreground_map > threshold
        if not np.any(semantic_mask):
            logger.debug("DINOSim: no foreground pixels at threshold=%.2f", threshold)
            return []

        nucleus_area: Optional[float] = None
        if diameter is not None and diameter > 0:
            nucleus_area = float(np.pi * (diameter / 2.0) ** 2)
            min_area = max(8, int(nucleus_area * 0.15))
            max_area = int(nucleus_area * 25.0)
            peak_distance = max(2, int(diameter * 0.25))
        else:
            min_area = 20
            max_area = int(foreground_map.size * 0.05)
            peak_distance = 4

        masks_to_try = []
        nuclear_score = self._nuclear_contrast_score(image_np)
        has_nuclear_masks = False
        if nuclear_score is not None:
            semantic_values = nuclear_score[semantic_mask]
            if semantic_values.size:
                positive_values = semantic_values[semantic_values > 0]
                threshold_values = positive_values if positive_values.size else semantic_values
                nuclear_thresholds = [
                    float(np.quantile(threshold_values, q))
                    for q in (0.98, 0.95, 0.90, 0.85)
                ]
                nuclear_thresholds.append(float(threshold_values.max()) * 0.35)
                for nuclear_threshold in nuclear_thresholds:
                    if nuclear_threshold <= 0:
                        continue
                    has_nuclear_masks = True
                    masks_to_try.append(
                        (
                            semantic_mask & (nuclear_score >= nuclear_threshold),
                            f"semantic+nuclear_{nuclear_threshold:.3f}",
                        )
                    )

        if not has_nuclear_masks:
            masks_to_try.append((semantic_mask, "semantic"))

        best_polygons: List[List[Tuple[int, int]]] = []
        best_score = -1.0
        best_source = "none"
        for raw_mask, source in masks_to_try:
            candidate_polygons = self._polygons_from_binary_mask(
                raw_mask,
                foreground_map,
                threshold,
                min_area,
                max_area,
                peak_distance,
                cv2,
                ndi,
                peak_local_max,
                label,
                remove_small_objects,
                remove_small_holes,
                opening,
                disk,
                watershed,
                source,
            )
            candidate_score = self._polygon_set_score(candidate_polygons)
            if source == "semantic":
                candidate_score *= 0.2
            if candidate_score > best_score:
                best_polygons = candidate_polygons
                best_score = candidate_score
                best_source = source

        if best_polygons:
            logger.info(
                "DINOSim: selected %d polygon(s) from %s at threshold=%.3f",
                len(best_polygons), best_source, threshold,
            )
        return best_polygons

    def _polygons_from_binary_mask(
        self,
        raw_mask: np.ndarray,
        foreground_map: np.ndarray,
        threshold: float,
        min_area: int,
        max_area: int,
        peak_distance: int,
        cv2,
        ndi,
        peak_local_max,
        label,
        remove_small_objects,
        remove_small_holes,
        opening,
        disk,
        watershed,
        source: str,
    ) -> List[List[Tuple[int, int]]]:
        binary = np.asarray(raw_mask, dtype=bool)
        if not np.any(binary):
            return []

        binary = remove_small_objects(binary, max_size=min_area)
        binary = remove_small_holes(binary, max_size=max(min_area * 2, 32))
        binary = opening(binary, disk(1))

        if not np.any(binary):
            logger.debug("DINOSim: %s mask removed by size/morphology filters.", source)
            return []

        distance = ndi.distance_transform_edt(binary)
        peak_coords = peak_local_max(
            distance,
            min_distance=peak_distance,
            labels=binary,
            exclude_border=False,
        )

        if len(peak_coords) > 0:
            markers = np.zeros(binary.shape, dtype=np.int32)
            markers[peak_coords[:, 0], peak_coords[:, 1]] = np.arange(1, len(peak_coords) + 1)
            labels = watershed(-distance, markers=markers, mask=binary)
        else:
            labels = label(binary)

        polygons = []
        rejected_large = 0
        for label_id in np.unique(labels):
            if label_id == 0:
                continue
            component = labels == label_id
            area = int(component.sum())
            if area < min_area:
                continue
            if area > max_area:
                rejected_large += 1
                continue
            component_u8 = component.astype(np.uint8) * 255
            contours, _ = cv2.findContours(component_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            contour = max(contours, key=cv2.contourArea)
            if len(contour) < 3:
                continue
            polygon = [(int(pt[0][0]), int(pt[0][1])) for pt in contour]
            polygons.append(polygon)

        logger.info(
            "DINOSim: extracted %d polygon(s) from %s with threshold=%.3f, min_area=%d, max_area=%d, rejected_large=%d",
            len(polygons), source, threshold, min_area, max_area, rejected_large,
        )
        return polygons

    @staticmethod
    def _polygon_set_score(polygons: List[List[Tuple[int, int]]]) -> float:
        """Prefer richer nuclear instance sets over the first non-empty attempt."""
        if not polygons:
            return 0.0
        from app.domain.geometry import polygon_area

        areas = [float(polygon_area(poly)) for poly in polygons if len(poly) >= 3]
        if not areas:
            return 0.0

        count = len(areas)
        median = float(np.median(areas))
        tiny_fraction = sum(area < max(8.0, median * 0.20) for area in areas) / count
        huge_fraction = sum(area > max(32.0, median * 6.0) for area in areas) / count
        fragmentation_penalty = 1.0 - min(0.8, tiny_fraction * 0.6 + huge_fraction * 0.4)
        excessive_count_penalty = 1.0
        if count > 60:
            excessive_count_penalty = 60.0 / count
        absolute_area_penalty = 1.0
        if median < 50.0:
            absolute_area_penalty = max(0.15, median / 50.0)

        return float(count) * fragmentation_penalty * excessive_count_penalty * absolute_area_penalty

    @staticmethod
    def _nuclear_contrast_score(image_np: Optional[np.ndarray]) -> Optional[np.ndarray]:
        """Estimate nucleus-like dark/purple contrast from the resized RGB tile."""
        if image_np is None:
            return None
        image = np.asarray(image_np)
        if image.ndim != 3 or image.shape[2] < 3:
            return None

        rgb = image[:, :, :3].astype(np.float32) / 255.0
        r = rgb[:, :, 0]
        g = rgb[:, :, 1]
        b = rgb[:, :, 2]
        luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
        darkness = 1.0 - luminance
        purple_blue = 0.5 * r + 0.8 * b - 0.7 * g
        score = 0.65 * darkness + 0.35 * purple_blue
        score = score.astype(np.float32)
        lo, hi = np.quantile(score, [0.01, 0.99])
        if hi <= lo:
            return None
        return np.clip((score - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)

    def _candidate_probability_thresholds(
        self,
        cellprob_threshold: Optional[float],
        foreground_map: Optional[np.ndarray] = None,
    ) -> List[float]:
        """Return DINOSim foreground similarity thresholds from strict to permissive."""
        if cellprob_threshold is not None and cellprob_threshold > 0:
            explicit = float(np.clip(cellprob_threshold, 0.01, 0.99))
            candidates = [explicit, explicit - 0.10, explicit - 0.20, 0.50, 0.40]
            unique: List[float] = []
            for threshold in candidates:
                threshold = float(np.clip(threshold, 0.35, 0.99))
                if not any(abs(threshold - existing) < 1e-4 for existing in unique):
                    unique.append(threshold)
            return unique

        candidates = [self._threshold]
        if foreground_map is not None:
            values = np.asarray(foreground_map, dtype=np.float32)
            values = values[np.isfinite(values)]
            if values.size:
                candidates.extend(
                    float(np.quantile(values, q)) for q in (0.70, 0.60, 0.50)
                )

        candidates.extend([0.45, 0.35])
        unique: List[float] = []
        for threshold in candidates:
            threshold = float(np.clip(threshold, 0.20, 0.90))
            if not any(abs(threshold - existing) < 1e-4 for existing in unique):
                unique.append(threshold)
        return unique

    def _resolve_probability_threshold(
        self,
        cellprob_threshold: Optional[float],
        foreground_map: Optional[np.ndarray] = None,
    ) -> float:
        """Backward-compatible single-threshold helper for tests and callers."""
        return self._candidate_probability_thresholds(cellprob_threshold, foreground_map)[0]

    # ── Image helpers ────────────────────────────────────────────────────────

    def _resize_to_single_crop(self, img_np: np.ndarray) -> np.ndarray:
        """Resize (1, H, W, 3) to (1, DINO_IMAGE_SIZE, DINO_IMAGE_SIZE, 3).

        Ensures the reference image produces exactly one embedding crop so that
        emb_id=0 is always valid and merge_data_with_overlap cannot encounter a
        crop-count mismatch during inference.
        """
        from PIL import Image as _PILImage
        size = self.DINO_IMAGE_SIZE
        pil_img = _PILImage.fromarray(img_np[0])
        pil_resized = pil_img.resize((size, size), _PILImage.BILINEAR)
        return np.array(pil_resized, dtype=np.uint8)[np.newaxis]

    def _coords_to_dino_pixels(
        self,
        coords: List[Tuple[int, int]],
        orig_w: int,
        orig_h: int,
    ) -> List[Tuple[int, float, float]]:
        """Scale original tile pixel coordinates into the resized DINO crop."""
        sx = self.DINO_IMAGE_SIZE / max(float(orig_w), 1.0)
        sy = self.DINO_IMAGE_SIZE / max(float(orig_h), 1.0)
        limit = float(self.DINO_IMAGE_SIZE - 1)
        return [
            (0, min(max(float(x) * sx, 0.0), limit), min(max(float(y) * sy, 0.0), limit))
            for x, y in coords
        ]

    def _resize_probability_to_original(
        self,
        prob_map: np.ndarray,
        orig_w: int,
        orig_h: int,
    ) -> np.ndarray:
        """Return a float32 probability map aligned with the original tile size."""
        prob_map = np.asarray(prob_map, dtype=np.float32)
        if prob_map.shape == (orig_h, orig_w):
            return prob_map

        from PIL import Image as _PILImage

        image = _PILImage.fromarray(prob_map, mode="F")
        resized = image.resize((orig_w, orig_h), _PILImage.BILINEAR)
        return np.asarray(resized, dtype=np.float32)

    @staticmethod
    def _to_nhwc(image) -> np.ndarray:
        """Convert PIL Image or numpy array to (1, H, W, 3) uint8."""
        if isinstance(image, np.ndarray):
            img = image if image.dtype == np.uint8 else (image * 255).astype(np.uint8)
        else:
            img = np.array(image.convert("RGB"), dtype=np.uint8)
        if img.ndim == 2:
            img = np.stack([img, img, img], axis=-1)
        elif img.shape[2] == 4:
            img = img[:, :, :3]
        return img[np.newaxis]  # (1, H, W, 3)

    # ── Model loading ────────────────────────────────────────────────────────

    def _ensure_model_loaded(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True
        self._load_model()

    def _load_model(self) -> None:
        if not _add_dinosim_to_path():
            return

        try:
            import torch
            from torchvision.transforms import InterpolationMode
            # Stub out napari_dinosim and napari_dinosim.utils BEFORE importing
            # their submodules. This prevents napari_dinosim/__init__.py and
            # napari_dinosim/utils/__init__.py from executing — those files pull
            # in napari/magicgui/qtpy dependencies that are not part of SERAPH's
            # venv. We only need the two utility submodules, whose own imports are
            # pure torch/numpy/tifffile and are already satisfied.
            import types as _types
            for _mod_name, _rel in (
                ("napari_dinosim",        "napari_dinosim"),
                ("napari_dinosim.utils",  "napari_dinosim/utils"),
            ):
                if _mod_name not in sys.modules:
                    _stub = _types.ModuleType(_mod_name)
                    _stub.__path__ = [str(_DINOSIM_SRC / _rel)]
                    _stub.__package__ = _mod_name
                    sys.modules[_mod_name] = _stub

            from napari_dinosim.utils.dinoSim_pipeline import DINOSim_pipeline
            from napari_dinosim.utils.utils import (
                gaussian_kernel,
                get_img_processing_f,
                torch_convolve,
            )
        except ImportError as exc:
            logger.error(
                "Failed to import DINOSim: %s\n"
                "Ensure external/napari-dinoSim/src exists and torch/torchvision are installed.",
                exc,
            )
            return

        self._device = self._select_device()
        model_letter = _MODEL_LETTERS[self._model_size]
        feat_dim = _MODEL_DIMS[self._model_size]

        logger.info(
            "DINOSim: loading dinov2_vit%s14_reg (dim=%d) on %s",
            model_letter, feat_dim, self._device,
        )
        try:
            model = torch.hub.load(
                "facebookresearch/dinov2",
                f"dinov2_vit{model_letter}14_reg",
                verbose=False,
            )
            model.to(self._device)
            model.eval()
            self._model = model
        except Exception as exc:
            logger.error("DINOSim: failed to load DINOv2 model: %s", exc)
            return

        kernel = gaussian_kernel(size=3, sigma=1)
        kernel_t = torch.tensor(kernel, dtype=torch.float32, device=self._device)
        self._filter = lambda x: torch_convolve(x, kernel_t)

        interpolation = (
            InterpolationMode.BILINEAR
            if self._device.type == "mps"
            else InterpolationMode.BICUBIC
        )
        self._pipeline = DINOSim_pipeline(
            model=self._model,
            model_patch_size=self._model.patch_size,
            device=self._device,
            img_preprocessing=get_img_processing_f(
                resize_size=self.DINO_IMAGE_SIZE,
                interpolation=interpolation,
            ),
            feat_dim=feat_dim,
            dino_image_size=self.DINO_IMAGE_SIZE,
        )

        logger.info(
            "DINOSim ready: dinov2_vit%s14_reg  feat_dim=%d  device=%s",
            model_letter, feat_dim, self._device,
        )

    # ── Device helpers ───────────────────────────────────────────────────────

    def _select_device(self):
        import torch

        try:
            from app.infrastructure.config.gpu_selector import get_best_cuda_device
            if self._use_gpu and torch.cuda.is_available():
                idx = get_best_cuda_device()
                if idx is not None:
                    return torch.device(f"cuda:{idx}")
        except Exception:
            pass

        if self._use_gpu and torch.cuda.is_available():
            return torch.device("cuda:0")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")

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
