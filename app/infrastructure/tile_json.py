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

    _label_unlabeled_regions_inside_roi(descriptors)

    if not descriptors:
        raise ValueError("No valid features found in JSON.")

    logger.info(
        "JSON parsed: %d features → %d slice descriptors from '%s'",
        len(children),
        len(descriptors),
        path,
    )
    return descriptors


def _label_unlabeled_regions_inside_roi(descriptors: List[dict]) -> None:
    """Name unlabeled regions enclosed by JSON ROI container annotations.

    A JSON annotation named "ROI" acts as a spatial container. Any unlabeled
    annotation whose centroid falls inside that ROI receives the contextual
    INV_C label for the ROI index.
    """
    roi_polygons = []
    for desc in descriptors:
        sl = desc.get("slice", {})
        name = sl.get("name", "").strip()
        polygon = sl.get("polygon")
        if name.lower() == "roi" and polygon:
            roi_polygons.append(polygon)

    if not roi_polygons:
        return

    roi_polygons.sort(key=lambda polygon: _polygon_centroid(polygon))
    renamed = 0

    for desc in descriptors:
        sl = desc.get("slice", {})
        name = sl.get("name", "").strip()
        polygon = sl.get("polygon")
        if name and name.lower() != "unknown":
            continue
        if not polygon:
            continue

        cx, cy = _polygon_centroid(polygon)
        for roi_idx, roi_polygon in enumerate(roi_polygons, 1):
            if _is_point_in_polygon(cx, cy, roi_polygon):
                label = f"INV_C{roi_idx}"
                sl["name"] = label
                feat_id = _description_feature_id(sl.get("description", ""))
                sl["description"] = f"JSON annotation '{label}'{feat_id}"
                renamed += 1
                break

    if renamed:
        logger.info(
            "JSON ROI context labels applied: %d unlabeled feature(s) renamed across %d ROI container(s).",
            renamed,
            len(roi_polygons),
        )


def _description_feature_id(description: str) -> str:
    start = description.rfind(" (")
    if start < 0 or not description.endswith(")"):
        return ""
    return description[start:]


def _polygon_centroid(polygon: List[Tuple[float, float]]) -> Tuple[float, float]:
    if not polygon:
        return (0.0, 0.0)
    x_sum = sum(pt[0] for pt in polygon)
    y_sum = sum(pt[1] for pt in polygon)
    return (x_sum / len(polygon), y_sum / len(polygon))


def _is_point_in_polygon(x: float, y: float, polygon: List[Tuple[float, float]]) -> bool:
    if not polygon or len(polygon) < 3:
        return False

    inside = False
    p1x, p1y = polygon[0]
    for i in range(len(polygon) + 1):
        p2x, p2y = polygon[i % len(polygon)]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        x_intersection = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= x_intersection:
                        inside = not inside
        p1x, p1y = p2x, p2y

    return inside


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

    # Class label / name — keep empty string as-is; "Unknown" was misleading
    class_name = meta.get("short_text", "").strip()
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
