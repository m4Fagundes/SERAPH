"""
Compatibility shims for running micro-sam inference from local source on Windows.

micro-sam imports a few torch-em/elf utilities at module import time. Some of
these pull in conda-only C++ packages (nifty, vigra) even though PathoSAM
inference only needs a small subset of their behavior. These shims keep the
runtime focused on inference-only functionality.
"""

from __future__ import annotations

import inspect
import sys
import types
from pathlib import Path

import numpy as np


def inject(torch_em_repo: Path) -> None:
    _inject_vigra()
    _inject_torch_em_package(torch_em_repo)
    _inject_torch_em_dataset_util()
    _inject_torch_em_segmentation_util()
    _inject_micro_sam_2d_only_modules()

    from app.infrastructure.ml_models._nifty_shim import inject as _inject_nifty

    _inject_nifty()


def _inject_micro_sam_2d_only_modules() -> None:
    if "micro_sam.multi_dimensional_segmentation" in sys.modules:
        return

    mds_mod = types.ModuleType("micro_sam.multi_dimensional_segmentation")

    def _unsupported(*args, **kwargs):
        raise NotImplementedError("3D/tracking segmentation is not available in the SERAPH PathoSAM adapter.")

    mds_mod.automatic_3d_segmentation = _unsupported
    mds_mod.automatic_tracking_implementation = _unsupported
    sys.modules["micro_sam.multi_dimensional_segmentation"] = mds_mod


def _inject_vigra() -> None:
    if "vigra" in sys.modules:
        return

    try:
        import vigra  # noqa: F401
        return
    except ImportError:
        pass

    from scipy import ndimage as ndi
    from skimage import measure, segmentation

    vigra_mod = types.ModuleType("vigra")
    analysis_mod = types.ModuleType("vigra.analysis")
    filters_mod = types.ModuleType("vigra.filters")

    def relabel_consecutive(data, start_label=1, keep_zeros=True, out=None):
        relabeled, fw, inv = segmentation.relabel_sequential(data, offset=start_label)
        if keep_zeros:
            relabeled = relabeled.astype(data.dtype, copy=False)
        if out is not None:
            out[...] = relabeled
            relabeled = out
        max_id = int(relabeled.max()) if relabeled.size else 0
        return relabeled, max_id, fw

    def label_image_with_background(data):
        return measure.label(data, background=0).astype("uint32")

    def gaussian_smoothing(data, sigma):
        return ndi.gaussian_filter(data, sigma=sigma)

    def distance_transform(data, pixel_pitch=None):
        sampling = pixel_pitch if pixel_pitch is not None else None
        return ndi.distance_transform_edt(data, sampling=sampling)

    analysis_mod.relabelConsecutive = relabel_consecutive
    analysis_mod.labelImageWithBackground = label_image_with_background
    filters_mod.gaussianSmoothing = gaussian_smoothing
    filters_mod.distanceTransform = distance_transform

    vigra_mod.analysis = analysis_mod
    vigra_mod.filters = filters_mod

    sys.modules["vigra"] = vigra_mod
    sys.modules["vigra.analysis"] = analysis_mod
    sys.modules["vigra.filters"] = filters_mod


def _inject_torch_em_package(torch_em_repo: Path) -> None:
    existing = sys.modules.get("torch_em")
    if existing is not None and hasattr(existing, "__path__"):
        return

    package = types.ModuleType("torch_em")
    package.__path__ = [str(torch_em_repo / "torch_em")]
    package.__package__ = "torch_em"
    sys.modules["torch_em"] = package


def _inject_torch_em_dataset_util() -> None:
    if "torch_em.data.datasets.util" in sys.modules:
        return

    data_pkg = types.ModuleType("torch_em.data")
    data_pkg.__path__ = []
    datasets_pkg = types.ModuleType("torch_em.data.datasets")
    datasets_pkg.__path__ = []
    util_mod = types.ModuleType("torch_em.data.datasets.util")

    def split_kwargs(function, **kwargs):
        signature = inspect.signature(function)
        accepted = set(signature.parameters)
        function_kwargs = {k: v for k, v in kwargs.items() if k in accepted}
        other_kwargs = {k: v for k, v in kwargs.items() if k not in accepted}
        return function_kwargs, other_kwargs

    util_mod.split_kwargs = split_kwargs

    sys.modules["torch_em.data"] = data_pkg
    sys.modules["torch_em.data.datasets"] = datasets_pkg
    sys.modules["torch_em.data.datasets.util"] = util_mod


def _inject_torch_em_segmentation_util() -> None:
    if "torch_em.util.segmentation" in sys.modules:
        return

    from scipy import ndimage as ndi
    from skimage import measure
    from skimage.filters import gaussian
    from skimage.segmentation import watershed, relabel_sequential

    util_pkg = types.ModuleType("torch_em.util")
    util_pkg.__path__ = []
    seg_mod = types.ModuleType("torch_em.util.segmentation")

    def size_filter(seg: np.ndarray, min_size: int, hmap=None, with_background=False) -> np.ndarray:
        if min_size <= 0:
            return seg

        out = np.asarray(seg).copy()
        ids, sizes = np.unique(out, return_counts=True)
        remove = ids[sizes < min_size]
        if not with_background:
            remove = remove[remove != 0]
        out[np.isin(out, remove)] = 0
        out, _, _ = relabel_sequential(out, offset=1)
        return out.astype(seg.dtype, copy=False)

    def watershed_from_center_and_boundary_distances(
        center_distances: np.ndarray,
        boundary_distances: np.ndarray,
        foreground_map: np.ndarray,
        center_distance_threshold: float = 0.5,
        boundary_distance_threshold: float = 0.5,
        foreground_threshold: float = 0.5,
        distance_smoothing: float = 1.6,
        min_size: int = 0,
        debug: bool = False,
    ) -> np.ndarray:
        if distance_smoothing > 0:
            center_distances = gaussian(center_distances, sigma=distance_smoothing, preserve_range=True)
            boundary_distances = gaussian(boundary_distances, sigma=distance_smoothing, preserve_range=True)

        fg_mask = foreground_map > foreground_threshold
        marker_map = np.logical_and(
            center_distances < center_distance_threshold,
            boundary_distances < boundary_distance_threshold,
        )
        marker_map[~fg_mask] = False
        markers = measure.label(marker_map)

        seg = watershed(boundary_distances, markers=markers, mask=fg_mask)
        seg = size_filter(seg.astype("uint32"), min_size)

        if debug:
            return seg, {
                "center_distances": center_distances,
                "boundary_distances": boundary_distances,
                "foreground_mask": fg_mask,
                "markers": markers,
            }
        return seg

    def watershed_from_components(boundaries, foreground, min_size=50, threshold1=0.5, threshold2=0.5):
        seeds = measure.label((foreground - boundaries) > threshold1)
        seg = watershed(boundaries, seeds, mask=foreground > threshold2)
        return size_filter(seg.astype("uint32"), min_size)

    def connected_components_with_boundaries(foreground, boundaries, threshold=0.5):
        seeds = measure.label(np.clip(foreground - boundaries, 0, 1) > threshold)
        return watershed(boundaries, markers=seeds, mask=foreground > threshold).astype("uint64")

    def watershed_from_maxima(boundaries, foreground, min_distance, min_size=50, sigma=1.0, threshold1=0.5):
        from skimage.feature import peak_local_max

        mask = foreground > threshold1
        distances = ndi.distance_transform_edt(boundaries < 0.1)
        distances[~mask] = 0
        distances = gaussian(distances, sigma=sigma, preserve_range=True)
        points = peak_local_max(distances, min_distance=min_distance, exclude_border=False)
        seeds = np.zeros(mask.shape, dtype="uint32")
        seeds[tuple(points.T)] = np.arange(1, len(points) + 1)
        seg = watershed(boundaries, markers=seeds, mask=mask)
        return size_filter(seg.astype("uint32"), min_size)

    seg_mod.size_filter = size_filter
    seg_mod.watershed_from_center_and_boundary_distances = watershed_from_center_and_boundary_distances
    seg_mod.watershed_from_components = watershed_from_components
    seg_mod.connected_components_with_boundaries = connected_components_with_boundaries
    seg_mod.watershed_from_maxima = watershed_from_maxima

    sys.modules["torch_em.util"] = util_pkg
    sys.modules["torch_em.util.segmentation"] = seg_mod
