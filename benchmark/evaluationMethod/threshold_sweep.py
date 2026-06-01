"""Precision-Recall threshold sweep for Cellpose, CellViT, PathoSAM.

Each model is swept over ITS OWN detection-confidence knob (the scales differ):
  - Cellpose : cellprob_threshold  (~[-2, 2]; higher -> fewer, more confident)
  - CellViT  : foreground prob threshold [0.1..0.9] (higher -> fewer)
  - PathoSAM : AIS foreground_threshold [0.1..0.9] (note: weak detection knob)

For efficiency the heavy network forward runs ONCE per ROI; only the threshold-
dependent postprocessing is repeated. Outputs a long CSV (model,threshold,tp,fp,
fn,precision,recall,f1) and a precision-recall plot.

Run:  python -m benchmark.evaluationMethod.threshold_sweep --class severe --n 50
"""
from __future__ import annotations
import argparse
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

CELLPROB_VALUES = [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0]
FG_VALUES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def pick_rois(cls: str, n: int) -> list[str]:
    out = []
    for p in sorted((GTDIR / cls).glob("*.png")):
        roi = p.stem
        if (RGBDIR / cls / roi / "roi_rgb.png").exists():
            out.append(roi)
        if len(out) >= n:
            break
    return out


def load(cls: str, roi: str):
    img = np.array(Image.open(RGBDIR / cls / roi / "roi_rgb.png").convert("RGB"), dtype=np.uint8)
    gt = np.array(Image.open(GTDIR / cls / f"{roi}.png")).astype(np.int32)
    return img, gt


def micro(pairs):
    tp = fp = fn = 0
    for gt, pred in pairs:
        r = match(gt, pred, iou_threshold=0.5)
        tp += r.tp; fp += r.fp; fn += r.fn
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    return dict(tp=tp, fp=fp, fn=fn, precision=round(prec, 4), recall=round(rec, 4), f1=round(f1, 4))


def sweep_cellpose(imgs):
    from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
    ad = CellposeAdapter()
    rows = []
    for t in CELLPROB_VALUES:
        pairs = []
        for _, img, gt in imgs:
            ad.segment(img, diameter=None, flow_threshold=0.4, cellprob_threshold=t)
            pred = ad.instance_map()
            if pred is None:
                pred = np.zeros_like(gt)
            pairs.append((gt, np.asarray(pred).astype(np.int32)))
        rows.append({"model": "Cellpose", "threshold": t, **micro(pairs)})
        print(f"  Cellpose cellprob={t}: {rows[-1]}", flush=True)
    return rows


def sweep_cellvit(imgs):
    import torch
    from app.infrastructure.ml_models.cellvit_adapter import CellViTAdapter
    ad = CellViTAdapter()
    ad._ensure_model_loaded()
    if ad._model is None:
        print("  CellViT model unavailable — skipping", flush=True)
        return []
    P = ad.PATCH_SIZE
    # forward ONCE per ROI -> probability pred_map
    predmaps = []
    for _, img, gt in imgs:
        H, W = img.shape[:2]
        patch = np.pad(img, ((0, max(0, P - H)), (0, max(0, P - W)), (0, 0)), mode="reflect")[:P, :P]
        with torch.no_grad():
            preds = ad._forward(torch.stack([ad._preprocess_patch(patch)]))
        predmaps.append((ad._assemble_pred_map(preds, idx=0), H, W, gt))
    rows = []
    for t in FG_VALUES:
        ad._postprocessor.fg_threshold = t
        pairs = []
        for pred_map, H, W, gt in predmaps:
            inst, _ = ad._postprocessor.post_process_cell_segmentation(pred_map)
            pairs.append((gt, np.asarray(inst[:H, :W]).astype(np.int32)))
        rows.append({"model": "CellViT-SAM", "threshold": t, **micro(pairs)})
        print(f"  CellViT fg={t}: {rows[-1]}", flush=True)
    return rows


def sweep_pathosam(imgs):
    from app.infrastructure.ml_models import patho_sam_adapter as PA
    PA._add_patho_sam_to_path()
    from app.infrastructure.ml_models._patho_sam_compat import inject as inj
    inj(PA._TORCH_EM_REPO)
    import torch
    from micro_sam.automatic_segmentation import get_predictor_and_segmenter
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    pred_m, seg = get_predictor_and_segmenter(
        model_type="vit_l_histopathology", device=dev, segmentation_mode="ais", is_tiled=False
    )
    # initialize ONCE per ROI, then generate per threshold (cheap)
    states = []
    for _, img, gt in imgs:
        seg.initialize(image=img, ndim=2, verbose=False)
        # cache generated maps per threshold now while state is hot
        per_t = {}
        for t in FG_VALUES:
            out = seg.generate(foreground_threshold=t, output_mode="instance_segmentation")
            per_t[t] = np.asarray(out).astype(np.int32)
        states.append((gt, per_t))
    rows = []
    for t in FG_VALUES:
        pairs = [(gt, per_t[t]) for gt, per_t in states]
        rows.append({"model": "PathoSAM", "threshold": t, **micro(pairs)})
        print(f"  PathoSAM fg={t}: {rows[-1]}", flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--class", dest="cls", default="severe")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--out", default="benchmark/results/pr_sweep")
    args = ap.parse_args()

    rois = pick_rois(args.cls, args.n)
    imgs = [(r, *load(args.cls, r)) for r in rois]
    print(f"Sweep on {len(imgs)} {args.cls} ROIs", flush=True)

    rows = []
    print("Cellpose...", flush=True);  rows += sweep_cellpose(imgs)
    print("CellViT...", flush=True);   rows += sweep_cellvit(imgs)
    print("PathoSAM...", flush=True);  rows += sweep_pathosam(imgs)

    df = pd.DataFrame(rows)
    out = Path(f"{args.out}_{args.cls}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nSaved {len(df)} rows -> {out}", flush=True)

    # PR plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.figure(figsize=(6, 6))
        for model, g in df.groupby("model"):
            g = g.sort_values("recall")
            plt.plot(g["recall"], g["precision"], "o-", label=model)
        plt.xlabel("Recall"); plt.ylabel("Precision")
        plt.title(f"Precision-Recall sweep ({args.cls}, {len(imgs)} ROIs)")
        plt.xlim(0, 1); plt.ylim(0, 1); plt.grid(True, alpha=0.3); plt.legend()
        fig = out.with_suffix(".png")
        plt.savefig(fig, dpi=150, bbox_inches="tight")
        print(f"Saved plot -> {fig}", flush=True)
    except Exception as exc:
        print(f"(plot skipped: {exc})", flush=True)


if __name__ == "__main__":
    main()
