"""
Batch runner for nuclei segmentation benchmark.

Iterates over all XML tiles in GT/, loads GT + all three predictions,
runs matching and metrics for each method, and returns a DataFrame
with one row per tile-method pair.

Usage (Python):
    from benchmark.evaluationMethod.runner import run_batch
    df = run_batch(gt_dir="GT/", dataset_root="E:/...", iou_threshold=0.5)

Usage (CLI):
    python -m benchmark.evaluationMethod.runner --gt_dir GT/ --dataset_root E:/... --output results.csv
    python -m benchmark.evaluationMethod.runner --gt_dir GT/ --dataset_root E:/... --iou_threshold 0.3 --output results_03.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

try:
    from .loader import load_tile
    from .matching import match
    from .metrics import compute_metrics
except ImportError:
    from loader import load_tile
    from matching import match
    from metrics import compute_metrics

METHODS = ["cellpose", "cellvit_sam", "pathosam_vitl"]


def run_batch(
    gt_dir: str | Path,
    dataset_root: str | Path,
    iou_threshold: float = 0.5,
    verbose: bool = True,
) -> pd.DataFrame:
    """Evaluate all methods on all tiles.

    Args:
        gt_dir:        Directory containing SERAPH XML tile files.
        dataset_root:  Root of oral_epithelium_activation_pack/oral_epithelium_activation_pack/.
        iou_threshold: IoU threshold for TP classification (default 0.5).
        verbose:       Print per-tile progress to stdout.

    Returns:
        DataFrame with columns: tile, method, + all metric columns.
        Tiles that fail to load are silently skipped (reason logged to stderr).
    """
    gt_dir = Path(gt_dir)
    xml_files = sorted(gt_dir.glob("*.xml"))

    if not xml_files:
        raise FileNotFoundError(f"No XML files found in {gt_dir}")

    rows: list[dict] = []
    n_total = len(xml_files)
    n_skipped = 0

    for i, xml_path in enumerate(xml_files, 1):
        tile_name = xml_path.stem
        if verbose:
            print(f"[{i:3d}/{n_total}] {tile_name}", end="  ", flush=True)

        try:
            masks = load_tile(xml_path, dataset_root)
        except Exception as exc:
            print(f"SKIP — {exc}", file=sys.stderr)
            n_skipped += 1
            if verbose:
                print("SKIP")
            continue

        gt = masks["gt"]
        for method in METHODS:
            pred = masks[method]
            result = match(gt, pred, iou_threshold=iou_threshold)
            metrics = compute_metrics(gt, pred, result)
            rows.append({"tile": tile_name, "method": method, **metrics})

        if verbose:
            print("ok")

    if verbose:
        n_ok = n_total - n_skipped
        print(f"\nDone: {n_ok}/{n_total} tiles processed, {n_skipped} skipped.")

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nuclei segmentation benchmark — batch evaluation runner"
    )
    parser.add_argument(
        "--gt_dir", required=True,
        help="Directory containing SERAPH XML tile files (e.g. GT/)",
    )
    parser.add_argument(
        "--dataset_root", required=True,
        help="Dataset root (oral_epithelium_activation_pack/oral_epithelium_activation_pack/)",
    )
    parser.add_argument(
        "--output", default="results.csv",
        help="Output CSV path (default: results.csv)",
    )
    parser.add_argument(
        "--iou_threshold", type=float, default=0.5,
        help="IoU threshold for TP classification (default: 0.5)",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-tile progress output",
    )
    args = parser.parse_args()

    df = run_batch(
        gt_dir=args.gt_dir,
        dataset_root=args.dataset_root,
        iou_threshold=args.iou_threshold,
        verbose=not args.quiet,
    )

    output = Path(args.output)
    df.to_csv(output, index=False)
    print(f"Saved {len(df)} rows → {output}")


if __name__ == "__main__":
    main()
