"""Boundary PR sweep (lab iftEvalBR, r=2) on NuInsSeg FULL (665 patches), 4 models.
Cellpose runs WITHOUT the error filter (flow_threshold=0) so it does not drop cells.

Per threshold (pooled): boundary TP/FN/FP -> BR=TP/(TP+FN), BP=TP/(TP+FP), BF=2BR*BP/(BR+BP).
Knob: Cellpose cellprob=logit(p) (flow=0); CellViT fg; PathoSAM AIS fg; InstanSeg seed. p in 0.1..0.9.
Output: boundary_pr_sweep_nuinsseg.csv  (Cellpose line = no error filter)
"""
from __future__ import annotations
import gc, math, sys
from pathlib import Path
sys.path.insert(0, ".")
import numpy as np, pandas as pd, torch
from PIL import Image
from scipy.ndimage import maximum_filter, minimum_filter
from benchmark.evaluationMethod._perimg import PerImg

ROOT = Path("benchmark/data/NuInsSeg")
PROBS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
OUT = Path("benchmark/results/boundary_pr_sweep_nuinsseg.csv")


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
    for organ in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        for ip in sorted((organ / "tissue images").glob("*.png")):
            mp = organ / "label masks" / f"{ip.stem}.tif"
            if mp.exists():
                lab = np.array(Image.open(mp)).astype(np.int32)
                H, W = lab.shape
                r = int(math.ceil(0.0025 * math.sqrt(H * H + W * W)))
                data.append((np.array(Image.open(ip).convert("RGB"), dtype=np.uint8), borders(lab, r)))
    return data


def add(rows, model, p, tp, fn, fp):
    br = tp / (tp + fn) if tp + fn else 0.0
    bp = tp / (tp + fp) if tp + fp else 0.0
    bf = 2 * br * bp / (br + bp) if br + bp else 0.0
    rows.append(dict(model=model, threshold=p, boundary_recall=round(br, 4),
                     boundary_precision=round(bp, 4), boundary_f=round(bf, 4)))
    print(f"  {model} p={p}: BR={br:.3f} BP={bp:.3f} BF={bf:.3f}", flush=True)


def main():
    data = load_data(); print(f"{len(data)} patches NuInsSeg", flush=True)
    rows = []
    peri = PerImg()  # per-image boundary TP/FN/FP for significance.py

    # ---- Cellpose WITHOUT error filter (flow_threshold=0) ----
    from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
    cp = CellposeAdapter()
    for p in PROBS:
        tp = fn = fp = 0
        for img, gtb in data:
            cp.segment(Image.fromarray(img), diameter=None, flow_threshold=0.0,
                       cellprob_threshold=math.log(p / (1 - p)))
            m = cp.instance_map(); m = np.asarray(m).astype(np.int32) if m is not None else np.zeros(gtb.shape, np.int32)
            a, b, c = bcounts(gtb, m); tp += a; fn += b; fp += c; peri.counts("Cellpose", p, a, b, c)
        add(rows, "Cellpose", p, tp, fn, fp)
    del cp; gc.collect(); torch.cuda.empty_cache()
    pd.DataFrame(rows).to_csv(OUT, index=False)

    # ---- InstanSeg ----
    sys.path.insert(0, "external/instanseg")
    from instanseg import InstanSeg
    ins = InstanSeg("brightfield_nuclei", verbosity=0)
    for p in PROBS:
        tp = fn = fp = 0
        for img, gtb in data:
            t = torch.from_numpy(img).permute(2, 0, 1).float()
            with torch.inference_mode():
                lab = ins.eval_small_image(t, pixel_size=0.5, target="nuclei",
                                           return_image_tensor=False, seed_threshold=p)
            a, b, c = bcounts(gtb, np.asarray(lab).squeeze().astype(np.int32)); tp += a; fn += b; fp += c; peri.counts("InstanSeg", p, a, b, c)
        add(rows, "InstanSeg", p, tp, fn, fp)
    del ins; gc.collect(); torch.cuda.empty_cache()
    pd.DataFrame(rows).to_csv(OUT, index=False)

    # ---- CellViT-SAM ----
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
    pd.DataFrame(rows).to_csv(OUT, index=False)

    # ---- PathoSAM ----
    from app.infrastructure.ml_models import patho_sam_adapter as PA
    PA._add_patho_sam_to_path()
    from app.infrastructure.ml_models._patho_sam_compat import inject as inj; inj(PA._TORCH_EM_REPO)
    from micro_sam.automatic_segmentation import get_predictor_and_segmenter
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    pred_m, seg = get_predictor_and_segmenter(model_type="vit_l_histopathology", device=dev,
                                              segmentation_mode="ais", is_tiled=False)
    states = []
    for img, gtb in data:
        seg.initialize(image=img, ndim=2, verbose=False)
        states.append(({p: np.asarray(seg.generate(foreground_threshold=p,
                       output_mode="instance_segmentation")).astype(np.int32) for p in PROBS}, gtb))
    for p in PROBS:
        tp = fn = fp = 0
        for per, gtb in states:
            a, b, c = bcounts(gtb, per[p]); tp += a; fn += b; fp += c; peri.counts("PathoSAM", p, a, b, c)
        add(rows, "PathoSAM", p, tp, fn, fp)

    pd.DataFrame(rows).to_csv(OUT, index=False)
    peri.save(OUT)  # -> boundary_pr_sweep_nuinsseg_perimg.csv
    print(f"\nSaved -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
