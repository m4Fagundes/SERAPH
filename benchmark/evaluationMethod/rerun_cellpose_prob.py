"""Re-run ONLY Cellpose with the threshold expressed as a probability 0.1..0.9.

Cellpose's cellprob_threshold is a logit-scale value, not a 0-1 probability. To put
it on the same 0.1..0.9 axis as CellViT/PathoSAM (foreground probability), we set
cellprob_threshold = logit(p) for p in 0.1..0.9 and record the threshold as p.

Replaces the Cellpose rows in pr_sweep_{class}.csv (CellViT/PathoSAM rows untouched,
they are already on a 0.1..0.9 foreground-probability axis).

Run:  python -m benchmark.evaluationMethod.rerun_cellpose_prob --class severe --n 50
"""
from __future__ import annotations
import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, "benchmark/evaluationMethod")
from matching import match  # noqa: E402

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
GTDIR = ROOT / "oral_epithelium_db" / "annotations" / "instance"
RGBDIR = ROOT / "cellpose_per_roi"
PROBS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def pick(cls, n):
    out = []
    for p in sorted((GTDIR / cls).glob("*.png")):
        if (RGBDIR / cls / p.stem / "roi_rgb.png").exists():
            out.append(p.stem)
        if len(out) >= n:
            break
    return out


def micro(pairs):
    tp = fp = fn = 0
    for gt, pred in pairs:
        r = match(gt, pred, 0.5); tp += r.tp; fp += r.fp; fn += r.fn
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    return dict(tp=tp, fp=fp, fn=fn, precision=round(prec, 4), recall=round(rec, 4), f1=round(f1, 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--class", dest="cls", default="severe")
    ap.add_argument("--n", type=int, default=50)
    args = ap.parse_args()

    rois = pick(args.cls, args.n)
    imgs = [(np.array(Image.open(RGBDIR / args.cls / r / "roi_rgb.png").convert("RGB"), dtype=np.uint8),
             np.array(Image.open(GTDIR / args.cls / f"{r}.png")).astype(np.int32)) for r in rois]
    print(f"Cellpose prob-sweep on {len(imgs)} {args.cls} ROIs", flush=True)

    from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
    ad = CellposeAdapter()
    rows = []
    for p in PROBS:
        cp = logit(p)
        pairs = []
        for img, gt in imgs:
            ad.segment(img, diameter=None, flow_threshold=0.4, cellprob_threshold=cp)
            pred = ad.instance_map()
            pairs.append((gt, np.asarray(pred if pred is not None else np.zeros_like(gt)).astype(np.int32)))
        rows.append({"model": "Cellpose", "threshold": p, **micro(pairs)})
        print(f"  p={p} (cellprob={cp:+.2f}): {rows[-1]}", flush=True)

    # merge: drop old Cellpose rows, append new
    csv = Path(f"benchmark/results/pr_sweep_{args.cls}.csv")
    df = pd.read_csv(csv)
    df = df[df["model"] != "Cellpose"]
    df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    df.to_csv(csv, index=False)
    print(f"Updated {csv} (Cellpose rows now on 0.1..0.9 probability axis)", flush=True)


if __name__ == "__main__":
    main()
