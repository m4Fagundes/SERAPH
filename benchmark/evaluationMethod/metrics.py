"""
Metrics for nuclei instance segmentation benchmark.

All metrics are computed per tile (one GT mask vs one prediction mask).

Detection metrics  — from MatchResult alone (no masks needed):
  precision, recall, f1

Delineation metrics — computed over matched TP pairs:
  mean_iou, mean_dice   : area overlap of matched nuclei
  hd95                  : 95th-percentile Hausdorff distance (pixels)
  asd                   : average surface distance (pixels)
  boundary_iou          : IoU on contour band (width=2px)
  area_bias             : mean(pred_area / gt_area) over TPs

Boundary metrics — class-agnostic, computed on combined boundary maps (no matching):
  boundary_recall       : frac. of GT boundary px with a pred boundary within tol (px)
  boundary_precision    : frac. of pred boundary px with a GT boundary within tol (px)
  boundary_f            : harmonic mean of boundary_precision and boundary_recall

Aggregate metrics:
  dq, sq, pq           : Panoptic Quality components (DQ=F1, SQ=mean IoU, PQ=DQ*SQ)
  aji                   : Aggregated Jaccard Index (HoVer-Net formulation)

Usage:
    result = match(gt, pred)
    m = compute_metrics(gt, pred, result)
    # m is a flat dict of floats, NaN when undefined (e.g. no TPs)
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt
from skimage.morphology import erosion, disk
from skimage.segmentation import find_boundaries

try:
    from .matching import MatchResult
except ImportError:
    from matching import MatchResult


def compute_metrics(
    gt: np.ndarray,
    pred: np.ndarray,
    result: MatchResult,
    boundary_width: int = 2,
    boundary_tolerance: int = 2,
) -> dict[str, float]:
    """Compute all metrics for one (gt, pred) tile pair.

    Args:
        gt:             (H, W) int32 GT mask.
        pred:           (H, W) int32 prediction mask.
        result:         MatchResult from matching.match().
        boundary_width: Width in pixels for boundary IoU band.

    Returns:
        Flat dict mapping metric name -> float (NaN when undefined).
    """
    m: dict[str, float] = {}

    # ── Detection ─────────────────────────────────────────────────────────
    tp, fp, fn = result.tp, result.fp, result.fn
    m["precision"] = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
    m["recall"]    = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
    pr, rc = m["precision"], m["recall"]
    m["f1"] = (2 * pr * rc / (pr + rc)) if (pr + rc) > 0 else float("nan")

    # ── Delineation (TP pairs only) ────────────────────────────────────────
    if tp == 0:
        for key in ("mean_iou", "mean_dice", "hd95", "asd", "boundary_iou", "area_bias"):
            m[key] = float("nan")
    else:
        iou_vals, dice_vals, hd95_vals, asd_vals, biou_vals, bias_vals = (
            [], [], [], [], [], []
        )
        disk_el = disk(boundary_width)

        for gt_id, pred_id, iou in result.matched_pairs:
            gt_bin   = gt   == gt_id
            pred_bin = pred == pred_id

            # IoU (from matching) and Dice
            iou_vals.append(iou)
            inter = float(np.sum(gt_bin & pred_bin))
            dice_vals.append(2 * inter / (gt_bin.sum() + pred_bin.sum()))

            # Surface distances via distance transform
            gt_surf   = _surface(gt_bin,   disk_el)
            pred_surf = _surface(pred_bin, disk_el)
            gt_to_pred = distance_transform_edt(~pred_surf)[gt_surf]
            pred_to_gt = distance_transform_edt(~gt_surf)[pred_surf]
            all_dists  = np.concatenate([gt_to_pred, pred_to_gt])
            hd95_vals.append(float(np.percentile(all_dists, 95)))
            asd_vals.append(float(np.mean(all_dists)))

            # Boundary IoU
            gt_bnd   = gt_bin   & ~erosion(gt_bin,   disk_el)
            pred_bnd = pred_bin & ~erosion(pred_bin, disk_el)
            bnd_inter = np.sum(gt_bnd & pred_bnd)
            bnd_union = np.sum(gt_bnd | pred_bnd)
            biou_vals.append(float(bnd_inter / bnd_union) if bnd_union > 0 else 0.0)

            # Area bias
            bias_vals.append(float(pred_bin.sum()) / float(gt_bin.sum()))

        m["mean_iou"]     = float(np.mean(iou_vals))
        m["mean_dice"]    = float(np.mean(dice_vals))
        m["hd95"]         = float(np.mean(hd95_vals))
        m["asd"]          = float(np.mean(asd_vals))
        m["boundary_iou"] = float(np.mean(biou_vals))
        m["area_bias"]    = float(np.mean(bias_vals))

    # ── Boundary adherence (class-agnostic, tolerance in px) ────────────────
    # Boundary Recall (BR): fraction of GT boundary pixels that have a predicted
    # boundary pixel within `boundary_tolerance` px. Computed on the combined
    # boundary maps of all instances (no matching), so it measures how well the
    # true edge structure is recovered, independent of detection count.
    # NOTE: BR alone can be inflated by over-segmentation (more predicted edges
    # everywhere → more GT edges happen to be "covered"); always read it next to
    # Boundary Precision (BP) and their F-score.
    gt_b = find_boundaries(gt, mode="thick")
    pred_b = find_boundaries(pred, mode="thick")
    if gt_b.any() and pred_b.any():
        d_to_pred = distance_transform_edt(~pred_b)
        d_to_gt = distance_transform_edt(~gt_b)
        br = float(np.mean(d_to_pred[gt_b] <= boundary_tolerance))
        bp = float(np.mean(d_to_gt[pred_b] <= boundary_tolerance))
        m["boundary_recall"]    = br
        m["boundary_precision"] = bp
        m["boundary_f"]         = (2 * br * bp / (br + bp)) if (br + bp) > 0 else 0.0
    else:
        m["boundary_recall"]    = float("nan")
        m["boundary_precision"] = float("nan")
        m["boundary_f"]         = float("nan")

    # ── Panoptic Quality ───────────────────────────────────────────────────
    m["dq"] = m["f1"]
    m["sq"]  = m["mean_iou"]  # NaN when tp=0
    m["pq"]  = m["dq"] * m["sq"] if tp > 0 else float("nan")

    # ── AJI (HoVer-Net formulation) ────────────────────────────────────────
    m["aji"] = _aji(gt, pred)

    return m


# ── Helpers ───────────────────────────────────────────────────────────────

def _surface(binary: np.ndarray, disk_el: np.ndarray) -> np.ndarray:
    """Return surface (boundary) pixels of a binary mask."""
    return binary & ~erosion(binary, disk_el)


def _aji(gt: np.ndarray, pred: np.ndarray) -> float:
    """Aggregated Jaccard Index (HoVer-Net formulation).

    For each GT nucleus, greedily assigns the pred nucleus with maximum
    intersection. Unmatched pred nuclei are added to denominator as FP area.
    """
    gt_ids   = np.unique(gt[gt > 0])
    pred_ids = np.unique(pred[pred > 0])

    if len(gt_ids) == 0 and len(pred_ids) == 0:
        return float("nan")
    if len(gt_ids) == 0:
        return 0.0

    pred_areas = {pid: int(np.sum(pred == pid)) for pid in pred_ids}
    used_pred  = set()

    numerator   = 0.0
    denominator = 0.0

    for gid in gt_ids:
        gt_bin = gt == gid
        gt_area = int(gt_bin.sum())

        best_inter, best_pid = 0, None
        for pid in pred_ids:
            inter = int(np.sum(gt_bin & (pred == pid)))
            if inter > best_inter:
                best_inter, best_pid = inter, pid

        if best_pid is not None:
            used_pred.add(best_pid)
            pred_area = pred_areas[best_pid]
            union = gt_area + pred_area - best_inter
        else:
            best_inter = 0
            union = gt_area

        numerator   += best_inter
        denominator += union

    # Unmatched pred nuclei contribute their area to the denominator
    for pid in pred_ids:
        if pid not in used_pred:
            denominator += pred_areas[pid]

    return float(numerator / denominator) if denominator > 0 else float("nan")
