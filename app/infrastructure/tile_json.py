"""
Pure I/O module for reading JSON annotation files.

The expected JSON schema is:
{
    "children": [
        {
            "meta": {
                "short_text": "INV",  // annotation class label
                "_points": [
                    {"x": 100, "y": 200},
                    ...
                ]
            }
        },
        ...
    ]
}

This module converts each JSON child into its own descriptor dict
(same shape as `read_tile_xml` and `read_geojson_features`).
"""

import json
import logging
import math
from typing import List, Tuple

logger = logging.getLogger(__name__)


def read_json_features(path: str) -> List[dict]:
    """Parse a custom JSON annotation file and return one descriptor per region.

    Args:
        path: Path to a ``.json`` file.

    Returns:
        List of descriptor dicts, one per valid child.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the JSON is malformed or has no children.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Cannot parse JSON '%s': %s", path, exc)
        raise

    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object at the root.")

    children = data.get("children", [])
    if not children:
        raise ValueError("JSON contains no 'children' array.")

    descriptors: List[dict] = []

    for child in children:
        meta = child.get("meta", {})
        points = meta.get("_points", [])
        
        desc = _build_descriptor_from_points(points, meta)
        if desc:
            descriptors.append(desc)

    if not descriptors:
        raise ValueError("No valid features found in JSON.")

    logger.info(
        "JSON parsed: %d features → %d slice descriptors from '%s'",
        len(children),
        len(descriptors),
        path,
    )
    return descriptors


def _build_descriptor_from_points(points: list, meta: dict) -> dict | None:
    """Build a single tile-descriptor dict from a list of points.

    Args:
        points: list of dicts with 'x' and 'y' keys.
        meta: The enclosing meta dict (for properties/id).

    Returns:
        Descriptor dict, or ``None`` if the polygon is degenerate.
    """
    if not points or len(points) < 3:
        return None

    # Convert [{"x": X, "y": Y}, …] → [(X, Y), …]
    try:
        polygon: List[Tuple[float, float]] = [
            (float(pt["x"]), float(pt["y"])) for pt in points
        ]
    except (KeyError, ValueError, TypeError):
        return None

    # Tight bounding box from this polygon only
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    bx1 = int(min(xs))
    by1 = int(min(ys))
    bx2 = int(math.ceil(max(xs)))
    by2 = int(math.ceil(max(ys)))

    # Class label / name
    class_name = meta.get("short_text", "") or "Unknown"
    feat_id = meta.get("id", "") or meta.get("annotation_id", "")

    return {
        "source": {},
        "grid": {"w": 1000, "h": 1000, "color": "#FFFF00"},
        "slice": {
            "name": class_name,
            "description": f"JSON annotation '{class_name}' ({feat_id})",
            "microns_per_pixel": "",
            "type": "brush",          # brush → polygon mask clipping
            "bounds": {"x1": bx1, "y1": by1, "x2": bx2, "y2": by2},
            "rects": [(bx1, by1, bx2, by2)],
            "polygon": polygon,       # authoritative clipping boundary
            "pixel_mask": [],
            "segmentations": [],
        },
    }
