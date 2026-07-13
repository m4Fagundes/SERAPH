"""Per-image F1/Dice/BR for the seeded study (Cellpose / NuClick / iDISF),
recomputed from the CACHED instance maps -- NO model inference.

build_ensemble_cache.py already persisted, for every (ROI, threshold):
  cellpose_map.npy, nuclick_map.npy, idisf_map.npy
and reports only the MACRO mean per (method, threshold). significance.py needs
the per-image values to bootstrap, so this script replays the exact same
metric functions (match() at IoU 0.5, matched-Dice, boundary recall with r=2)
over the cache and dumps one row per (method, threshold, ROI).

The metric helpers below are copied verbatim from build_ensemble_cache.py so the
per-image values reproduce the published table when averaged.

Output: benchmark/results/study_3metrics_full_perimg.csv
        (method, threshold, img, f1, dice, br)
Run: python -m benchmark.evaluationMethod.seeded_perimg
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, "."); sys.path.insert(0, "benchmark/evaluationMethod")
import numpy as np
from PIL import Image
from scipy.ndimage import maximum_filter, minimum_filter
from matching import match
from _perimg import save_perimg

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
GTDIR = ROOT / "oral_epithelium_db" / "annotations" / "instance"
CACHE = Path("benchmark/cache/ensemble")
OUT = Path("benchmark/results/study_3metrics_full.csv")  # save_perimg -> *_perimg.csv
PROBS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
MAPS = {"Cellpose": "cellpose_map.npy", "NuClick": "nuclick_map.npy", "iDISF": "idisf_map.npy"}


def borders(label, r=2):  # copied from build_ensemble_cache.py
    size = 2 * r + 1
    lab = label.astype(np.int64)
    mx = maximum_filter(lab, size=size, mode="constant", cval=-1)
    mn = minimum_filter(lab, size=size, mode="constant", cval=-1)
    return (mx != lab) | (mn != lab)


def metrics(gt, pred, gtb):  # copied from build_ensemble_cache.py
    r = match(gt, pred, 0.5)
    d = 2 * r.tp + r.fp + r.fn
    f1 = (2 * r.tp / d) if d else 0.0
    dices = []
    for gid, pid, _ in r.matched_pairs:
        a = gt == gid
        b = pred == pid
        inter = int(np.count_nonzero(a & b))
        dices.append(2 * inter / (int(np.count_nonzero(a)) + int(np.count_nonzero(b))))
    dice = float(np.mean(dices)) if dices else float("nan")
    pb = borders(pred)
    btp = int((gtb & pb).sum())
    bfn = int((gtb & ~pb).sum())
    br = btp / (btp + bfn) if btp + bfn else 0.0
    return f1, dice, br


def rois():
    out = []
    for cls in ["severe", "healthy"]:
        for gp in sorted((GTDIR / cls).glob("*.png")):
            if (CACHE / cls / gp.stem).is_dir():
                out.append((cls, gp.stem))
    return out


def main():
    items = rois()
    print(f"{len(items)} cached ROIs", flush=True)
    peri = []
    for p in PROBS:
        for cls, roi in items:
            gt = np.array(Image.open(GTDIR / cls / f"{roi}.png")).astype(np.int32)
            gtb = borders(gt)
            pdir = CACHE / cls / roi / f"p{p}"
            for method, fname in MAPS.items():
                mp = pdir / fname
                if not mp.exists():
                    continue
                pred = np.load(mp).astype(np.int32)
                f1, dice, br = metrics(gt, pred, gtb)
                peri.append(dict(method=method, threshold=p, img=roi,
                                 f1=round(f1, 6),
                                 dice=("" if dice != dice else round(dice, 6)),
                                 br=round(br, 6)))
        print(f"  p={p} done", flush=True)
    save_perimg(peri, OUT)


if __name__ == "__main__":
    main()
