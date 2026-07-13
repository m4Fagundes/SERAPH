"""Is the 'seeded methods lose to Cellpose' result oral-specific?

Runs the seeded comparison (Cellpose end-to-end vs NuClick/iDISF seeded at the
centroids of Cellpose instances) on a SMALL sample of EACH dataset -- oral,
NuInsSeg, CryoNuSeg, IHC -- to see whether NuClick/iDISF are relatively more
competitive on the nuclei-centric sets than on full-cell oral.

Needs inference (torch+CUDA for Cellpose/NuClick; iDISF binary if --idisf).
Run on the project venv:
  ./venv/Scripts/python.exe -m benchmark.evaluationMethod.study_seeded_crossdomain --n 10
  ... --idisf            # also run iDISF (slow: one subprocess per cell)
Output: benchmark/results/study_seeded_crossdomain.csv
"""
from __future__ import annotations
import argparse, math, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, "."); sys.path.insert(0, "benchmark/evaluationMethod")
import numpy as np, pandas as pd, cv2
from PIL import Image
from scipy import ndimage
from scipy.ndimage import maximum_filter, minimum_filter
from matching import match

DATA = Path("benchmark/data")
ORAL = DATA / "oral_epithelium_activation_pack/oral_epithelium_activation_pack"
PROBS = [0.3, 0.5, 0.7]
OUT = Path("benchmark/results/study_seeded_crossdomain.csv")


def borders(label, r=2):
    size = 2 * r + 1; lab = label.astype(np.int64)
    mx = maximum_filter(lab, size=size, mode="constant", cval=-1)
    mn = minimum_filter(lab, size=size, mode="constant", cval=-1)
    return (mx != lab) | (mn != lab)


def metrics(gt, pred, gtb):
    r = match(gt, pred, 0.5); d = 2 * r.tp + r.fp + r.fn
    f1 = (2 * r.tp / d) if d else 0.0
    dices = []
    for gid, pid, _ in r.matched_pairs:
        a = gt == gid; b = pred == pid
        inter = int(np.count_nonzero(a & b))
        dices.append(2 * inter / (int(np.count_nonzero(a)) + int(np.count_nonzero(b))))
    dice = float(np.mean(dices)) if dices else float("nan")
    pb = borders(pred); btp = int((gtb & pb).sum()); bfn = int((gtb & ~pb).sum())
    br = btp / (btp + bfn) if btp + bfn else 0.0
    return f1, dice, br


def rasterize(polys, shape):
    inst = np.zeros(shape, np.int32)
    for i, poly in enumerate(polys, 1):
        if poly and len(poly) >= 3:
            cv2.fillPoly(inst, [np.array(poly, np.int32)], int(i))
    return inst


def instance_centroids(label_map):
    ids = [int(i) for i in np.unique(label_map) if i > 0]
    if not ids:
        return []
    coms = ndimage.center_of_mass(label_map > 0, label_map, ids)
    return [(int(cx), int(cy)) for cy, cx in coms]


# ---- dataset samplers: return [(name, PIL_rgb, gt_int32), ...] -------------
def load_oral(n):
    out = []
    gtd = ORAL / "oral_epithelium_db/annotations/instance"
    rgbd = ORAL / "cellpose_per_roi"
    for cls in ["severe", "healthy"]:
        for gp in sorted((gtd / cls).glob("*.png")):
            rgb = rgbd / cls / gp.stem / "roi_rgb.png"
            if rgb.exists():
                gt = np.array(Image.open(gp)).astype(np.int32)
                out.append((gp.stem, Image.open(rgb).convert("RGB"), gt))
            if len(out) >= n:
                return out
    return out


def load_nuinsseg(n):
    out = []
    root = DATA / "NuInsSeg"
    for organ in sorted(p for p in root.iterdir() if p.is_dir()):
        for ip in sorted((organ / "tissue images").glob("*.png")):
            mp = organ / "label masks" / f"{ip.stem}.tif"
            if mp.exists():
                gt = np.array(Image.open(mp)).astype(np.int32)
                out.append((ip.stem, Image.open(ip).convert("RGB"), gt))
            if len(out) >= n:
                return out
    return out


def load_cryonuseg(n):
    out = []
    d = DATA / "CryoNuSeg"
    for ip in sorted((d / "tissue images").glob("*.tif")):
        mp = d / "Annotator 1 (biologist)" / "label masks" / f"{ip.stem}.tif"
        if mp.exists():
            gt = np.array(Image.open(mp)).astype(np.int32)
            out.append((ip.stem, Image.open(ip).convert("RGB"), gt))
        if len(out) >= n:
            return out
    return out


def load_ihc(n):
    out = []
    d = DATA / "IHC_TMA_dataset/IHC_TMA_dataset"
    for ip in sorted((d / "images").glob("*.png")):
        mp = d / "masks" / f"{ip.stem}.npy"
        if mp.exists():
            m = np.load(mp); m = m[0] if m.ndim == 3 else m
            out.append((ip.stem, Image.open(ip).convert("RGB"), m.astype(np.int32)))
        if len(out) >= n:
            return out
    return out


LOADERS = {"Oral": load_oral, "NuInsSeg": load_nuinsseg,
           "CryoNuSeg": load_cryonuseg, "IHC": load_ihc}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10, help="patches per dataset")
    ap.add_argument("--idisf", action="store_true", help="also run iDISF")
    ap.add_argument("--workers", type=int, default=24,
                    help="parallel iDISF subprocess calls (CPU; machine has ~28 cores)")
    args = ap.parse_args()
    pool = ThreadPoolExecutor(max_workers=args.workers) if args.idisf else None

    from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
    from app.infrastructure.ml_models.nuclick_adapter import NuClickAdapter
    cp = CellposeAdapter(); nc = NuClickAdapter()
    idisf = None
    if args.idisf:
        from app.infrastructure.ml_models.idisf_adapter import IDISFAdapter
        idisf = IDISFAdapter(); idisf.set_parameters(iterations=4, c1=0.5, c2=0.6)

    methods = ["Cellpose", "NuClick"] + (["iDISF"] if idisf else [])
    rows = []
    peri = []  # per-image rows for bootstrap significance
    for dsname, loader in LOADERS.items():
        data = [(nm, im, gt, borders(gt)) for nm, im, gt in loader(args.n)]
        print(f"\n=== {dsname}: {len(data)} patches ===", flush=True)
        for p in PROBS:
            agg = {m: ([], [], []) for m in methods}
            for nm, img, gt, gtb in data:
                cp.segment(img, diameter=None, flow_threshold=0.0,
                           cellprob_threshold=math.log(p / (1 - p)))
                m = cp.instance_map()
                cpmap = np.asarray(m).astype(np.int32) if m is not None else np.zeros(gt.shape, np.int32)
                cents = instance_centroids(cpmap)

                preds = {"Cellpose": cpmap}
                npolys = nc.predict_batch(img, cents) if cents else []
                preds["NuClick"] = rasterize(npolys, gt.shape)
                if idisf:
                    def _one(c):
                        try: return idisf.predict(img, int(c[0]), int(c[1]))
                        except Exception: return []
                    ipolys = list(pool.map(_one, cents)) if cents else []
                    preds["iDISF"] = rasterize(ipolys, gt.shape)

                for mth in methods:
                    f1, dice, br = metrics(gt, preds[mth], gtb)
                    agg[mth][0].append(f1); agg[mth][1].append(dice); agg[mth][2].append(br)
                    peri.append(dict(dataset=dsname, method=mth, threshold=p, img=nm,
                                     f1=round(f1, 6), dice=("" if dice != dice else round(dice, 6)),
                                     br=round(br, 6)))
            for mth in methods:
                f1s, ds, brs = agg[mth]
                rows.append(dict(dataset=dsname, method=mth, threshold=p,
                                 f1=round(float(np.nanmean(f1s)), 4),
                                 dice=round(float(np.nanmean(ds)), 4),
                                 br=round(float(np.nanmean(brs)), 4)))
                print(f"  p={p} {mth:9s}: F1={rows[-1]['f1']} Dice={rows[-1]['dice']} BR={rows[-1]['br']}", flush=True)
            pd.DataFrame(rows).to_csv(OUT, index=False)
            pd.DataFrame(peri).to_csv(OUT.with_name(OUT.stem + "_perimg.csv"), index=False)

    df = pd.DataFrame(rows)
    print("\n=== best-F1 per dataset/method (does the seeded gap shrink off oral?) ===")
    for dsname in LOADERS:
        sub = df[df.dataset == dsname]
        cp_best = sub[sub.method == "Cellpose"].f1.max()
        line = [f"{dsname:10s} Cellpose={cp_best:.3f}"]
        for mth in methods[1:]:
            mb = sub[sub.method == mth].f1.max()
            line.append(f"{mth}={mb:.3f} (gap={mb - cp_best:+.3f})")
        print("  " + " | ".join(line))
    print(f"\nSaved -> {OUT}")


if __name__ == "__main__":
    main()
