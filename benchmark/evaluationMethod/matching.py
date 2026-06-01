"""
Instance matching engine for nuclei segmentation benchmark.

Given a GT mask and a prediction mask (both int32, pixel = instance ID, 0 = background),
computes optimal TP/FP/FN classification using Hungarian assignment with an IoU threshold.

Usage:
    result = match(gt, pred, iou_threshold=0.5)
    result.tp, result.fp, result.fn
    result.matched_iou   # IoU of each TP pair — used by SQ in PQ
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass
class MatchResult:
    tp: int
    fp: int
    fn: int
    # (gt_id, pred_id, iou) for each TP — used by delineation metrics
    matched_pairs: list[tuple[int, int, float]] = field(default_factory=list)
    # Full IoU matrix (n_gt x n_pred) — available for downstream analysis
    iou_matrix: np.ndarray = field(default_factory=lambda: np.empty((0, 0)))

    @property
    def n_gt(self) -> int:
        return self.tp + self.fn

    @property
    def n_pred(self) -> int:
        return self.tp + self.fp

    @property
    def matched_iou(self) -> list[float]:
        return [iou for _, _, iou in self.matched_pairs]


def match(gt: np.ndarray, pred: np.ndarray, iou_threshold: float = 0.5) -> MatchResult:
    """Match predicted instances to GT instances using Hungarian assignment.

    Args:
        gt:            (H, W) int32 ground truth mask (0 = background).
        pred:          (H, W) int32 prediction mask (0 = background).
        iou_threshold: Minimum IoU for a pair to count as TP (default 0.5).

    Returns:
        MatchResult with tp, fp, fn, matched_iou, iou_matrix.
    """
    gt_ids   = np.unique(gt[gt > 0])
    pred_ids = np.unique(pred[pred > 0])

    n_gt   = len(gt_ids)
    n_pred = len(pred_ids)

    if n_gt == 0 and n_pred == 0:
        return MatchResult(tp=0, fp=0, fn=0)
    if n_gt == 0:
        return MatchResult(tp=0, fp=n_pred, fn=0)
    if n_pred == 0:
        return MatchResult(tp=0, fp=0, fn=n_gt)

    iou_mat = _iou_matrix(gt, pred, gt_ids, pred_ids)

    # Hungarian on cost = 1 - IoU (maximise IoU <=> minimise cost)
    row_ind, col_ind = linear_sum_assignment(1.0 - iou_mat)

    matched_pairs = []
    for r, c in zip(row_ind, col_ind):
        iou = iou_mat[r, c]
        if iou >= iou_threshold:
            matched_pairs.append((int(gt_ids[r]), int(pred_ids[c]), float(iou)))

    tp = len(matched_pairs)
    fp = n_pred - tp
    fn = n_gt   - tp

    return MatchResult(tp=tp, fp=fp, fn=fn, matched_pairs=matched_pairs, iou_matrix=iou_mat)


def _iou_matrix(
    gt: np.ndarray,
    pred: np.ndarray,
    gt_ids: np.ndarray,
    pred_ids: np.ndarray,
) -> np.ndarray:
    """Compute (n_gt x n_pred) pairwise IoU matrix efficiently.

    Uses a combined-label encoding to count intersections in a single pass
    instead of iterating over all (gt_id, pred_id) pairs.
    """
    n_gt, n_pred = len(gt_ids), len(pred_ids)

    # Map IDs to contiguous indices (0..n-1) for array indexing
    gt_idx   = {gid: i for i, gid in enumerate(gt_ids)}
    pred_idx = {pid: j for j, pid in enumerate(pred_ids)}

    # Pre-compute areas
    gt_areas   = np.array([np.sum(gt == gid)   for gid in gt_ids],   dtype=np.float64)
    pred_areas = np.array([np.sum(pred == pid) for pid in pred_ids], dtype=np.float64)

    # Count intersections: iterate only over pixels where both masks are non-zero
    fg = (gt > 0) & (pred > 0)
    intersections = np.zeros((n_gt, n_pred), dtype=np.float64)

    if fg.any():
        gt_fg   = gt[fg]
        pred_fg = pred[fg]
        for gid, pid in zip(gt_fg, pred_fg):
            i = gt_idx.get(int(gid))
            j = pred_idx.get(int(pid))
            if i is not None and j is not None:
                intersections[i, j] += 1

    # IoU = intersection / (area_gt + area_pred - intersection)
    unions = (
        gt_areas[:, np.newaxis]
        + pred_areas[np.newaxis, :]
        - intersections
    )
    iou_mat = np.where(unions > 0, intersections / unions, 0.0)
    return iou_mat
