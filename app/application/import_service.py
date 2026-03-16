import logging
import math
import os

from app.domain.session import ImageSession
from app.infrastructure.tile_xml import read_tile_xml

logger = logging.getLogger(__name__)

class TileImportService:
    """Application-layer service for restoring a saved tile descriptor into a session.

    Reads the XML produced by :class:`ExportService` and rehydrates the
    corresponding slice (rects, metadata, pixel mask) into the active
    :class:`~app.domain.session.ImageSession`.
    """

    def load_tile_xml(self, path: str, session: ImageSession) -> int:
        """Parse *path*, append the described slice to *session*, and return
        the new slice index.

        Args:
            path: Path to a ``*_tile.xml`` descriptor file.
            session: The :class:`ImageSession` to extend.

        Returns:
            Index of the newly appended slice in ``session.selected_cells``.

        Raises:
            OSError: If the XML file cannot be read.
            ValueError: If the XML is malformed or has an unsupported version.
        """
        descriptor = read_tile_xml(path)
        sl = descriptor.get("slice", {})
        slice_type = sl.get("type", "grid")   # "brush" or "grid"

        # ── Restore polygon first (needed to compute brush bounding box) ──
        raw_polygon = sl.get("polygon")  # list of (x,y) floats, or None
        polygon = (
            [tuple(pt) for pt in raw_polygon]
            if raw_polygon and len(raw_polygon) >= 3
            else None
        )

        # ── Resolve the bounding rect for selected_cells ──────────────────
        # DESIGN: For brush slices the authoritative area is the polygon's
        # tight bounding box (N/S/E/W extremes), NOT the grid cells.
        # Grid cells can be 1000x1000px cells that happen to intersect the
        # polygon — storing them as selected_cells caused the preview to show
        # a region 10-100x larger than what was actually drawn by the user.
        # For grid slices the original grid-cell rect set is kept unchanged.
        if slice_type == "brush" and polygon:
            bx1 = int(min(p[0] for p in polygon))
            by1 = int(min(p[1] for p in polygon))
            bx2 = int(math.ceil(max(p[0] for p in polygon)))
            by2 = int(math.ceil(max(p[1] for p in polygon)))
            rects = {(bx1, by1, bx2, by2)}
        else:
            # Grid slice: use the stored rects (or fall back to <bounds>)
            raw_rects = sl.get("rects", [])
            if not raw_rects:
                b = sl.get("bounds", {})
                raw_rects = [(b.get("x1", 0), b.get("y1", 0),
                              b.get("x2", 0), b.get("y2", 0))]
            rects = {tuple(r) for r in raw_rects}

        # ── Source image path validation (warn-only, don't block import) ──
        src = descriptor.get("source", {})
        xml_dir = os.path.dirname(os.path.abspath(path))
        candidate_abs = src.get("abs_path", "")
        candidate_rel = os.path.normpath(
            os.path.join(xml_dir, src.get("rel_path", ""))
        )
        if not os.path.exists(candidate_abs) and not os.path.exists(candidate_rel):
            logger.warning(
                "Tile XML source image not found — "
                "abs='%s' rel='%s'. Importing anyway.",
                candidate_abs, candidate_rel,
            )

        # ── Append slice to session ──
        session.selected_cells.append(rects)
        session.sync_metadata()

        new_idx = len(session.selected_cells) - 1

        # ── Restore metadata ──
        session.slice_metadata[new_idx] = {
            "name": sl.get("name", ""),
            "description": sl.get("description", ""),
            "microns_per_pixel": sl.get("microns_per_pixel", ""),
        }

        # ── Restore pixel mask ──
        pixel_mask = {(p[0], p[1]) for p in sl.get("pixel_mask", [])}
        if hasattr(session, "pixel_masks"):
            session.pixel_masks[new_idx] = pixel_mask

        # ── Restore polygon ──
        if hasattr(session, "selected_polygons"):
            session.selected_polygons[new_idx] = polygon

        logger.info(
            "Tile XML imported: type=%s, rect=%s, polygon=%s, %d removed pixels → slice idx %d",
            slice_type,
            list(rects),
            f"{len(raw_polygon)} pts" if raw_polygon else "none",
            len(pixel_mask),
            new_idx,
        )
        return new_idx
