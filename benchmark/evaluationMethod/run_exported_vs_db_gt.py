"""Evaluate SERAPH exported instance masks against the dataset's PNG GT.

Use this runner when the SERAPH export contains ONLY model predictions (no GT
layer) and the ground truth lives in the activation pack as per-ROI instance
PNGs:

    <dataset_root>/oral_epithelium_db/annotations/instance/<class>/<roi>.png

It reads the export manifest, maps each prediction's ``slice_name`` (e.g.
``severe-01-roi1``) to its GT PNG, and runs the SAME matching + metrics used by
the other runners. Predictions whose ROI has no GT PNG are skipped and reported.

Usage (CLI):
    python -m benchmark.evaluationMethod.run_exported_vs_db_gt \
        --manifest benchmark/data/exports/run1/severe_instance_masks_manifest.csv \
        --dataset_root benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack \
        --output benchmark/results/results.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

try:
    from .matching import match
    from .metrics import compute_metrics
except ImportError:
    from matching import match
    from metrics import compute_metrics


def _gt_path(dataset_root: Path, roi_name: str) -> Path:
    """Resolve the instance-GT PNG path for a ROI name like 'severe-01-roi1'."""
    cls = roi_name.split("-")[0]
    return (
        dataset_root
        / "oral_epithelium_db"
        / "annotations"
        / "instance"
        / cls
        / f"{roi_name}.png"
    )


def _load_gt(path: Path) -> np.ndarray:
    return np.array(Image.open(path)).astype(np.int32, copy=False)


def _load_pred(path: Path) -> np.ndarray:
    return np.load(path).astype(np.int32, copy=False)


def run(
    manifest: str | Path,
    dataset_root: str | Path,
    output: str | Path = "benchmark/results/results.csv",
    iou_threshold: float = 0.5,
    verbose: bool = True,
) -> pd.DataFrame:
    manifest = Path(manifest)
    dataset_root = Path(dataset_root)
    export_dir = manifest.parent
    df = pd.read_csv(manifest)

    rows: list[dict] = []
    skipped_no_gt: set[str] = set()
    skipped_shape = 0

    for _, pred_row in df.iterrows():
        roi = str(pred_row["slice_name"])
        gt_path = _gt_path(dataset_root, roi)
        if not gt_path.exists():
            skipped_no_gt.add(roi)
            continue

        gt = _load_gt(gt_path)
        pred = _load_pred(export_dir / str(pred_row["npy"]))
        if pred.shape != gt.shape:
            skipped_shape += 1
            if verbose:
                print(
                    f"SKIP {roi} / {pred_row['layer']}: "
                    f"pred {pred.shape} != GT {gt.shape}"
                )
            continue

        result = match(gt, pred, iou_threshold=iou_threshold)
        metrics = compute_metrics(gt, pred, result)
        rows.append({
            "slice_index": int(pred_row["slice_index"]),
            "roi": roi,
            "layer": pred_row.get("layer", ""),
            "model": pred_row.get("model", ""),
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

    if verbose:
        n_roi_eval = out_df["roi"].nunique() if not out_df.empty else 0
        print(f"\nEvaluated {len(out_df)} prediction(s) across {n_roi_eval} ROI(s).")
        if skipped_no_gt:
            print(
                f"Skipped {len(skipped_no_gt)} ROI(s) with no GT PNG "
                f"(not annotated in the dataset)."
            )
        if skipped_shape:
            print(f"Skipped {skipped_shape} prediction(s) on shape mismatch.")
        print(f"Saved -> {output}")

    return out_df


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate SERAPH exported masks against dataset PNG GT"
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument(
        "--dataset_root",
        default="benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack",
    )
    parser.add_argument("--output", default="benchmark/results/results.csv")
    parser.add_argument("--iou_threshold", type=float, default=0.5)
    args = parser.parse_args()

    run(
        manifest=args.manifest,
        dataset_root=args.dataset_root,
        output=args.output,
        iou_threshold=args.iou_threshold,
    )


if __name__ == "__main__":
    main()
