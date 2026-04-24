"""
Pure I/O module for reading and writing tile descriptor XML files.

No PyQt or PIL dependency—stdlib only.  The XML schema describes one
extracted slice: its source image, grid settings, bounding rects, optional
brush polygon, and the pixel-level removal mask produced by the Pixel Editor.

Schema
------
::

    <tile version="1">
      <source abs_path="…" rel_path="…"
              width="…"    height="…"/>
      <grid   w="…" h="…" color="…"/>
      <slice  name="…" description="…" microns_per_pixel="…" type="grid|brush">
        <bounds  x1="…" y1="…" x2="…" y2="…"/>
        <rects>
          <rect x1="…" y1="…" x2="…" y2="…"/>
        </rects>
        <!-- only present for brush slices -->
        <polygon>
          <point x="…" y="…"/>
        </polygon>
        <pixel_mask>
          <pixel x="…" y="…"/>
        </pixel_mask>
      </slice>
    </tile>
"""

import logging
import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Set, Tuple

from app.domain.geometry import get_polygon_bounding_box, is_rect_overlapping

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = "1"


# ──────────────────────────────────────────────────────────────────────────────
# Write
# ──────────────────────────────────────────────────────────────────────────────

def write_tile_xml(path: str, descriptor: dict) -> None:
    """Serialize a tile descriptor dict to *path* as XML.

    Args:
        path: Destination file path (e.g. ``output/img_slice1_tile.xml``).
        descriptor: Dictionary produced by :func:`build_tile_descriptor`.

    Raises:
        OSError: If the file cannot be written.
    """
    root = ET.Element("tile", version=_SCHEMA_VERSION)

    # <source>
    src = descriptor.get("source", {})
    ET.SubElement(root, "source",
                  abs_path=str(src.get("abs_path", "")),
                  rel_path=str(src.get("rel_path", "")),
                  width=str(src.get("width", 0)),
                  height=str(src.get("height", 0)))

    # <grid>
    grid = descriptor.get("grid", {})
    ET.SubElement(root, "grid",
                  w=str(grid.get("w", 1000)),
                  h=str(grid.get("h", 1000)),
                  color=str(grid.get("color", "#FFFF00")))

    # <slice>
    sl = descriptor.get("slice", {})
    slice_type = "brush" if sl.get("polygon") else "grid"
    slice_el = ET.SubElement(root, "slice",
                              name=str(sl.get("name", "")),
                              description=str(sl.get("description", "")),
                              microns_per_pixel=str(sl.get("microns_per_pixel", "")),
                              type=slice_type)

    # <bounds>
    bounds = sl.get("bounds", {})
    ET.SubElement(slice_el, "bounds",
                  x1=str(bounds.get("x1", 0)),
                  y1=str(bounds.get("y1", 0)),
                  x2=str(bounds.get("x2", 0)),
                  y2=str(bounds.get("y2", 0)))

    # <rects> (underlying grid cells — kept for reference, rendering uses polygon)
    rects_el = ET.SubElement(slice_el, "rects")
    for (rx1, ry1, rx2, ry2) in sl.get("rects", []):
        ET.SubElement(rects_el, "rect",
                      x1=str(rx1), y1=str(ry1),
                      x2=str(rx2), y2=str(ry2))

    # <polygon> — only for brush slices; this is the authoritative shape
    polygon = sl.get("polygon")
    if polygon:
        poly_el = ET.SubElement(slice_el, "polygon")
        for (px, py) in polygon:
            ET.SubElement(poly_el, "point", x=str(px), y=str(py))

    # <pixel_mask>
    mask_el = ET.SubElement(slice_el, "pixel_mask")
    for (px, py) in sl.get("pixel_mask", []):
        ET.SubElement(mask_el, "pixel", x=str(px), y=str(py))

    # <segmentations>
    segmentations = sl.get("segmentations", [])
    if segmentations:
        segs_el = ET.SubElement(slice_el, "segmentations")
        for i, seg in enumerate(segmentations):
            poly = seg.get("polygon", seg) if isinstance(seg, dict) else seg
            model = seg.get("model", "Imported") if isinstance(seg, dict) else "Imported"
            nuc_el = ET.SubElement(segs_el, "nucleus", id=str(i), source=model)
            for (px, py) in poly:
                ET.SubElement(nuc_el, "point", x=str(px), y=str(py))

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    try:
        tree.write(path, encoding="utf-8", xml_declaration=True)
        logger.info("Tile XML written: %s", path)
    except OSError as exc:
        logger.error("Failed to write tile XML '%s': %s", path, exc)
        raise


def build_tile_descriptor(
    session,
    slice_idx: int,
    output_dir: str,
) -> dict:
    """Build a tile descriptor dict from a session's slice data.

    Args:
        session: :class:`~app.domain.session.ImageSession` instance.
        slice_idx: Index of the slice to describe.
        output_dir: Directory where the accompanying image will be saved
            (used to compute a relative path back to the source image).

    Returns:
        dict ready to be passed to :func:`write_tile_xml`.
    """
    tile = session.tiles[slice_idx]
    slice_rects = tile.rects
    polygon = tile.polygon

    # For brush slices, compute bounds from the actual polygon, not the grid rects
    if polygon and len(polygon) >= 3:
        bx1 = int(min(p[0] for p in polygon))
        by1 = int(min(p[1] for p in polygon))
        bx2 = int(max(p[0] for p in polygon))
        by2 = int(max(p[1] for p in polygon))
    else:
        bx1 = min(r[0] for r in slice_rects)
        by1 = min(r[1] for r in slice_rects)
        bx2 = max(r[2] for r in slice_rects)
        by2 = max(r[3] for r in slice_rects)

    meta: Dict[str, str] = tile.metadata
    pixel_mask: Set[Tuple[int, int]] = tile.pixel_mask

    abs_src = os.path.abspath(session.path)
    try:
        rel_src = os.path.relpath(abs_src, output_dir)
    except ValueError:
        rel_src = abs_src  # cross-drive on Windows

    # Flatten segmentation layers into individual segmentation dicts for XML compat
    segmentations = []
    for layer in tile.segmentation_layers:
        model = layer.get("model", "Imported")
        for poly in layer.get("polygons", []):
            segmentations.append({"polygon": list(poly), "model": model})

    return {
        "source": {
            "abs_path": abs_src,
            "rel_path": rel_src,
            "width": session.real_width,
            "height": session.real_height,
        },
        "grid": {
            "w": session.grid_w,
            "h": session.grid_h,
            "color": session.grid_color,
        },
        "slice": {
            "name": meta.get("name", ""),
            "description": meta.get("description", ""),
            "microns_per_pixel": meta.get("microns_per_pixel", ""),
            "bounds": {"x1": bx1, "y1": by1, "x2": bx2, "y2": by2},
            "rects": sorted(slice_rects),
            "polygon": list(polygon) if polygon and len(polygon) >= 3 else None,
            "pixel_mask": sorted(pixel_mask),
            "segmentations": segmentations,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Read
# ──────────────────────────────────────────────────────────────────────────────

def read_tile_xml(path: str) -> dict:
    """Parse a tile descriptor XML file and return a descriptor dict.

    The dict has the same shape as the one produced by
    :func:`build_tile_descriptor`, with native Python types (int, str, etc.).

    Args:
        path: Path to the ``*_tile.xml`` file.

    Returns:
        Descriptor dict.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the XML is malformed or uses an unsupported version.
    """
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as exc:
        logger.error("Cannot parse tile XML '%s': %s", path, exc)
        raise

    root = tree.getroot()
    version = root.get("version", "1")
    if version != _SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported tile XML version '{version}' "
            f"(expected '{_SCHEMA_VERSION}')"
        )

    # <source>
    src_el = root.find("source")
    source: dict = {}
    if src_el is not None:
        source = {
            "abs_path": src_el.get("abs_path", ""),
            "rel_path": src_el.get("rel_path", ""),
            "width": int(src_el.get("width", 0)),
            "height": int(src_el.get("height", 0)),
        }

    # <grid>
    grid_el = root.find("grid")
    grid: dict = {"w": 1000, "h": 1000, "color": "#FFFF00"}
    if grid_el is not None:
        grid = {
            "w": int(grid_el.get("w", 1000)),
            "h": int(grid_el.get("h", 1000)),
            "color": grid_el.get("color", "#FFFF00"),
        }

    # <slice>
    sl_el = root.find("slice")
    slice_data: dict = {
        "name": "", "description": "", "microns_per_pixel": "",
        "bounds": {}, "rects": [], "pixel_mask": [],
    }
    if sl_el is not None:
        slice_data["name"] = sl_el.get("name", "")
        slice_data["description"] = sl_el.get("description", "")
        slice_data["microns_per_pixel"] = sl_el.get("microns_per_pixel", "")

        bounds_el = sl_el.find("bounds")
        if bounds_el is not None:
            slice_data["bounds"] = {
                "x1": int(bounds_el.get("x1", 0)),
                "y1": int(bounds_el.get("y1", 0)),
                "x2": int(bounds_el.get("x2", 0)),
                "y2": int(bounds_el.get("y2", 0)),
            }

        rects_el = sl_el.find("rects")
        rects: List[Tuple[int, int, int, int]] = []
        if rects_el is not None:
            for r in rects_el.findall("rect"):
                rects.append((
                    int(r.get("x1", 0)), int(r.get("y1", 0)),
                    int(r.get("x2", 0)), int(r.get("y2", 0)),
                ))
        slice_data["rects"] = rects

        # <polygon> — list of (x, y) float tuples; None if this is a grid slice
        poly_el = sl_el.find("polygon")
        polygon: List[Tuple[float, float]] = []
        if poly_el is not None:
            for pt in poly_el.findall("point"):
                polygon.append((float(pt.get("x", 0)), float(pt.get("y", 0))))
        slice_data["polygon"] = polygon if polygon else None

        mask_el = sl_el.find("pixel_mask")
        mask: List[Tuple[int, int]] = []
        if mask_el is not None:
            for p in mask_el.findall("pixel"):
                mask.append((int(p.get("x", 0)), int(p.get("y", 0))))
        slice_data["pixel_mask"] = mask

        segs_el = sl_el.find("segmentations")
        segmentations: List[dict] = []
        if segs_el is not None:
            for nuc_el in segs_el.findall("nucleus"):
                model = nuc_el.get("source", "Imported")
                poly = []
                for pt in nuc_el.findall("point"):
                    poly.append((float(pt.get("x", 0)), float(pt.get("y", 0))))
                if poly:
                    segmentations.append({"polygon": poly, "model": model})
        slice_data["segmentations"] = segmentations

    return {"source": source, "grid": grid, "slice": slice_data}
