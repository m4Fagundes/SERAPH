"""Convert a dataset GT instance PNG into a SERAPH tile XML.

The generated *_gt_tile.xml can be imported via SERAPH's "Import Tile" and the
ground truth appears as a new segmentation layer named ``gt-pathology``
(the import normalizes the source string automatically).

Each ROI is emitted as a self-contained grid tile whose source image is the
ROI's ``roi_rgb.png`` (origin 0,0), so polygon coordinates equal the pixel
coordinates inside the ROI — no slide offset needed.

Workflow:
    1. Open the ROI image in SERAPH (the same roi_rgb.png referenced here).
    2. File > Import Tile... > pick the generated <roi>_gt_tile.xml.
    3. The GT shows up as the ``gt-pathology`` layer.

Usage:
    python -m benchmark.evaluationMethod.gt_to_tile_xml --roi severe-01-roi1
    python -m benchmark.evaluationMethod.gt_to_tile_xml --all --class severe
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from app.infrastructure.tile_xml import write_tile_xml

DATASET_ROOT = Path(
    "benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack"
)
OUT_DIR = Path("benchmark/data/exports/gt_tiles")


def _instance_polygons(label: np.ndarray) -> list[dict]:
    """Extract one polygon per instance ID as {'polygon': [(x,y)...], 'model': ...}."""
    import cv2

    segs: list[dict] = []
    for uid in np.unique(label[label > 0]):
        mask = (label == uid).astype(np.uint8)
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        if len(contour) < 3:
            continue
        poly = [(int(pt[0][0]), int(pt[0][1])) for pt in contour]
        segs.append({"polygon": poly, "model": "gt-pathology"})
    return segs


def _gt_png(roi: str) -> Path:
    cls = roi.split("-")[0]
    return DATASET_ROOT / "oral_epithelium_db" / "annotations" / "instance" / cls / f"{roi}.png"


def _roi_rgb(roi: str) -> Path:
    cls = roi.split("-")[0]
    return DATASET_ROOT / "cellpose_per_roi" / cls / roi / "roi_rgb.png"


def build_xml(roi: str, out_dir: Path = OUT_DIR) -> Path:
    gt_path = _gt_png(roi)
    if not gt_path.exists():
        raise FileNotFoundError(f"No GT PNG for {roi}: {gt_path}")

    label = np.array(Image.open(gt_path)).astype(np.int32)
    h, w = label.shape
    segs = _instance_polygons(label)

    rgb_path = _roi_rgb(roi)
    out_dir.mkdir(parents=True, exist_ok=True)
    xml_path = out_dir / f"{roi}_gt_tile.xml"

    import os
    abs_src = str(rgb_path.resolve()) if rgb_path.exists() else ""
    try:
        rel_src = os.path.relpath(abs_src, out_dir) if abs_src else ""
    except ValueError:
        rel_src = abs_src

    descriptor = {
        "source": {"abs_path": abs_src, "rel_path": rel_src, "width": w, "height": h},
        "grid": {"w": 1000, "h": 1000, "color": "#FFFF00"},
        "slice": {
            "name": roi,
            "description": f"Ground truth instance mask ({len(segs)} nuclei)",
            "microns_per_pixel": "",
            "bounds": {"x1": 0, "y1": 0, "x2": w, "y2": h},
            "rects": [(0, 0, w, h)],
            "polygon": None,  # grid slice
            "pixel_mask": [],
            "segmentations": segs,
        },
    }
    write_tile_xml(str(xml_path), descriptor)
    print(f"{roi}: {len(segs)} nuclei -> {xml_path}")
    return xml_path


def main() -> None:
    p = argparse.ArgumentParser(description="Generate SERAPH tile XML from GT instance PNG")
    p.add_argument("--roi", help="ROI name, e.g. severe-01-roi1")
    p.add_argument("--all", action="store_true", help="All ROIs that have a GT PNG")
    p.add_argument("--class", dest="cls", default="severe", help="Class for --all (severe/healthy)")
    p.add_argument("--out", default=str(OUT_DIR), help="Output directory")
    args = p.parse_args()

    out_dir = Path(args.out)
    if args.all:
        gt_dir = DATASET_ROOT / "oral_epithelium_db" / "annotations" / "instance" / args.cls
        rois = sorted(p.stem for p in gt_dir.glob("*.png"))
        for roi in rois:
            build_xml(roi, out_dir)
        print(f"\nDone: {len(rois)} GT tile XML(s) in {out_dir}")
    elif args.roi:
        build_xml(args.roi, out_dir)
    else:
        p.error("provide --roi <name> or --all")


if __name__ == "__main__":
    main()
