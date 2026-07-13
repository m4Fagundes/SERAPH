"""Boundary PR sweep (lab iftEvalBR, r=2) for Cellpose WITHOUT the error filter (flow_threshold=0).
Oral base, 100 ROIs, thresholds 0.1..0.9. Output: cellpose_noflow_boundary.csv
"""
from __future__ import annotations
import math, sys
from pathlib import Path
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from PIL import Image
from scipy.ndimage import maximum_filter, minimum_filter

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
GTDIR = ROOT / "oral_epithelium_db" / "annotations" / "instance"
RGBDIR = ROOT / "cellpose_per_roi"
PROBS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
OUT = Path("benchmark/results/cellpose_noflow_boundary.csv")


def borders(label, r):
    size = 2 * r + 1
    lab = label.astype(np.int64)
    mx = maximum_filter(lab, size=size, mode="constant", cval=-1)
    mn = minimum_filter(lab, size=size, mode="constant", cval=-1)
    return (mx != lab) | (mn != lab)


def bcounts(gt_b, pred):
    H, W = pred.shape
    r = int(math.ceil(0.0025 * math.sqrt(H * H + W * W)))
    pb = borders(pred, r)
    tp = int(np.count_nonzero(gt_b & pb)); fn = int(np.count_nonzero(gt_b & ~pb)); fp = int(np.count_nonzero(pb & ~gt_b))
    return tp, fn, fp


def main():
    data = []
    for cls in ["severe", "healthy"]:
        for p in sorted((GTDIR / cls).glob("*.png")):
            rgb = RGBDIR / cls / p.stem / "roi_rgb.png"
            if rgb.exists():
                gt = np.array(Image.open(p)).astype(np.int32)
                H, W = gt.shape
                r = int(math.ceil(0.0025 * math.sqrt(H * H + W * W)))
                data.append((np.array(Image.open(rgb).convert("RGB"), dtype=np.uint8), borders(gt, r)))
    print(f"{len(data)} ROIs", flush=True)

    from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
    cp = CellposeAdapter()
    rows = []
    for p in PROBS:
        tp = fn = fp = 0
        for img, gtb in data:
            cp.segment(Image.fromarray(img), diameter=None, flow_threshold=0.0,
                       cellprob_threshold=math.log(p / (1 - p)))
            m = cp.instance_map(); m = np.asarray(m).astype(np.int32) if m is not None else np.zeros(gtb.shape, np.int32)
            a, b, c = bcounts(gtb, m); tp += a; fn += b; fp += c
        br = tp / (tp + fn) if tp + fn else 0.0
        bp = tp / (tp + fp) if tp + fp else 0.0
        bf = 2 * br * bp / (br + bp) if br + bp else 0.0
        rows.append(dict(model="Cellpose", threshold=p, boundary_recall=round(br, 4),
                         boundary_precision=round(bp, 4), boundary_f=round(bf, 4)))
        print(f"  Cellpose(noflow) p={p}: BR={br:.3f} BP={bp:.3f} BF={bf:.3f}", flush=True)

    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"\nSaved -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
