"""
Add GT instance mask contours as a new segmentation layer in each XML tile.

Reads:
  GT/severe_sliceN_tile.xml                                      (tile XMLs)
  oral_epithelium_db/annotations/instance/severe/{roi}.png       (GT masks)

Writes:
  GT/severe_sliceN_tile.xml  — modified in-place
  Adds <nucleus source="GT (pathologist)"> elements to <segmentations>.

Run:
  python -m benchmark.evaluationMethod.add_gt_to_xml
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image
from skimage.measure import approximate_polygon, find_contours

GT_SOURCE    = "GT (pathologist)"
DATASET_ROOT = Path(r"E:\oral_epithelium_activation_pack\oral_epithelium_activation_pack")
GT_DIR       = Path(__file__).parents[2] / "GT"
SIMPLIFY_TOL = 1.5   # pixels; lower = more points, higher = smoother polygons


def _instance_contour(binary: np.ndarray) -> list[tuple[int, int]] | None:
    """Return simplified [(x, y), ...] polygon for a binary instance mask."""
    contours = find_contours(binary, level=0.5)
    if not contours:
        return None
    outer = max(contours, key=len)
    simplified = approximate_polygon(outer, tolerance=SIMPLIFY_TOL)
    # find_contours returns (row, col) → XML convention is x=col, y=row
    return [(int(round(c[1])), int(round(c[0]))) for c in simplified]


def process_xml(xml_path: Path) -> int:
    """Inject GT nuclei into one XML. Returns number of nuclei added (0 = skipped)."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    slice_el = root.find("slice")
    roi_name = slice_el.attrib["name"]
    bounds   = slice_el.find("bounds").attrib
    x1, y1   = int(bounds["x1"]), int(bounds["y1"])
    width    = int(bounds["x2"]) - x1
    height   = int(bounds["y2"]) - y1
    shape    = (height, width)

    cls     = roi_name.split("-")[0]
    gt_path = (
        DATASET_ROOT
        / "oral_epithelium_db"
        / "annotations"
        / "instance"
        / cls
        / f"{roi_name}.png"
    )

    if not gt_path.exists():
        return 0

    gt           = np.array(Image.open(gt_path)).astype(np.int32)
    instance_ids = [i for i in np.unique(gt) if i != 0]

    segmentations = slice_el.find("segmentations")

    # Remove any GT layer from a previous run so re-runs are idempotent
    for n in list(segmentations.findall("nucleus")):
        if n.attrib.get("source") == GT_SOURCE:
            segmentations.remove(n)

    existing_ids = [int(n.attrib.get("id", -1)) for n in segmentations.findall("nucleus")]
    next_id      = max(existing_ids, default=-1) + 1

    added = 0
    for iid in instance_ids:
        points = _instance_contour(gt == iid)
        if points is None or len(points) < 3:
            continue

        nuc = ET.SubElement(segmentations, "nucleus")
        nuc.set("id",     str(next_id))
        nuc.set("source", GT_SOURCE)
        next_id += 1

        for (px, py) in points:
            # Clip to tile bounds then shift to absolute slide coordinates
            px_abs = int(np.clip(px, 0, width  - 1)) + x1
            py_abs = int(np.clip(py, 0, height - 1)) + y1
            pt = ET.SubElement(nuc, "point")
            pt.set("x", str(px_abs))
            pt.set("y", str(py_abs))

        added += 1

    ET.indent(root, space="  ")
    tree.write(str(xml_path), encoding="utf-8", xml_declaration=True)
    return added


def main() -> None:
    xml_files = sorted(GT_DIR.glob("*_tile.xml"))
    if not xml_files:
        print(f"No *_tile.xml files found in {GT_DIR}")
        return

    total_added  = 0
    total_tiles  = 0
    skipped      = 0

    for xml_path in xml_files:
        n = process_xml(xml_path)
        if n:
            print(f"  {xml_path.name}: +{n} GT nuclei")
            total_added += n
            total_tiles += 1
        else:
            print(f"  {xml_path.name}: skipped (no GT PNG)")
            skipped += 1

    print(f"\nDone. Added {total_added} GT nuclei across {total_tiles} tiles ({skipped} skipped).")


if __name__ == "__main__":
    main()
