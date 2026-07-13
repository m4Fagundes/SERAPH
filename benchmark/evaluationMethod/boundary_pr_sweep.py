"""Boundary Precision-Recall CURVE vs threshold, for the 4 models.

Per threshold (pooled over 100 ROIs), boundary metric = lab iftEvalBR style:
  r = ceil(0.0025*diagonal) (=2 for 250x450); a pixel is 'border' if any neighbor in the
  (2r+1)^2 window has a different label (image edge counts as border).
  TP = border in GT & pred ; FN = GT-only ; FP = pred-only
  Boundary Recall = TP/(TP+FN) ; Boundary Precision = TP/(TP+FP)

Threshold knob: Cellpose cellprob=logit(p); CellViT fg_threshold; PathoSAM AIS
foreground_threshold; InstanSeg seed_threshold.  p in 0.1..0.9.
Output: boundary_pr_sweep.csv (model, threshold, boundary_precision, boundary_recall, boundary_f).
"""
from __future__ import annotations
import gc, math, sys
from pathlib import Path
import numpy as np, pandas as pd, torch
from PIL import Image
from scipy.ndimage import maximum_filter, minimum_filter
from benchmark.evaluationMethod._perimg import PerImg

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
GTDIR = ROOT / "oral_epithelium_db" / "annotations" / "instance"
RGBDIR = ROOT / "cellpose_per_roi"
PROBS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
OUT = Path("benchmark/results/boundary_pr_sweep.csv")


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


def load_data():
    data = []
    for cls in ["severe", "healthy"]:
        for p in sorted((GTDIR / cls).glob("*.png")):
            rgb = RGBDIR / cls / p.stem / "roi_rgb.png"
            if rgb.exists():
                gt = np.array(Image.open(p)).astype(np.int32)
                H, W = gt.shape
                r = int(math.ceil(0.0025 * math.sqrt(H * H + W * W)))
                data.append((np.array(Image.open(rgb).convert("RGB"), dtype=np.uint8), borders(gt, r)))
    return data


def add(rows, model, p, tp, fn, fp):
    br = tp / (tp + fn) if tp + fn else 0.0
    bp = tp / (tp + fp) if tp + fp else 0.0
    bf = 2 * br * bp / (br + bp) if br + bp else 0.0
    rows.append(dict(model=model, threshold=p, boundary_recall=round(br, 4),
                     boundary_precision=round(bp, 4), boundary_f=round(bf, 4)))
    print(f"  {model} p={p}: BR={br:.3f} BP={bp:.3f}", flush=True)


def main():
    data = load_data(); print(f"{len(data)} ROIs", flush=True)
    rows = []
    peri = PerImg()  # per-image boundary TP/FN/FP for significance.py

    from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
    cp = CellposeAdapter()
    for p in PROBS:
        tp = fn = fp = 0
        for img, gtb in data:
            cp.segment(Image.fromarray(img), diameter=None, flow_threshold=0.4, cellprob_threshold=math.log(p / (1 - p)))
            m = cp.instance_map(); m = np.asarray(m).astype(np.int32) if m is not None else np.zeros(gtb.shape, np.int32)
            a, b, c = bcounts(gtb, m); tp += a; fn += b; fp += c; peri.counts("Cellpose", p, a, b, c)
        add(rows, "Cellpose", p, tp, fn, fp)
    del cp; gc.collect(); torch.cuda.empty_cache()

    sys.path.insert(0, "external/instanseg")
    from instanseg import InstanSeg
    ins = InstanSeg("brightfield_nuclei", verbosity=0)
    for p in PROBS:
        tp = fn = fp = 0
        for img, gtb in data:
            t = torch.from_numpy(img).permute(2, 0, 1).float()
            with torch.inference_mode():
                lab = ins.eval_small_image(t, pixel_size=0.25, target="nuclei", return_image_tensor=False, seed_threshold=p)
            a, b, c = bcounts(gtb, np.asarray(lab).squeeze().astype(np.int32)); tp += a; fn += b; fp += c; peri.counts("InstanSeg", p, a, b, c)
        add(rows, "InstanSeg", p, tp, fn, fp)
    del ins; gc.collect(); torch.cuda.empty_cache()

    from app.infrastructure.ml_models.cellvit_adapter import CellViTAdapter
    cv = CellViTAdapter(); cv._ensure_model_loaded()
    if cv._model is not None:
        P = cv.PATCH_SIZE; predmaps = []
        for img, gtb in data:
            H, W = img.shape[:2]
            patch = np.pad(img, ((0, max(0, P - H)), (0, max(0, P - W)), (0, 0)), mode="reflect")[:P, :P]
            with torch.no_grad():
                preds = cv._forward(torch.stack([cv._preprocess_patch(patch)]))
            predmaps.append((cv._assemble_pred_map(preds, idx=0), H, W, gtb))
        for p in PROBS:
            cv._postprocessor.fg_threshold = p; tp = fn = fp = 0
            for pm, H, W, gtb in predmaps:
                inst, _ = cv._postprocessor.post_process_cell_segmentation(pm)
                a, b, c = bcounts(gtb, np.asarray(inst[:H, :W]).astype(np.int32)); tp += a; fn += b; fp += c; peri.counts("CellViT-SAM", p, a, b, c)
            add(rows, "CellViT-SAM", p, tp, fn, fp)
        del predmaps
    del cv; gc.collect(); torch.cuda.empty_cache()

    from app.infrastructure.ml_models import patho_sam_adapter as PA
    PA._add_patho_sam_to_path()
    from app.infrastructure.ml_models._patho_sam_compat import inject as inj; inj(PA._TORCH_EM_REPO)
    from micro_sam.automatic_segmentation import get_predictor_and_segmenter
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    pred_m, seg = get_predictor_and_segmenter(model_type="vit_l_histopathology", device=dev, segmentation_mode="ais", is_tiled=False)
    states = []
    for img, gtb in data:
        seg.initialize(image=img, ndim=2, verbose=False)
        states.append(({p: np.asarray(seg.generate(foreground_threshold=p, output_mode="instance_segmentation")).astype(np.int32) for p in PROBS}, gtb))
    for p in PROBS:
        tp = fn = fp = 0
        for per, gtb in states:
            a, b, c = bcounts(gtb, per[p]); tp += a; fn += b; fp += c; peri.counts("PathoSAM", p, a, b, c)
        add(rows, "PathoSAM", p, tp, fn, fp)

    pd.DataFrame(rows).to_csv(OUT, index=False)
    peri.save(OUT)  # -> boundary_pr_sweep_perimg.csv
    print(f"\nSaved -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
