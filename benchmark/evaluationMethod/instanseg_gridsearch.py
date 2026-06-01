"""Grid search over InstanSeg hyperparameters on the pooled dataset (100 ROIs).

Sweeps the knobs that actually affect the result:
  seed_threshold  (main detection knob), peak_distance (seed separation / merge-split),
  mask_threshold  (minor; 2 levels to confirm).
Network forward runs per (config x ROI); image tensors + GT are cached in memory.
Optimizes micro-F1 vs GT (IoU@0.5). Deterministic model -> stable results.

Run:  python -m benchmark.evaluationMethod.instanseg_gridsearch
"""
from __future__ import annotations
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image

sys.path.insert(0, "benchmark/evaluationMethod")
from matching import match  # noqa: E402

sys.path.insert(0, "external/instanseg")
from instanseg import InstanSeg  # noqa: E402

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
GTDIR = ROOT / "oral_epithelium_db" / "annotations" / "instance"
RGBDIR = ROOT / "cellpose_per_roi"

SEED_THR = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
PEAK_DIST = [3, 5, 7, 10]
MASK_THR = [0.3, 0.5]
PIXEL_SIZE = 0.25


def main():
    # cache tensors + GT once
    data = []
    for cls in ["severe", "healthy"]:
        for p in sorted((GTDIR / cls).glob("*.png")):
            roi = p.stem
            rgb = RGBDIR / cls / roi / "roi_rgb.png"
            if not rgb.exists():
                continue
            img = np.array(Image.open(rgb).convert("RGB"))
            t = torch.from_numpy(img).permute(2, 0, 1).float()
            gt = np.array(Image.open(p)).astype(np.int32)
            data.append((t, gt))
    print(f"Loaded {len(data)} ROIs", flush=True)

    model = InstanSeg("brightfield_nuclei", verbosity=0)
    configs = list(itertools.product(SEED_THR, PEAK_DIST, MASK_THR))
    print(f"Grid: {len(configs)} configs x {len(data)} ROIs = {len(configs)*len(data)} forwards", flush=True)

    rows = []
    for ci, (seed, peak, mask) in enumerate(configs, 1):
        tp = fp = fn = 0
        for t, gt in data:
            try:
                with torch.inference_mode():
                    lab = model.eval_small_image(
                        t, pixel_size=PIXEL_SIZE, target="nuclei", return_image_tensor=False,
                        seed_threshold=seed, peak_distance=peak, mask_threshold=mask,
                    )
                pred = np.asarray(lab).squeeze().astype(np.int32)
            except Exception:
                pred = np.zeros_like(gt)
            r = match(gt, pred, 0.5)
            tp += r.tp; fp += r.fp; fn += r.fn
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
        rows.append(dict(seed_threshold=seed, peak_distance=peak, mask_threshold=mask,
                         precision=round(prec, 4), recall=round(rec, 4), f1=round(f1, 4),
                         tp=tp, fp=fp, fn=fn))
        print(f"[{ci}/{len(configs)}] seed={seed} peak={peak} mask={mask} -> "
              f"F1={f1:.4f} P={prec:.3f} R={rec:.3f}", flush=True)

    df = pd.DataFrame(rows).sort_values("f1", ascending=False).reset_index(drop=True)
    df.to_csv("benchmark/results/instanseg_gridsearch.csv", index=False)
    print("\n=== TOP 10 configs (by micro-F1) ===", flush=True)
    print(df.head(10).to_string(index=False), flush=True)
    b = df.iloc[0]
    print(f"\nBEST: seed_threshold={b.seed_threshold} peak_distance={b.peak_distance} "
          f"mask_threshold={b.mask_threshold} -> F1={b.f1} (P={b.precision} R={b.recall})", flush=True)
    print("Saved -> benchmark/results/instanseg_gridsearch.csv", flush=True)


if __name__ == "__main__":
    main()
