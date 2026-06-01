"""Evaluate SERAPH exported instance masks against exported GT masks.

Use this runner after File > Export > Export Instance Masks... in SERAPH.
The export writes one *_instance_masks_manifest.csv plus TIFF/NPY masks. This
script groups masks by slice, finds the ground-truth layer, and compares every
prediction layer with the GT using the benchmark metrics.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from .matching import match
    from .metrics import compute_metrics
except ImportError:
    from matching import match
    from metrics import compute_metrics


GT_HINTS = ("gt", "ground", "patholog")


def run_exported_masks(
    manifest: str | Path,
    output: str | Path = "results.csv",
    iou_threshold: float = 0.5,
) -> pd.DataFrame:
    """Evaluate all exported prediction masks against the exported GT layer."""
    manifest = Path(manifest)
    export_dir = manifest.parent
    df = pd.read_csv(manifest)

    rows: list[dict] = []
    for slice_index, group in df.groupby("slice_index", sort=True):
        gt_rows = group[group.apply(_is_gt_row, axis=1)]
        if gt_rows.empty:
            print(f"slice {slice_index}: SKIP, no GT layer in manifest")
            continue

        gt_row = gt_rows.iloc[0]
        gt = _load_mask(export_dir / str(gt_row["npy"]))

        pred_rows = group[~group.index.isin(gt_rows.index)]
        for _, pred_row in pred_rows.iterrows():
            pred = _load_mask(export_dir / str(pred_row["npy"]))
            if pred.shape != gt.shape:
                print(
                    f"slice {slice_index}: SKIP {pred_row['layer']}, "
                    f"shape {pred.shape} != GT {gt.shape}"
                )
                continue

            result = match(gt, pred, iou_threshold=iou_threshold)
            metrics = compute_metrics(gt, pred, result)
            rows.append({
                "slice_index": int(slice_index),
                "slice_name": gt_row.get("slice_name", ""),
                "layer": pred_row.get("layer", ""),
                "model": pred_row.get("model", ""),
                "source_kind": pred_row.get("source_kind", ""),
                "gt_layer": gt_row.get("layer", ""),
                "gt_instances": int(gt.max()) if gt.size else 0,
                "pred_instances": int(pred.max()) if pred.size else 0,
                "tp": result.tp,
                "fp": result.fp,
                "fn": result.fn,
                **metrics,
            })

    out_df = pd.DataFrame(rows)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output, index=False)
    return out_df


def _is_gt_row(row) -> bool:
    text = " ".join(str(row.get(key, "")) for key in ("layer", "model", "source_kind")).lower()
    return any(hint in text for hint in GT_HINTS)


def _load_mask(path: Path) -> np.ndarray:
    return np.load(path).astype(np.int32, copy=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate masks exported by SERAPH Export Instance Masks"
    )
    parser.add_argument("--manifest", required=True, help="Path to *_instance_masks_manifest.csv")
    parser.add_argument("--output", default="benchmark/results/results.csv", help="Output CSV path")
    parser.add_argument("--iou_threshold", type=float, default=0.5, help="TP IoU threshold")
    args = parser.parse_args()

    df = run_exported_masks(
        manifest=args.manifest,
        output=args.output,
        iou_threshold=args.iou_threshold,
    )
    print(f"Saved {len(df)} rows -> {args.output}")


if __name__ == "__main__":
    main()
