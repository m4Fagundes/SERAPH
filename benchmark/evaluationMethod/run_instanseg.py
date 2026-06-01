"""Run InstanSeg on the dataset ROIs (severe+healthy) and evaluate vs GT.

Produces results_instanseg.csv with the same metric columns as the other runners,
so InstanSeg can be pooled/compared with Cellpose / CellViT / PathoSAM.

Run:  python -m benchmark.evaluationMethod.run_instanseg
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, "benchmark/evaluationMethod")
from matching import match  # noqa: E402
from metrics import compute_metrics  # noqa: E402

from app.infrastructure.ml_models.instanseg_adapter import InstanSegAdapter  # noqa: E402

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
GTDIR = ROOT / "oral_epithelium_db" / "annotations" / "instance"
RGBDIR = ROOT / "cellpose_per_roi"


def main():
    ad = InstanSegAdapter(pixel_size=0.25)
    rows = []
    for cls in ["severe", "healthy"]:
        rois = sorted(p.stem for p in (GTDIR / cls).glob("*.png")
                      if (RGBDIR / cls / p.stem / "roi_rgb.png").exists())
        for roi in rois:
            img = Image.open(RGBDIR / cls / roi / "roi_rgb.png").convert("RGB")
            gt = np.array(Image.open(GTDIR / cls / f"{roi}.png")).astype(np.int32)
            ad.segment(img)
            pred = ad.instance_map()
            pred = np.zeros_like(gt) if pred is None else np.asarray(pred).astype(np.int32)
            if pred.shape != gt.shape:
                print(f"shape mismatch {roi}: {pred.shape} vs {gt.shape}")
                continue
            r = match(gt, pred, iou_threshold=0.5)
            m = compute_metrics(gt, pred, r)
            rows.append({"tissue": cls, "roi": roi, "layer": "InstanSeg",
                         "gt_instances": int(gt.max()), "pred_instances": int(pred.max()),
                         "tp": r.tp, "fp": r.fp, "fn": r.fn, **m})
        print(f"[{cls}] done: {len([x for x in rows if x['tissue']==cls])} ROIs", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv("benchmark/results/results_instanseg.csv", index=False)

    # pooled micro summary
    agg = df[["tp", "fp", "fn"]].sum()
    prec = agg.tp / (agg.tp + agg.fp)
    rec = agg.tp / (agg.tp + agg.fn)
    f1 = 2 * agg.tp / (2 * agg.tp + agg.fp + agg.fn)
    print("\n=== InstanSeg POOLED (100 ROIs) ===")
    print(f"precision={prec:.3f} recall={rec:.3f} f1={f1:.3f} "
          f"(tp={int(agg.tp)} fp={int(agg.fp)} fn={int(agg.fn)})")
    print(f"mean_dice={df.mean_dice.mean():.3f} mean_iou={df.mean_iou.mean():.3f} "
          f"boundary_f={df.boundary_f.mean():.3f}")
    print("Saved -> benchmark/results/results_instanseg.csv")


if __name__ == "__main__":
    main()
