"""
Loader for nuclei segmentation benchmark.

For each tile (XML from SERAPH), returns instance mask arrays for:
  - gt           : ground truth (PNG, uint8 → int32)
  - cellpose     : Cellpose predictions (npy int32)
  - cellvit_sam  : CellViT-SAM predictions (rasterised from XML polygons)
  - pathosam_vitl: PathoSAM ViT-L predictions (rasterised from XML polygons)

All arrays: shape (H, W), dtype int32, pixel = instance ID, 0 = background.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image
from skimage.draw import polygon as sk_polygon


# Source attribute strings as they appear in the XML
_SOURCE_CELLVIT = "CellViT-SAM"
_SOURCE_PATHOSAM = "PathoSAM (ViT-L)"


def load_tile(xml_path: str | Path, dataset_root: str | Path) -> dict[str, np.ndarray]:
    """Load all four instance mask arrays for one tile.

    Args:
        xml_path: Path to a SERAPH tile XML (e.g. GT/severe_slice1_tile.xml).
        dataset_root: Root of oral_epithelium_activation_pack/oral_epithelium_activation_pack/.

    Returns:
        Dict with keys "gt", "cellpose", "cellvit_sam", "pathosam_vitl",
        each a (H, W) int32 ndarray.
    """
    xml_path = Path(xml_path)
    dataset_root = Path(dataset_root)

    tree = ET.parse(xml_path)
    root = tree.getroot()

    slice_el = root.find("slice")
    roi_name = slice_el.attrib["name"]          # e.g. "severe-01-roi1"
    bounds = slice_el.find("bounds").attrib
    x1, y1 = int(bounds["x1"]), int(bounds["y1"])
    width   = int(bounds["x2"]) - x1
    height  = int(bounds["y2"]) - y1
    shape   = (height, width)

    # class prefix: "severe" or "healthy"
    cls = roi_name.split("-")[0]

    gt       = _load_gt(dataset_root, cls, roi_name, shape)
    cellpose = _load_cellpose(dataset_root, cls, roi_name, shape)

    nuclei = slice_el.findall("segmentations/nucleus")
    cellvit  = _rasterise(nuclei, _SOURCE_CELLVIT, shape, origin=(x1, y1))
    pathosam = _rasterise(nuclei, _SOURCE_PATHOSAM, shape, origin=(x1, y1))

    return {
        "gt":            gt,
        "cellpose":      cellpose,
        "cellvit_sam":   cellvit,
        "pathosam_vitl": pathosam,
    }


def _load_gt(root: Path, cls: str, roi_name: str, shape: tuple[int, int]) -> np.ndarray:
    path = root / "oral_epithelium_db" / "annotations" / "instance" / cls / f"{roi_name}.png"
    arr = np.array(Image.open(path)).astype(np.int32)
    _check_shape(arr, shape, "GT", roi_name)
    return arr


def _load_cellpose(root: Path, cls: str, roi_name: str, shape: tuple[int, int]) -> np.ndarray:
    path = root / "cellpose_per_roi" / cls / roi_name / "cellpose_masks_int32.npy"
    arr = np.load(path).astype(np.int32)
    _check_shape(arr, shape, "Cellpose", roi_name)
    return arr


def _rasterise(
    nuclei: list,
    source: str,
    shape: tuple[int, int],
    origin: tuple[int, int] = (0, 0),
) -> np.ndarray:
    """Rasterise polygon contours from XML nucleus elements for one source.

    Coordinates in the XML are absolute (original slide space).
    origin=(x1, y1) is subtracted to convert to tile-local coordinates.
    """
    mask = np.zeros(shape, dtype=np.int32)
    ox, oy = origin  # ox = col offset, oy = row offset
    instance_id = 1
    for nucleus in nuclei:
        if nucleus.attrib.get("source") != source:
            continue
        points = nucleus.findall("point")
        if len(points) < 3:
            continue
        # XML convention: x = column, y = row; subtract tile origin
        cols = np.array([int(p.attrib["x"]) - ox for p in points])
        rows = np.array([int(p.attrib["y"]) - oy for p in points])
        rr, cc = sk_polygon(rows, cols, shape=shape)
        mask[rr, cc] = instance_id
        instance_id += 1
    return mask


def _check_shape(arr: np.ndarray, expected: tuple[int, int], name: str, roi: str) -> None:
    if arr.shape != expected:
        raise ValueError(
            f"{name} array for {roi} has shape {arr.shape}, expected {expected}"
        )
