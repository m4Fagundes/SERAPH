"""Ensemble of Cellpose + PathoSAM from already-exported masks (no model re-run).

For each ROI, pairs the two models' instances (IoU>=0.5) and builds:
  - CONSENSUS: nuclei BOTH models detect (agreement) -> expected higher precision.
  - UNION:     nuclei EITHER model detects            -> expected higher recall.
Evaluates Cellpose, PathoSAM, Consensus, Union against the GT (micro precision/recall/F1).

Run:  python -m benchmark.evaluationMethod.ensemble_study
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, "benchmark/evaluationMethod")
from matching import match  # noqa: E402

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
GTDIR = ROOT / "oral_epithelium_db" / "annotations" / "instance"
EXPORTS = {
    "severe": Path("benchmark/data/exports/run1/severe_instance_masks_manifest.csv"),
    "healthy": Path("benchmark/data/exports/run_healthy/healthy_instance_masks_manifest.csv"),
}
A, B = "Macro Cellpose", "Macro PathoSAM"


def micro(pairs):
    tp = fp = fn = 0
    for gt, pred in pairs:
        r = match(gt, pred, 0.5); tp += r.tp; fp += r.fp; fn += r.fn
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    return dict(tp=tp, fp=fp, fn=fn, precision=round(prec, 4), recall=round(rec, 4), f1=round(f1, 4))


def build_ensembles(cp: np.ndarray, ps: np.ndarray):
    """Return (consensus, union) instance maps from two prediction maps."""
    res = match(cp, ps, iou_threshold=0.5)
    matched_cp = {g for g, p, i in res.matched_pairs}
    matched_ps = {p for g, p, i in res.matched_pairs}

    # consensus: keep only Cellpose instances that have a PathoSAM match
    consensus = np.where(np.isin(cp, list(matched_cp)), cp, 0).astype(np.int32)

    # union: all Cellpose instances + unmatched PathoSAM instances (new ids, bg pixels only)
    union = cp.astype(np.int32).copy()
    next_id = int(cp.max()) + 1
    for ps_id in np.unique(ps[ps > 0]):
        if ps_id in matched_ps:
            continue
        add = (ps == ps_id) & (union == 0)
        if add.sum() >= 5:               # ignore slivers fully covered by Cellpose
            union[add] = next_id
            next_id += 1
    return consensus, union


def main():
    rows = []
    for cls, manifest in EXPORTS.items():
        df = pd.read_csv(manifest)
        exp = manifest.parent
        coll = {"Cellpose": [], "PathoSAM": [], "Consenso": [], "Uniao": []}
        for roi in df["slice_name"].dropna().unique():
            gp = GTDIR / cls / f"{roi}.png"
            if not gp.exists():
                continue
            gt = np.array(Image.open(gp)).astype(np.int32)
            ra = df[(df.slice_name == roi) & (df.layer == A)]
            rb = df[(df.slice_name == roi) & (df.layer == B)]
            if ra.empty or rb.empty:
                continue
            cp = np.load(exp / ra.iloc[0]["npy"]).astype(np.int32)
            ps = np.load(exp / rb.iloc[0]["npy"]).astype(np.int32)
            if cp.shape != gt.shape or ps.shape != gt.shape:
                continue
            cons, uni = build_ensembles(cp, ps)
            coll["Cellpose"].append((gt, cp))
            coll["PathoSAM"].append((gt, ps))
            coll["Consenso"].append((gt, cons))
            coll["Uniao"].append((gt, uni))
        for name, pairs in coll.items():
            rows.append({"tissue": cls, "method": name, "n_roi": len(pairs), **micro(pairs)})

    out = pd.DataFrame(rows)
    out.to_csv("benchmark/results/ensemble_cellpose_pathosam.csv", index=False)
    pd.set_option("display.width", 200)
    for cls in EXPORTS:
        print(f"\n=== {cls} (50 ROIs) ===")
        print(out[out.tissue == cls][["method", "precision", "recall", "f1", "tp", "fp", "fn"]].to_string(index=False))
    print("\nSaved -> benchmark/results/ensemble_cellpose_pathosam.csv")


if __name__ == "__main__":
    main()
