"""Delineation quality on the COMMON nuclei — those detected by ALL three models.

Removes the detection confound (orphans / GT-subset): for each GT nucleus matched
(IoU>=0.5) by Cellpose AND CellViT AND PathoSAM, compare how well each model
delineates it vs the GT (IoU, Dice). Also a per-nucleus head-to-head win count.
"""
from __future__ import annotations
import collections
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, "benchmark/evaluationMethod")
from matching import match  # noqa: E402

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
GTDIR = ROOT / "oral_epithelium_db" / "annotations" / "instance"
EXP = Path("benchmark/data/exports/run1")
MANIFEST = EXP / "severe_instance_masks_manifest.csv"
MODELS = ["Macro Cellpose", "Macro CellViT-SAM", "Macro PathoSAM"]


def dice(a: np.ndarray, b: np.ndarray) -> float:
    inter = float(np.logical_and(a, b).sum())
    s = a.sum() + b.sum()
    return 2 * inter / s if s else 0.0


def main():
    df = pd.read_csv(MANIFEST)
    ious = collections.defaultdict(list)
    dices = collections.defaultdict(list)
    wins = collections.Counter()
    n_common = 0
    n_gt_total = 0

    for roi in df["slice_name"].unique():
        cls = roi.split("-")[0]
        gp = GTDIR / cls / f"{roi}.png"
        if not gp.exists():
            continue
        gt = np.array(Image.open(gp)).astype(np.int32)
        n_gt_total += len(np.unique(gt[gt > 0]))

        masks = {}
        ok = True
        for m in MODELS:
            row = df[(df["slice_name"] == roi) & (df["layer"] == m)]
            if row.empty:
                ok = False
                break
            masks[m] = np.load(EXP / row.iloc[0]["npy"]).astype(np.int32)
        if not ok:
            continue

        matched = {}
        for m in MODELS:
            res = match(gt, masks[m], iou_threshold=0.5)
            matched[m] = {g: (p, i) for g, p, i in res.matched_pairs}

        common = set(matched[MODELS[0]])
        for m in MODELS[1:]:
            common &= set(matched[m])

        for g in common:
            n_common += 1
            per_iou = {}
            for m in MODELS:
                p, i = matched[m][g]
                per_iou[m] = i
                ious[m].append(i)
                dices[m].append(dice(gt == g, masks[m] == p))
            wins[max(per_iou, key=per_iou.get)] += 1

    print(f"Total GT nuclei: {n_gt_total}")
    print(f"Detected by ALL 3 models (IoU>=0.5): {n_common} "
          f"({100*n_common/n_gt_total:.0f}% of GT)")
    print()
    print(f"{'model':18} {'mean IoU':>9} {'mean Dice':>10} {'best-IoU wins':>14}")
    for m in MODELS:
        name = m.replace("Macro ", "")
        print(f"{name:18} {np.mean(ious[m]):9.4f} {np.mean(dices[m]):10.4f} "
              f"{wins[m]:8d} ({100*wins[m]/max(n_common,1):.0f}%)")


if __name__ == "__main__":
    main()
