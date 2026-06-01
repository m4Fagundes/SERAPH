"""Measure how saturated CellViT's binary (foreground) softmax map is.

Forwards CellViT on a few ROIs, takes the softmax foreground probability, and
reports how many pixels fall in the saturated bands (<0.1 or >0.9) vs the
intermediate transition band (0.1-0.9). Saves a histogram.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
RGBDIR = ROOT / "cellpose_per_roi" / "severe"
ROIS = ["severe-01-roi1", "severe-01-roi2", "severe-03-roi1", "severe-04-roi1", "severe-05-roi1"]


def main():
    import torch
    from app.infrastructure.ml_models.cellvit_adapter import CellViTAdapter
    ad = CellViTAdapter(); ad._ensure_model_loaded()
    if ad._model is None:
        print("CellViT unavailable"); return
    P = ad.PATCH_SIZE
    probs = []
    for roi in ROIS:
        img = np.array(Image.open(RGBDIR / roi / "roi_rgb.png").convert("RGB"), dtype=np.uint8)
        H, W = img.shape[:2]
        patch = np.pad(img, ((0, max(0, P - H)), (0, max(0, P - W)), (0, 0)), mode="reflect")[:P, :P]
        with torch.no_grad():
            preds = ad._forward(torch.stack([ad._preprocess_patch(patch)]))
        fg = preds["nuclei_binary_map"][0, 1].numpy()[:H, :W]  # softmax foreground prob
        probs.append(fg.ravel())
    p = np.concatenate(probs)

    sat_lo = float(np.mean(p < 0.1))
    sat_hi = float(np.mean(p > 0.9))
    mid = float(np.mean((p >= 0.1) & (p <= 0.9)))
    print(f"Pixels analysed: {p.size:,}")
    print(f"  prob < 0.1  (claramente fundo):   {100*sat_lo:6.2f}%")
    print(f"  prob > 0.9  (claramente nucleo):  {100*sat_hi:6.2f}%")
    print(f"  0.1 <= prob <= 0.9 (intermediario): {100*mid:6.2f}%")
    print(f"  => SATURADO (extremos): {100*(sat_lo+sat_hi):.2f}%")

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(p, bins=50, color="#2ca02c", log=True)
    ax.axvspan(0.1, 0.9, color="orange", alpha=0.15, label="faixa intermediaria (0.1-0.9)")
    ax.set_xlabel("Probabilidade de foreground (softmax) — CellViT")
    ax.set_ylabel("nº de pixels (log)")
    ax.set_title(f"CellViT: {100*(sat_lo+sat_hi):.1f}% dos pixels saturados (~0 ou ~1)")
    ax.legend()
    out = Path("benchmark/results/cellvit_prob_histogram.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved -> {out}")


if __name__ == "__main__":
    main()
