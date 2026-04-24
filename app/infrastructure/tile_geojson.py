"""
Pure I/O module for reading GeoJSON annotation files exported by third-party
medical slide software (e.g. QuPath, ASAP, SlideRunner).

No PyQt or PIL dependency—stdlib + json only.

The expected GeoJSON schema is a **FeatureCollection** whose Features each
describe an annotated region on the whole-slide image:

::

    {
      "type": "FeatureCollection",
      "features": [
        {
          "type": "Feature",
          "id": "...",
          "geometry": {
            "type": "Polygon",
            "coordinates": [[[x, y], [x, y], ...]]
          },
          "properties": {
            "objectType": "annotation",
            "name": "IS"            // annotation class label
          }
        },
        ...
      ]
    }

Each feature's polygon coordinates are in *pixel space* of the source
whole-slide image (integer or float).

This module converts each GeoJSON Feature into its own descriptor dict
(same shape as :func:`~app.infrastructure.tile_xml.read_tile_xml`),
so each annotated region becomes an independent Slice/Tile in the
application.
"""

import json
import logging
import math
from typing import List, Tuple

logger = logging.getLogger(__name__)


def read_geojson_features(path: str) -> List[dict]:
    """Parse a GeoJSON annotation file and return one descriptor per Feature.

    Each returned descriptor mirrors the shape of
    :func:`~app.infrastructure.tile_xml.read_tile_xml` so the import
    pipeline can consume them directly.  The polygon from each Feature
    is stored as the tile's ``polygon`` (brush-style clipping boundary),
    and the bounding box is computed from that specific polygon only—
    keeping each Slice lightweight.

    Args:
        path: Path to a ``.geojson`` file.

    Returns:
        List of descriptor dicts, one per valid Feature.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the JSON is malformed or has no features.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Cannot parse GeoJSON '%s': %s", path, exc)
        raise

    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError(
            f"Expected a GeoJSON FeatureCollection, got type='{data.get('type')}'"
        )

    features = data.get("features", [])
    if not features:
        raise ValueError("GeoJSON FeatureCollection contains no features.")

    descriptors: List[dict] = []

    for feat in features:
        geom = feat.get("geometry", {})
        geom_type = geom.get("type", "")

        if geom_type == "Polygon":
            rings = geom.get("coordinates", [])
            desc = _build_descriptor_from_rings(rings, feat)
            if desc:
                descriptors.append(desc)
        elif geom_type == "MultiPolygon":
            # Each sub-polygon becomes its own Slice
            for rings in geom.get("coordinates", []):
                desc = _build_descriptor_from_rings(rings, feat)
                if desc:
                    descriptors.append(desc)
        else:
            logger.debug(
                "Skipping feature with unsupported geometry type '%s'",
                geom_type,
            )

    if not descriptors:
        raise ValueError("No valid Polygon features found in GeoJSON.")

    logger.info(
        "GeoJSON parsed: %d features → %d slice descriptors from '%s'",
        len(features),
        len(descriptors),
        path,
    )
    return descriptors


def _build_descriptor_from_rings(rings: list, feature: dict) -> dict | None:
    """Build a single tile-descriptor dict from one Polygon's coordinate rings.

    Only the *outer ring* (index 0) is used; inner rings (holes) are
    ignored.

    Args:
        rings: ``coordinates`` array from a Polygon geometry
               (list of rings, each ring is a list of [x, y] pairs).
        feature: The enclosing GeoJSON Feature dict (for properties/id).

    Returns:
        Descriptor dict, or ``None`` if the polygon is degenerate.
    """
    if not rings:
        return None

    outer_ring = rings[0]
    if len(outer_ring) < 3:
        return None

    # Convert [[x, y], …] → [(x, y), …]
    polygon: List[Tuple[float, float]] = [
        (float(pt[0]), float(pt[1])) for pt in outer_ring
    ]

    # Tight bounding box from this polygon only
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    bx1 = int(min(xs))
    by1 = int(min(ys))
    bx2 = int(math.ceil(max(xs)))
    by2 = int(math.ceil(max(ys)))

    # Class label / name
    props = feature.get("properties", {})
    class_name = (
        props.get("name")
        or props.get("classification", {}).get("name", "")
        or "Unknown"
    )
    feat_id = feature.get("id", "")

    return {
        "source": {},
        "grid": {"w": 1000, "h": 1000, "color": "#FFFF00"},
        "slice": {
            "name": class_name,
            "description": f"GeoJSON annotation '{class_name}' ({feat_id})",
            "microns_per_pixel": "",
            "type": "brush",          # brush → polygon mask clipping
            "bounds": {"x1": bx1, "y1": by1, "x2": bx2, "y2": by2},
            "rects": [(bx1, by1, bx2, by2)],
            "polygon": polygon,       # authoritative clipping boundary
            "pixel_mask": [],
            "segmentations": [],
        },
    }
