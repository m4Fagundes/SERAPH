"""Pixel-wise (foreground) Precision-Recall CURVE vs threshold — BOTH versions.

Per threshold (pooled, foreground 0/1): TP,FN,FP,TN
  V1 (acertou=TP):     prec=TP/(TP+FP),        rec=TP/(TP+FN)
  V2 (acertou=TP+TN):  prec=(TP+TN)/(TP+TN+FP), rec=(TP+TN)/(TP+TN+FN)
Threshold: Cellpose cellprob=logit(p); CellViT fg; PathoSAM AIS fg; InstanSeg seed. p in 0.1..0.9.
Output: pixel_pr_sweep_both.csv
"""
from __future__ import annotations
import gc, math, sys
from pathlib import Path
import numpy as np, pandas as pd, torch
from PIL import Image

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
GTDIR = ROOT / "oral_epithelium_db" / "annotations" / "instance"
RGBDIR = ROOT / "cellpose_per_roi"
PROBS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
OUT = Path("benchmark/results/pixel_pr_sweep_both.csv")


def load_data():
    data = []
    for cls in ["severe", "healthy"]:
        for p in sorted((GTDIR / cls).glob("*.png")):
            rgb = RGBDIR / cls / p.stem / "roi_rgb.png"
            if rgb.exists():
                data.append((np.array(Image.open(rgb).convert("RGB"), dtype=np.uint8),
                             (np.array(Image.open(p)).astype(np.int32) > 0)))
    return data


def counts(A, B):
    return (int(np.count_nonzero(A & B)), int(np.count_nonzero(A & ~B)),
            int(np.count_nonzero(~A & B)), int(np.count_nonzero(~A & ~B)))


def add(rows, model, p, tp, fn, fp, tn):
    v1p = tp / (tp + fp) if tp + fp else 0.0
    v1r = tp / (tp + fn) if tp + fn else 0.0
    ac = tp + tn
    v2p = ac / (ac + fp); v2r = ac / (ac + fn)
    rows.append(dict(model=model, threshold=p, v1_prec=round(v1p, 4), v1_rec=round(v1r, 4),
                     v2_prec=round(v2p, 4), v2_rec=round(v2r, 4)))
    print(f"  {model} p={p}: V1 P={v1p:.3f} R={v1r:.3f} | V2 P={v2p:.3f} R={v2r:.3f}", flush=True)


def main():
    data = load_data(); print(f"{len(data)} ROIs", flush=True)
    rows = []

    from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
    cp = CellposeAdapter()
    for p in PROBS:
        tp = fn = fp = tn = 0
        for img, A in data:
            cp.segment(Image.fromarray(img), diameter=None, flow_threshold=0.4, cellprob_threshold=math.log(p / (1 - p)))
            m = cp.instance_map(); B = (np.asarray(m) > 0) if m is not None else np.zeros_like(A)
            a, b, c, d = counts(A, B); tp += a; fn += b; fp += c; tn += d
        add(rows, "Cellpose", p, tp, fn, fp, tn)
    del cp; gc.collect(); torch.cuda.empty_cache()

    sys.path.insert(0, "external/instanseg")
    from instanseg import InstanSeg
    ins = InstanSeg("brightfield_nuclei", verbosity=0)
    for p in PROBS:
        tp = fn = fp = tn = 0
        for img, A in data:
            t = torch.from_numpy(img).permute(2, 0, 1).float()
            with torch.inference_mode():
                lab = ins.eval_small_image(t, pixel_size=0.25, target="nuclei", return_image_tensor=False, seed_threshold=p)
            a, b, c, d = counts(A, np.asarray(lab).squeeze() > 0); tp += a; fn += b; fp += c; tn += d
        add(rows, "InstanSeg", p, tp, fn, fp, tn)
    del ins; gc.collect(); torch.cuda.empty_cache()

    from app.infrastructure.ml_models.cellvit_adapter import CellViTAdapter
    cv = CellViTAdapter(); cv._ensure_model_loaded()
    if cv._model is not None:
        P = cv.PATCH_SIZE; predmaps = []
        for img, A in data:
            H, W = img.shape[:2]
            patch = np.pad(img, ((0, max(0, P - H)), (0, max(0, P - W)), (0, 0)), mode="reflect")[:P, :P]
            with torch.no_grad():
                preds = cv._forward(torch.stack([cv._preprocess_patch(patch)]))
            predmaps.append((cv._assemble_pred_map(preds, idx=0), H, W, A))
        for p in PROBS:
            cv._postprocessor.fg_threshold = p; tp = fn = fp = tn = 0
            for pm, H, W, A in predmaps:
                inst, _ = cv._postprocessor.post_process_cell_segmentation(pm)
                a, b, c, d = counts(A, np.asarray(inst[:H, :W]) > 0); tp += a; fn += b; fp += c; tn += d
            add(rows, "CellViT-SAM", p, tp, fn, fp, tn)
        del predmaps
    del cv; gc.collect(); torch.cuda.empty_cache()

    from app.infrastructure.ml_models import patho_sam_adapter as PA
    PA._add_patho_sam_to_path()
    from app.infrastructure.ml_models._patho_sam_compat import inject as inj; inj(PA._TORCH_EM_REPO)
    from micro_sam.automatic_segmentation import get_predictor_and_segmenter
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    pred_m, seg = get_predictor_and_segmenter(model_type="vit_l_histopathology", device=dev, segmentation_mode="ais", is_tiled=False)
    states = []
    for img, A in data:
        seg.initialize(image=img, ndim=2, verbose=False)
        states.append(({p: (np.asarray(seg.generate(foreground_threshold=p, output_mode="instance_segmentation")) > 0) for p in PROBS}, A))
    for p in PROBS:
        tp = fn = fp = tn = 0
        for per, A in states:
            a, b, c, d = counts(A, per[p]); tp += a; fn += b; fp += c; tn += d
        add(rows, "PathoSAM", p, tp, fn, fp, tn)

    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"\nSaved -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
