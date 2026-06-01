"""
CellViT post-processing pipeline.

Direct port of DetectionCellPostProcessor from the official CellViT repository:
  CellViT/cell_segmentation/utils/post_proc_cellvit.py

Original authors: Fabian Hörst et al. (Institute for Artificial Intelligence in Medicine,
University Medicine Essen). Licensed under Apache 2.0 with Commons Clause.

External deps: scipy, skimage, numpy, opencv — all available in the SERAPH env.
The numba-accelerated helpers from tools.py are replaced with equivalent numpy/scipy
implementations so numba is not required.
"""

from typing import Tuple

import cv2
import numpy as np
from scipy.ndimage import measurements
from scipy.ndimage.morphology import binary_fill_holes
from skimage.segmentation import watershed


# ── Helpers (ported from CellViT/cell_segmentation/utils/tools.py) ──────────

def _get_bounding_box(img: np.ndarray):
    """Return [rmin, rmax, cmin, cmax] for a binary mask (rmax/cmax are exclusive+1)."""
    rows = np.any(img, axis=1)
    cols = np.any(img, axis=0)
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    rmax += 1
    cmax += 1
    return [rmin, rmax, cmin, cmax]


def _remove_small_objects(pred: np.ndarray, min_size: int = 64) -> np.ndarray:
    """Remove labeled connected components with fewer than min_size pixels."""
    if min_size == 0:
        return pred
    out = pred.copy()
    component_sizes = np.bincount(pred.ravel())
    too_small = component_sizes < min_size
    out[too_small[pred]] = 0
    return out


# ── Main postprocessor ───────────────────────────────────────────────────────

class DetectionCellPostProcessor:
    """
    Converts raw CellViT pred_map into labeled cell instances.

    Exact port of the official HoVer-Net watershed pipeline used by CellViT.
    """

    def __init__(
        self,
        nr_types: int = None,
        magnification: int = 40,
        gt: bool = False,
    ) -> None:
        """
        Args:
            nr_types: Number of cell classes including background (background=0).
                      None disables type classification.
            magnification: 20 or 40. Controls Sobel kernel size and min object size.
            gt: Set True for ground-truth processing (disables small-object removal).
        """
        self.nr_types = nr_types

        if magnification == 40:
            self.object_size = 10
            self.k_size = 21
        elif magnification == 20:
            self.object_size = 3
            self.k_size = 11
        else:
            raise ValueError(f"Unsupported magnification: {magnification}. Use 20 or 40.")

        if gt:
            self.object_size = 100
            self.k_size = 21

        # Foreground (binary nucleus) probability threshold. 0.5 reproduces the
        # original argmax behaviour; lower → more foreground/detections, higher →
        # fewer. Settable so callers can sweep it (e.g. precision-recall curves).
        self.fg_threshold = 0.5

    def post_process_cell_segmentation(
        self,
        pred_map: np.ndarray,
    ) -> Tuple[np.ndarray, dict]:
        """
        Convert a raw CellViT pred_map [H, W, 4] into instance map + info dict.

        Args:
            pred_map: shape (H, W, 4)
                [..., 0] — per-pixel cell-type class (int, argmax of softmax type_map)
                [..., 1] — binary nucleus probability (argmax of softmax binary_map → 0 or 1)
                [..., 2] — horizontal HV-map channel
                [..., 3] — vertical HV-map channel

        Returns:
            (instance_map, inst_info_dict)
            instance_map: (H, W) int array; each detected nucleus has a unique non-zero ID.
            inst_info_dict: {inst_id: {"bbox", "centroid", "contour", "type_prob", "type"}}
        """
        if self.nr_types is not None:
            pred_type = pred_map[..., :1].astype(np.int32)   # [H, W, 1]
            pred_inst = pred_map[..., 1:]                     # [H, W, 3]
        else:
            pred_type = None
            pred_inst = pred_map

        pred_inst = np.squeeze(pred_inst)  # [H, W, 3]
        pred_inst = self._proc_np_hv(pred_inst, self.object_size, self.k_size, self.fg_threshold)

        inst_id_list = np.unique(pred_inst)[1:]  # exclude background (0)
        inst_info_dict = {}

        for inst_id in inst_id_list:
            inst_mask = pred_inst == inst_id
            rmin, rmax, cmin, cmax = _get_bounding_box(inst_mask)
            inst_bbox = np.array([[rmin, cmin], [rmax, cmax]])

            inst_crop = inst_mask[rmin:rmax, cmin:cmax].astype(np.uint8)
            inst_moment = cv2.moments(inst_crop)
            if inst_moment["m00"] == 0:
                continue

            contour_result = cv2.findContours(inst_crop, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            if not contour_result[0]:
                continue
            inst_contour = np.squeeze(contour_result[0][0].astype(np.int32))
            if inst_contour.ndim != 2 or inst_contour.shape[0] < 3:
                continue

            inst_centroid = np.array([
                inst_moment["m10"] / inst_moment["m00"],  # X (col direction)
                inst_moment["m01"] / inst_moment["m00"],  # Y (row direction)
            ])

            # Translate from crop-local to patch-local coordinates
            inst_contour[:, 0] += cmin  # X += col offset
            inst_contour[:, 1] += rmin  # Y += row offset
            inst_centroid[0] += cmin
            inst_centroid[1] += rmin

            inst_info_dict[inst_id] = {
                "bbox": inst_bbox,
                "centroid": inst_centroid,
                "contour": inst_contour,
                "type_prob": None,
                "type": None,
            }

        # Assign per-instance cell type using majority vote within instance pixels
        if pred_type is not None:
            for inst_id in list(inst_info_dict.keys()):
                rmin, cmin, rmax, cmax = inst_info_dict[inst_id]["bbox"].flatten()
                inst_mask_crop = (pred_inst[rmin:rmax, cmin:cmax] == inst_id)
                type_vals = pred_type[rmin:rmax, cmin:cmax][inst_mask_crop]
                type_list, type_pixels = np.unique(type_vals, return_counts=True)
                type_list = sorted(zip(type_list, type_pixels), key=lambda x: x[1], reverse=True)
                inst_type = int(type_list[0][0])
                # If background dominates, pick second most common type
                if inst_type == 0 and len(type_list) > 1:
                    inst_type = int(type_list[1][0])
                type_prob = float(dict(type_list)[inst_type] / (inst_mask_crop.sum() + 1e-6))
                inst_info_dict[inst_id]["type"] = inst_type
                inst_info_dict[inst_id]["type_prob"] = type_prob

        return pred_inst, inst_info_dict

    @staticmethod
    def _proc_np_hv(
        pred: np.ndarray,
        object_size: int = 10,
        ksize: int = 21,
        fg_threshold: float = 0.5,
    ) -> np.ndarray:
        """
        Watershed instance separation using the HoVer-Net approach.

        Args:
            pred: (H, W, 3) — channels are [binary_prob, hv_x, hv_y]
            object_size: Minimum nucleus size in pixels (for remove_small_objects).
            ksize: Sobel kernel size (21 for 40×, 11 for 20×).

        Returns:
            Instance map (H, W) with unique non-zero IDs per nucleus.
        """
        pred = pred.astype(np.float32)
        blb_raw = pred[..., 0]
        h_dir_raw = pred[..., 1]
        v_dir_raw = pred[..., 2]

        # 1. Binarise and label connected components; remove noise
        blb = (blb_raw >= fg_threshold).astype(np.int32)
        blb = measurements.label(blb)[0]
        blb = _remove_small_objects(blb, min_size=10)
        blb[blb > 0] = 1

        # 2. Normalize HV maps to [0, 1]
        h_dir = cv2.normalize(h_dir_raw, None, alpha=0, beta=1,
                              norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_32F)
        v_dir = cv2.normalize(v_dir_raw, None, alpha=0, beta=1,
                              norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_32F)

        # 3. Sobel gradient: invert so cell centres are HIGH (mountains, not valleys)
        sobelh = cv2.Sobel(h_dir, cv2.CV_64F, 1, 0, ksize=ksize)
        sobelv = cv2.Sobel(v_dir, cv2.CV_64F, 0, 1, ksize=ksize)

        sobelh = 1.0 - cv2.normalize(sobelh, None, alpha=0, beta=1,
                                      norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_32F)
        sobelv = 1.0 - cv2.normalize(sobelv, None, alpha=0, beta=1,
                                      norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_32F)

        overall = np.maximum(sobelh, sobelv)
        overall = overall - (1 - blb)
        overall[overall < 0] = 0

        # 4. Build watershed topography: basins at cell boundaries
        dist = (1.0 - overall) * blb
        dist = -cv2.GaussianBlur(dist, (3, 3), 0)  # negate → valleys at boundaries

        # 5. Build seed markers: nucleus interior minus high-gradient edges
        overall = (overall >= 0.4).astype(np.int32)
        marker = blb - overall
        marker[marker < 0] = 0
        marker = binary_fill_holes(marker).astype(np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        marker = cv2.morphologyEx(marker, cv2.MORPH_OPEN, kernel)
        marker = measurements.label(marker)[0]
        marker = _remove_small_objects(marker, min_size=object_size)

        return watershed(dist, markers=marker, mask=blb)
