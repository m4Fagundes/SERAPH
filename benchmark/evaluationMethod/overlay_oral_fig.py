"""Qualitative overlay figure (oral set) for Sec. 'protocol effect, not delineation'.

Runs Cellpose, CellViT-SAM and PathoSAM on a few oral ROIs at their best-F1 oral
thresholds (Cellpose 0.3, CellViT 0.1, PathoSAM 0.2) and renders, per model, the
pixel TP/FP/FN overlay vs the oral GT:
  green = TP   ·   red = FP (mask where GT is empty -> orphan)   ·   blue = FN (missed GT)
On the oral set the GT annotates a subset of nuclei (epithelial), so the SAM
detectors -- generic nucleus finders -- light up red where they detect real but
un-annotated nuclei. This is the documented orphan / over-detection effect.

We render several ROIs, print the FP count per model, and also save the single ROI
with the largest SAM-vs-Cellpose FP gap as the paper figure.

Predictions are cached to benchmark/cache/overlay_oral/{roi}.npz on first run, so
later tweaks to colors/legend/layout re-render instantly with NO GPU inference.
Pass --rerun to force re-inference (e.g. after changing a threshold).

Run: CUDA_VISIBLE_DEVICES=1 venv/Scripts/python.exe benchmark/evaluationMethod/overlay_oral_fig.py
Output: benchmark/results/overlay_oral_protocol.png
"""
from __future__ import annotations
import sys, math
from pathlib import Path
sys.path.insert(0, "."); sys.path.insert(0, "benchmark/evaluationMethod")
import numpy as np, matplotlib.pyplot as plt
from PIL import Image

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
GTDIR = ROOT / "oral_epithelium_db" / "annotations" / "instance"
RGBDIR = ROOT / "cellpose_per_roi"
OUT = Path("benchmark/results/overlay_oral_protocol.png")
THR = {"Cellpose": 0.3, "CellViT-SAM": 0.1, "PathoSAM": 0.2, "InstanSeg": 0.1}
# candidate ROIs to probe (severe = clearest subset-annotation effect)
ROIS = [("severe", "severe-01-roi1"), ("severe", "severe-01-roi2"),
        ("severe", "severe-02-roi1"), ("severe", "severe-03-roi1"),
        ("severe", "severe-05-roi1")]


def pixel_stats(A, B):
    tp = int((A & B).sum()); fn = int((A & ~B).sum()); fp = int((~A & B).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f1, fp


def overlay(A, Bf):
    ov = np.zeros((*A.shape, 3), np.uint8)
    ov[A & Bf] = [0, 170, 0]
    ov[~A & Bf] = [220, 0, 0]
    ov[A & ~Bf] = [40, 90, 230]
    return ov


def available(rois):
    out = []
    for cls, roi in rois:
        if (GTDIR / cls / f"{roi}.png").exists() and (RGBDIR / cls / roi / "roi_rgb.png").exists():
            out.append((cls, roi))
    return out


CACHE = Path("benchmark/cache/overlay_oral")  # one .npz per ROI with all model maps


def load_data():
    rois = available(ROIS)
    if not rois:
        cand = [(p.parent.name, p.stem) for p in sorted((GTDIR / "severe").glob("*.png"))][:5]
        rois = available(cand)
    data = []
    for cls, roi in rois:
        rgb = np.array(Image.open(RGBDIR / cls / roi / "roi_rgb.png").convert("RGB"), np.uint8)
        gt = np.array(Image.open(GTDIR / cls / f"{roi}.png")).astype(np.int32)
        data.append((cls, roi, rgb, gt, gt > 0))
    return data


def cache_complete(data):
    """True if every ROI has a cached .npz with all 4 model maps."""
    models = ["Cellpose", "CellViT-SAM", "PathoSAM", "InstanSeg"]
    for _, roi, _, _, _ in data:
        f = CACHE / f"{roi}.npz"
        if not f.exists():
            return False
        keys = set(np.load(f).files)
        if not all(m in keys for m in models):
            return False
    return True


def load_preds(data):
    preds = {}
    for _, roi, _, _, _ in data:
        z = np.load(CACHE / f"{roi}.npz")
        preds[roi] = {k: z[k] for k in z.files}
    return preds


def save_preds(data, preds):
    CACHE.mkdir(parents=True, exist_ok=True)
    for _, roi, _, _, _ in data:
        np.savez_compressed(CACHE / f"{roi}.npz", **preds[roi])
    print(f"  cached predictions -> {CACHE}", flush=True)


def run_models(data):
    """Run all 4 segmenters once each and return preds dict. Heavy: GPU inference."""
    import torch, gc
    preds = {roi: {} for _, roi, _, _, _ in data}

    from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
    cp = CellposeAdapter()
    cprob = math.log(THR["Cellpose"] / (1 - THR["Cellpose"]))
    for cls, roi, rgb, gt, A in data:
        cp.segment(Image.fromarray(rgb), diameter=None, flow_threshold=0.0, cellprob_threshold=cprob)
        m = cp.instance_map()
        preds[roi]["Cellpose"] = np.asarray(m).astype(np.int32) if m is not None else np.zeros(A.shape, np.int32)
    del cp; gc.collect(); torch.cuda.empty_cache(); print("  Cellpose done", flush=True)

    try:
        from app.infrastructure.ml_models.cellvit_adapter import CellViTAdapter
        cv = CellViTAdapter(); cv._ensure_model_loaded()
        P = cv.PATCH_SIZE; cv._postprocessor.fg_threshold = THR["CellViT-SAM"]
        for cls, roi, rgb, gt, A in data:
            H, W = A.shape
            patch = np.pad(rgb, ((0, max(0, P - H)), (0, max(0, P - W)), (0, 0)), mode="reflect")[:P, :P]
            with torch.no_grad():
                fpred = cv._forward(torch.stack([cv._preprocess_patch(patch)]))
            inst, _ = cv._postprocessor.post_process_cell_segmentation(cv._assemble_pred_map(fpred, idx=0))
            preds[roi]["CellViT-SAM"] = np.asarray(inst[:H, :W]).astype(np.int32)
        del cv; gc.collect(); torch.cuda.empty_cache(); print("  CellViT done", flush=True)
    except Exception as e:
        print(f"  CellViT FAILED: {e}", flush=True)

    try:
        sys.path.insert(0, "external/instanseg")
        from instanseg import InstanSeg
        ins = InstanSeg("brightfield_nuclei", verbosity=0)
        for cls, roi, rgb, gt, A in data:
            t = torch.from_numpy(rgb).permute(2, 0, 1).float()
            with torch.inference_mode():
                lab = ins.eval_small_image(t, pixel_size=0.25, target="nuclei",
                                           return_image_tensor=False, seed_threshold=THR["InstanSeg"])
            preds[roi]["InstanSeg"] = np.asarray(lab).squeeze().astype(np.int32)
        del ins; gc.collect(); torch.cuda.empty_cache(); print("  InstanSeg done", flush=True)
    except Exception as e:
        print(f"  InstanSeg FAILED: {e}", flush=True)

    try:
        from app.infrastructure.ml_models import patho_sam_adapter as PA
        PA._add_patho_sam_to_path()
        from app.infrastructure.ml_models._patho_sam_compat import inject as inj
        inj(PA._TORCH_EM_REPO)
        from micro_sam.automatic_segmentation import get_predictor_and_segmenter
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _, seg = get_predictor_and_segmenter(model_type="vit_l_histopathology", device=dev,
                                             segmentation_mode="ais", is_tiled=False)
        for cls, roi, rgb, gt, A in data:
            seg.initialize(image=rgb, ndim=2, verbose=False)
            inst = np.asarray(seg.generate(foreground_threshold=THR["PathoSAM"],
                              output_mode="instance_segmentation")).astype(np.int32)
            preds[roi]["PathoSAM"] = inst
        print("  PathoSAM done", flush=True)
    except Exception as e:
        print(f"  PathoSAM FAILED: {e}", flush=True)

    return preds


def render(data, preds):
    # score + pick the ROI with the largest SAM-vs-Cellpose FP gap
    best_roi, best_gap = None, -1
    models = ["Cellpose", "CellViT-SAM", "PathoSAM", "InstanSeg"]
    for cls, roi, rgb, gt, A in data:
        fps = {}
        for mdl in models:
            if mdl in preds[roi]:
                _, _, _, fp = pixel_stats(A, preds[roi][mdl] > 0)
                fps[mdl] = fp
        sam_fp = max(fps.get("CellViT-SAM", 0), fps.get("PathoSAM", 0))
        gap = sam_fp - fps.get("Cellpose", 0)
        print(f"  {roi}: FP {fps}  gap={gap}", flush=True)
        if gap > best_gap:
            best_gap, best_roi = gap, (cls, roi, rgb, gt, A)

    cls, roi, rgb, gt, A = best_roi
    H, W = A.shape
    mdls = [m for m in models if m in preds[roi]]

    # 3 rows x 2 cols: (RGB, GT) / (Cellpose, CellViT) / (PathoSAM, InstanSeg)
    gt_ov = np.zeros((H, W, 3), np.uint8); gt_ov[A] = [255, 255, 255]
    panels = [("H&E", rgb, None), (f"Ground truth ({len(np.unique(gt))-1} nuclei)", gt_ov, None)]
    for mdl in mdls:
        Bf = preds[roi][mdl] > 0
        ninst = len(np.unique(preds[roi][mdl])) - 1
        p, r, f1, _ = pixel_stats(A, Bf)
        panels.append((f"{mdl}  ({ninst} nuclei)\npixel-F1={f1:.2f}  P={p:.2f}  R={r:.2f}",
                       overlay(A, Bf), None))

    fig, axes = plt.subplots(3, 2, figsize=(8.6, 12.0))
    axes = axes.ravel()
    for ax, (title, img, _) in zip(axes, panels):
        ax.imshow(img); ax.set_title(title, fontsize=11); ax.axis("off")
    for ax in axes[len(panels):]:
        ax.axis("off")

    fig.suptitle(f"Pixel agreement with the ground truth — oral epithelium ({roi})",
                 fontsize=13, y=0.97)
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=(0, 170 / 255, 0), label="correct (TP)"),
               Patch(facecolor=(220 / 255, 0, 0), label="extra model detection (FP / orphan)"),
               Patch(facecolor=(40 / 255, 90 / 255, 230 / 255), label="missed GT (FN)")]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=12, frameon=False,
               bbox_to_anchor=(0.5, 0.025), handlelength=1.2, handleheight=1.2, columnspacing=2.5)
    fig.tight_layout(rect=[0, 0.05, 1, 0.95])
    fig.savefig(OUT, dpi=140, bbox_inches="tight")
    print(f"Saved -> {OUT}  (ROI={roi}, FP gap={best_gap})", flush=True)


def main():
    force = "--rerun" in sys.argv
    data = load_data()
    print("ROIs:", [r for _, r, _, _, _ in data], flush=True)
    if not force and cache_complete(data):
        print("  using cached predictions (pass --rerun to re-infer)", flush=True)
        preds = load_preds(data)
    else:
        preds = run_models(data)
        save_preds(data, preds)
    render(data, preds)


if __name__ == "__main__":
    main()
