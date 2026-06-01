"""Compare PathoSAM AIS with tiling ON (current adapter) vs OFF (is_tiled=False)
on small ROIs, scored against the dataset GT.

Hypothesis: for ROIs smaller than the 384x384 tile, tiling adds spurious
detections / seam splits. Untiled should match GT better.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, "benchmark/evaluationMethod")
from matching import match  # noqa: E402

# Replicate the adapter's environment setup (sys.path + conda-compat shim)
from app.infrastructure.ml_models import patho_sam_adapter as PA  # noqa: E402
PA._add_patho_sam_to_path()
from app.infrastructure.ml_models._patho_sam_compat import inject as inject_compat  # noqa: E402
inject_compat(PA._TORCH_EM_REPO)

import torch  # noqa: E402
from micro_sam.automatic_segmentation import (  # noqa: E402
    get_predictor_and_segmenter,
    automatic_instance_segmentation,
)

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
GTDIR = ROOT / "oral_epithelium_db" / "annotations" / "instance" / "severe"
RGBDIR = ROOT / "cellpose_per_roi" / "severe"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MODEL = "vit_l_histopathology"
N_ROIS = 50


def pick_rois(n: int) -> list[str]:
    out = []
    for p in sorted(GTDIR.glob("*.png")):
        roi = p.stem
        if (RGBDIR / roi / "roi_rgb.png").exists():
            out.append(roi)
        if len(out) >= n:
            break
    return out


def load(roi: str):
    img = np.array(Image.open(RGBDIR / roi / "roi_rgb.png").convert("RGB"), dtype=np.uint8)
    gt = np.array(Image.open(GTDIR / f"{roi}.png")).astype(np.int32)
    return img, gt


def run_config(rois, is_tiled: bool):
    pred, seg = get_predictor_and_segmenter(
        model_type=MODEL, device=DEVICE, segmentation_mode="ais", is_tiled=is_tiled
    )
    rows = []
    for roi in rois:
        img, gt = load(roi)
        kw = dict(
            predictor=pred, segmenter=seg, input_path=img, output_path=None,
            embedding_path=None, ndim=2, verbose=False,
            output_mode="instance_segmentation", return_embeddings=False,
        )
        if is_tiled:
            kw.update(tile_shape=(384, 384), halo=(64, 64))
        with torch.inference_mode():
            res = automatic_instance_segmentation(**kw)
        lab = (res[0] if isinstance(res, tuple) else res).astype(np.int32)
        r = match(gt, lab, iou_threshold=0.5)
        rows.append((roi, int(gt.max()), int(lab.max()), r.tp, r.fp, r.fn))
        try:
            seg.clear_state()
        except Exception:
            pass
    del pred, seg
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return rows


def summarize(label, rows):
    gt = sum(r[1] for r in rows); pred = sum(r[2] for r in rows)
    tp = sum(r[3] for r in rows); fp = sum(r[4] for r in rows); fn = sum(r[5] for r in rows)
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0
    print(f"\n=== {label} ===")
    print(f"{'roi':16} {'gt':>4} {'pred':>5} {'tp':>4} {'fp':>4} {'fn':>4}")
    for roi, g, p, t, f, n in rows:
        print(f"{roi:16} {g:4d} {p:5d} {t:4d} {f:4d} {n:4d}")
    print(f"TOTAL gt={gt} pred={pred} tp={tp} fp={fp} fn={fn}")
    print(f"precision={prec:.3f} recall={rec:.3f} F1={f1:.3f}")
    return dict(pred=pred, fp=fp, f1=f1, prec=prec, rec=rec)


def main():
    rois = pick_rois(N_ROIS)
    print(f"device={DEVICE} model={MODEL} | {len(rois)} ROIs: {rois}")
    print("Loading TILED config...", flush=True)
    tiled = summarize("TILED (current: 384/64)", run_config(rois, is_tiled=True))
    print("\nLoading UNTILED config...", flush=True)
    untiled = summarize("UNTILED (is_tiled=False)", run_config(rois, is_tiled=False))

    print("\n========= COMPARISON =========")
    print(f"{'metric':12} {'tiled':>8} {'untiled':>8} {'delta':>8}")
    for k in ("pred", "fp", "precision" if False else "prec", "rec", "f1"):
        print(f"{k:12} {tiled[k]:8.3f} {untiled[k]:8.3f} {untiled[k]-tiled[k]:+8.3f}")


if __name__ == "__main__":
    main()
