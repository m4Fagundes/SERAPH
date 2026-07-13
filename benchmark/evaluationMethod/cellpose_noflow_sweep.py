"""Cellpose threshold sweep WITHOUT the flow-error filter (flow_threshold=0) vs WITH it (0.4).

For each cellprob threshold (p in 0.1..0.9, cellprob=logit(p)), pooled over 100 ROIs:
  - n_instances
  - instance precision/recall (IoU@0.5 matching)   -> shows if the "hook" disappears
  - pixel foreground precision/recall
Compares flow_threshold = 0.0 (filter OFF) vs 0.4 (default).
Output: cellpose_noflow_sweep.csv
"""
from __future__ import annotations
import math, sys
from pathlib import Path
import numpy as np, pandas as pd
from PIL import Image

sys.path.insert(0, "benchmark/evaluationMethod")
from matching import match

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
GTDIR = ROOT / "oral_epithelium_db" / "annotations" / "instance"
RGBDIR = ROOT / "cellpose_per_roi"
PROBS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def main():
    data = []
    for cls in ["severe", "healthy"]:
        for p in sorted((GTDIR / cls).glob("*.png")):
            rgb = RGBDIR / cls / p.stem / "roi_rgb.png"
            if rgb.exists():
                gt = np.array(Image.open(p)).astype(np.int32)
                data.append((np.array(Image.open(rgb).convert("RGB"), dtype=np.uint8), gt))
    print(f"{len(data)} ROIs", flush=True)

    from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
    cp = CellposeAdapter()
    rows = []
    for flow in [0.0, 0.4]:
        for p in PROBS:
            itp = ifp = ifn = 0          # instance
            ptp = pfn = pfp = 0          # pixel foreground
            ninst = 0
            for img, gt in data:
                cp.segment(Image.fromarray(img), diameter=None, flow_threshold=flow,
                           cellprob_threshold=math.log(p / (1 - p)))
                m = cp.instance_map()
                m = np.asarray(m).astype(np.int32) if m is not None else np.zeros_like(gt)
                ninst += len(np.unique(m[m > 0]))
                r = match(gt, m, 0.5); itp += r.tp; ifp += r.fp; ifn += r.fn
                A = gt > 0; B = m > 0
                ptp += int((A & B).sum()); pfn += int((A & ~B).sum()); pfp += int((~A & B).sum())
            iprec = itp / (itp + ifp) if itp + ifp else 0
            irec = itp / (itp + ifn) if itp + ifn else 0
            pprec = ptp / (ptp + pfp) if ptp + pfp else 0
            prec_rec = ptp / (ptp + pfn) if ptp + pfn else 0
            rows.append(dict(flow_threshold=flow, threshold=p, n_instances=ninst,
                             inst_prec=round(iprec, 4), inst_rec=round(irec, 4),
                             inst_f1=round(2 * itp / (2 * itp + ifp + ifn), 4) if itp else 0,
                             pix_prec=round(pprec, 4), pix_rec=round(prec_rec, 4)))
            print(f"  flow={flow} p={p}: n={ninst} | inst P={iprec:.3f} R={irec:.3f} | pix P={pprec:.3f} R={prec_rec:.3f}", flush=True)

    pd.DataFrame(rows).to_csv("benchmark/results/cellpose_noflow_sweep.csv", index=False)
    print("\nSaved -> benchmark/results/cellpose_noflow_sweep.csv", flush=True)


if __name__ == "__main__":
    main()
