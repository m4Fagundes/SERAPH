"""Boundary PR sweep (lab iftEvalBR, r=2) for CryoNuSeg (30) and IHC (266), 4 models.
Cellpose uses flow_threshold=0 (no error filter). Pick GPU via CUDA_VISIBLE_DEVICES.
Outputs: boundary_pr_sweep_cryonuseg.csv, boundary_pr_sweep_ihc.csv
"""
from __future__ import annotations
import gc, math, sys
from pathlib import Path
sys.path.insert(0, ".")
import numpy as np, pandas as pd, torch
from PIL import Image
from scipy.ndimage import maximum_filter, minimum_filter
from benchmark.evaluationMethod._perimg import PerImg

PROBS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
CRYO = Path("benchmark/data/CryoNuSeg")
IHC = Path("benchmark/data/IHC_TMA_dataset/IHC_TMA_dataset")


def borders(label, r):
    size = 2 * r + 1; lab = label.astype(np.int64)
    mx = maximum_filter(lab, size=size, mode="constant", cval=-1)
    mn = minimum_filter(lab, size=size, mode="constant", cval=-1)
    return (mx != lab) | (mn != lab)


def bcounts(gt_b, pred):
    H, W = pred.shape
    r = int(math.ceil(0.0025 * math.sqrt(H * H + W * W)))
    pb = borders(pred, r)
    return (int(np.count_nonzero(gt_b & pb)), int(np.count_nonzero(gt_b & ~pb)),
            int(np.count_nonzero(pb & ~gt_b)))


def gt_border(inst):
    H, W = inst.shape
    r = int(math.ceil(0.0025 * math.sqrt(H * H + W * W)))
    return borders(inst, r)


def load_cryo():
    data = []
    img_dir = CRYO / "tissue images"; gt_dir = CRYO / "Annotator 1 (biologist)" / "label masks"
    for ip in sorted(img_dir.glob("*.tif")):
        mp = gt_dir / f"{ip.stem}.tif"
        if mp.exists():
            data.append((np.array(Image.open(ip).convert("RGB"), dtype=np.uint8),
                         gt_border(np.array(Image.open(mp)).astype(np.int32))))
    return data


def load_ihc():
    data = []
    for ip in sorted((IHC / "images").glob("*.png")):
        mp = IHC / "masks" / f"{ip.stem}.npy"
        if mp.exists():
            m = np.load(mp); m = m[0] if m.ndim == 3 else m
            data.append((np.array(Image.open(ip).convert("RGB"), dtype=np.uint8),
                         gt_border(m.astype(np.int32))))
    return data


def add(rows, model, p, tp, fn, fp):
    br = tp / (tp + fn) if tp + fn else 0.0
    bp = tp / (tp + fp) if tp + fp else 0.0
    bf = 2 * br * bp / (br + bp) if br + bp else 0.0
    rows.append(dict(model=model, threshold=p, boundary_recall=round(br, 4),
                     boundary_precision=round(bp, 4), boundary_f=round(bf, 4)))
    print(f"  {model} p={p}: BR={br:.3f} BP={bp:.3f} BF={bf:.3f}", flush=True)


def run_base(name, data, out, pixsize):
    print(f"=== {name}: {len(data)} imgs ===", flush=True)
    rows = []
    peri = PerImg()  # per-image boundary TP/FN/FP for significance.py
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
    pd.DataFrame(rows).to_csv(out, index=False)

    sys.path.insert(0, "external/instanseg")
    from instanseg import InstanSeg
    ins = InstanSeg("brightfield_nuclei", verbosity=0)
    for p in PROBS:
        tp = fn = fp = 0
        for img, gtb in data:
            t = torch.from_numpy(img).permute(2, 0, 1).float()
            with torch.inference_mode():
                lab = ins.eval_small_image(t, pixel_size=pixsize, target="nuclei",
                                           return_image_tensor=False, seed_threshold=p)
            a, b, c = bcounts(gtb, np.asarray(lab).squeeze().astype(np.int32)); tp += a; fn += b; fp += c; peri.counts("InstanSeg", p, a, b, c)
        add(rows, "InstanSeg", p, tp, fn, fp)
    del ins; gc.collect(); torch.cuda.empty_cache()
    pd.DataFrame(rows).to_csv(out, index=False)

    from app.infrastructure.ml_models.cellvit_adapter import CellViTAdapter
    cv = CellViTAdapter(); cv._ensure_model_loaded()
    if cv._model is not None:
        P = cv.PATCH_SIZE; pm = []
        for img, gtb in data:
            H, W = img.shape[:2]
            patch = np.pad(img, ((0, max(0, P - H)), (0, max(0, P - W)), (0, 0)), mode="reflect")[:P, :P]
            with torch.no_grad():
                preds = cv._forward(torch.stack([cv._preprocess_patch(patch)]))
            pm.append((cv._assemble_pred_map(preds, idx=0), H, W, gtb))
        for p in PROBS:
            cv._postprocessor.fg_threshold = p; tp = fn = fp = 0
            for pmap, H, W, gtb in pm:
                inst, _ = cv._postprocessor.post_process_cell_segmentation(pmap)
                a, b, c = bcounts(gtb, np.asarray(inst[:H, :W]).astype(np.int32)); tp += a; fn += b; fp += c; peri.counts("CellViT-SAM", p, a, b, c)
            add(rows, "CellViT-SAM", p, tp, fn, fp)
        del pm
    del cv; gc.collect(); torch.cuda.empty_cache()
    pd.DataFrame(rows).to_csv(out, index=False)

    from app.infrastructure.ml_models import patho_sam_adapter as PA
    PA._add_patho_sam_to_path()
    from app.infrastructure.ml_models._patho_sam_compat import inject as inj; inj(PA._TORCH_EM_REPO)
    from micro_sam.automatic_segmentation import get_predictor_and_segmenter
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    _, seg = get_predictor_and_segmenter(model_type="vit_l_histopathology", device=dev,
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
    del states, seg; gc.collect(); torch.cuda.empty_cache()
    pd.DataFrame(rows).to_csv(out, index=False)
    peri.save(out)  # -> boundary_pr_sweep_{cryonuseg,ihc}_perimg.csv
    print(f"Saved -> {out}", flush=True)


def main():
    run_base("CryoNuSeg", load_cryo(), "benchmark/results/boundary_pr_sweep_cryonuseg.csv", 0.25)
    run_base("IHC", load_ihc(), "benchmark/results/boundary_pr_sweep_ihc.csv", 0.5)


if __name__ == "__main__":
    main()
