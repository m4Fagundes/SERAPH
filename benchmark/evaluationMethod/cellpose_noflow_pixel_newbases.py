"""Cellpose WITHOUT error filter (flow_threshold=0) — pixel V1/V2 — on NuInsSeg (665) and IHC (266).
Fills the gap so every figure uses Cellpose no-flow.
Outputs: cellpose_noflow_pixel_nuinsseg.csv, cellpose_noflow_pixel_ihc.csv
"""
from __future__ import annotations
import math, sys
from pathlib import Path
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from PIL import Image

PROBS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
NUIN = Path("benchmark/data/NuInsSeg")
IHC = Path("benchmark/data/IHC_TMA_dataset/IHC_TMA_dataset")


def load_nuinsseg():
    data = []
    for organ in sorted(p for p in NUIN.iterdir() if p.is_dir()):
        for ip in sorted((organ / "tissue images").glob("*.png")):
            mp = organ / "label masks" / f"{ip.stem}.tif"
            if mp.exists():
                A = np.array(Image.open(mp)).astype(np.int32) > 0
                data.append((np.array(Image.open(ip).convert("RGB"), dtype=np.uint8), A))
    return data


def load_ihc():
    data = []
    for ip in sorted((IHC / "images").glob("*.png")):
        mp = IHC / "masks" / f"{ip.stem}.npy"
        if mp.exists():
            m = np.load(mp)
            if m.ndim == 3:
                m = m[0]
            data.append((np.array(Image.open(ip).convert("RGB"), dtype=np.uint8), m.astype(np.int32) > 0))
    return data


def counts(A, B):
    return (int(np.count_nonzero(A & B)), int(np.count_nonzero(A & ~B)),
            int(np.count_nonzero(~A & B)), int(np.count_nonzero(~A & ~B)))


def run(name, data, out, cp):
    rows = []
    for p in PROBS:
        tp = fn = fp = tn = 0
        for img, A in data:
            cp.segment(Image.fromarray(img), diameter=None, flow_threshold=0.0,
                       cellprob_threshold=math.log(p / (1 - p)))
            m = cp.instance_map(); B = (np.asarray(m) > 0) if m is not None else np.zeros_like(A)
            a, b, c, d = counts(A, B); tp += a; fn += b; fp += c; tn += d
        v1p = tp / (tp + fp) if tp + fp else 0.0
        v1r = tp / (tp + fn) if tp + fn else 0.0
        ac = tp + tn
        v2p = ac / (ac + fp) if ac + fp else 0.0
        v2r = ac / (ac + fn) if ac + fn else 0.0
        rows.append(dict(model="Cellpose", threshold=p, v1_prec=round(v1p, 4), v1_rec=round(v1r, 4),
                         v2_prec=round(v2p, 4), v2_rec=round(v2r, 4)))
        print(f"  [{name}] p={p}: V1 P={v1p:.3f} R={v1r:.3f}", flush=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"Saved -> {out}", flush=True)


def main():
    from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
    cp = CellposeAdapter()
    print("Loading IHC...", flush=True)
    run("IHC", load_ihc(), "benchmark/results/cellpose_noflow_pixel_ihc.csv", cp)
    print("Loading NuInsSeg...", flush=True)
    run("NuInsSeg", load_nuinsseg(), "benchmark/results/cellpose_noflow_pixel_nuinsseg.csv", cp)


if __name__ == "__main__":
    main()
