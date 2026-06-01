import logging
import math
import os

from app.domain.session import ImageSession
from app.infrastructure.tile_xml import read_tile_xml
from app.infrastructure.tile_geojson import read_geojson_features

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

        # ── Append Tile to session, or merge into an existing matching tile ──
        from app.domain.tile import Tile
        metadata = {
            "name": sl.get("name", ""),
            "description": sl.get("description", ""),
            "microns_per_pixel": sl.get("microns_per_pixel", ""),
        }
        pixel_mask = {(p[0], p[1]) for p in sl.get("pixel_mask", [])}

        match_idx = self._find_matching_tile(session, list(rects), metadata, polygon)
        if match_idx is not None:
            tile = session.tiles[match_idx]
            tile.pixel_mask.update(pixel_mask)
            if polygon and not getattr(tile, "polygon", None):
                tile.polygon = polygon
            new_idx = match_idx
            logger.info("Tile XML matched existing slice idx %d; merging layers.", new_idx)
        else:
            tile = Tile(rects=list(rects))
            tile.metadata = metadata
            tile.pixel_mask = pixel_mask
            tile.polygon = polygon
            session.tiles.append(tile)
            new_idx = len(session.tiles) - 1

        # ── Re-base imported polygons onto the matched tile's coordinate frame ──
        # A descriptor stores its polygons relative to its own <bounds> origin.
        # When they merge into a tile placed at a DIFFERENT position — e.g. slices
        # laid out across a WSI canvas via "Import Slice Images Folder", where each
        # tile origin is its placement (x, y) — the polygons must be shifted by the
        # difference so they land on the nuclei instead of at the canvas origin.
        src_bounds = sl.get("bounds") or {}
        if src_bounds:
            sx1, sy1 = int(src_bounds.get("x1", 0)), int(src_bounds.get("y1", 0))
        elif rects:
            sx1 = min(r[0] for r in rects)
            sy1 = min(r[1] for r in rects)
        else:
            sx1 = sy1 = 0
        tx1, ty1, _, _ = tile.bounding_box
        dx, dy = tx1 - sx1, ty1 - sy1

        # Restore segmentations as layers on the tile
        segmentations = sl.get("segmentations", [])
        if segmentations:
            from collections import defaultdict
            grouped = defaultdict(list)
            for seg in segmentations:
                poly = seg.get("polygon", seg) if isinstance(seg, dict) else seg
                raw_model = seg.get("model", "Imported") if isinstance(seg, dict) else "Imported"
                model = self._normalize_segmentation_source(raw_model)
                int_poly = [(int(pt[0]) + dx, int(pt[1]) + dy) for pt in poly]
                grouped[model].append(int_poly)
            from app.domain.tile import LAYER_COLORS
            for i, (model, polys) in enumerate(grouped.items()):
                color = LAYER_COLORS[i % len(LAYER_COLORS)]
                self._add_or_extend_layer(tile, model, polys, color)

        logger.info(
            "Tile XML imported: type=%s, rect=%s, polygon=%s, %d removed pixels, %d nuclei → slice idx %d",
            slice_type,
            list(rects),
            f"{len(raw_polygon)} pts" if raw_polygon else "none",
            len(tile.pixel_mask),
            len(segmentations),
            new_idx,
        )
        return new_idx

    def _normalize_segmentation_source(self, source: str) -> str:
        text = (source or "").strip()
        key = text.lower().replace("_", "-").strip()
        gt_aliases = {
            "gt",
            "gt-pathology",
            "gt pathology",
            "gt-pathologist",
            "gt pathologist",
            "gt (pathologist)",
            "ground truth",
            "ground-truth",
            "groundtruth",
            "pathologist",
            "pathology",
        }
        return "gt-pathology" if key in gt_aliases else (text or "Imported")

    def _find_matching_tile(self, session: ImageSession, rects: list, metadata: dict, polygon):
        target_name = (metadata.get("name") or "").strip()
        target_rects = {tuple(r) for r in rects}
        target_bbox = self._rects_bbox(target_rects)

        # Name is authoritative. A descriptor that carries a slice name only ever
        # matches the slice with that exact name — never the rects/bbox fallback.
        # Without this, several same-size tiles (e.g. equal-dimension ROIs all at
        # origin 0,0) collide on rects/bbox and every import merges into the first
        # tile instead of its own named slice.
        if target_name:
            for idx, tile in enumerate(session.tiles):
                if (tile.metadata.get("name") or "").strip() == target_name:
                    return idx
            return None

        # Unnamed descriptor: fall back to geometry matching.
        for idx, tile in enumerate(session.tiles):
            tile_rects = {tuple(r) for r in getattr(tile, "rects", [])}
            if target_rects and tile_rects == target_rects:
                return idx
            if target_bbox and getattr(tile, "bounding_box", None) == target_bbox:
                return idx
        return None

    def _rects_bbox(self, rects: set[tuple[int, int, int, int]]):
        if not rects:
            return None
        return (
            min(r[0] for r in rects),
            min(r[1] for r in rects),
            max(r[2] for r in rects),
            max(r[3] for r in rects),
        )

    def _add_or_extend_layer(self, tile, model: str, polys: list, color: str) -> None:
        for layer in tile.segmentation_layers:
            layer_model = self._normalize_segmentation_source(
                layer.get("model_name") or layer.get("model") or layer.get("name") or ""
            )
            layer_name = self._normalize_segmentation_source(layer.get("name") or "")
            if layer_model == model or layer_name == model:
                existing = {
                    tuple((int(x), int(y)) for x, y in poly)
                    for poly in layer.setdefault("polygons", [])
                }
                for poly in polys:
                    key = tuple((int(x), int(y)) for x, y in poly)
                    if key not in existing:
                        layer["polygons"].append(poly)
                        existing.add(key)
                layer["model"] = model
                layer["model_name"] = model
                layer["name"] = model
                return
        tile.add_layer(model, model, polys, color)

    def load_geojson(self, path: str, session: ImageSession) -> list[int]:
        """Parse a GeoJSON annotation file.  Each annotated region becomes
        its own independent Slice/Tile in *session*.

        Args:
            path: Path to a ``.geojson`` annotation file.
            session: The :class:`ImageSession` to extend.

        Returns:
            List of indices of the newly appended tiles.

        Raises:
            OSError: If the file cannot be read.
            ValueError: If the GeoJSON is malformed or empty.
        """
        descriptors = read_geojson_features(path)
        from app.domain.tile import Tile

        new_indices: list[int] = []

        for descriptor in descriptors:
            sl = descriptor.get("slice", {})

            # ── Polygon (authoritative clipping boundary) ─────────────
            raw_polygon = sl.get("polygon")
            polygon = (
                [tuple(pt) for pt in raw_polygon]
                if raw_polygon and len(raw_polygon) >= 3
                else None
            )

            # ── Bounding rect from the polygon ────────────────────────
            if polygon:
                bx1 = int(min(p[0] for p in polygon))
                by1 = int(min(p[1] for p in polygon))
                bx2 = int(math.ceil(max(p[0] for p in polygon)))
                by2 = int(math.ceil(max(p[1] for p in polygon)))
                rects = [(bx1, by1, bx2, by2)]
            else:
                raw_rects = sl.get("rects", [])
                if not raw_rects:
                    b = sl.get("bounds", {})
                    raw_rects = [(b.get("x1", 0), b.get("y1", 0),
                                  b.get("x2", 0), b.get("y2", 0))]
                rects = [tuple(r) for r in raw_rects]

            # ── Build Tile ────────────────────────────────────────────
            tile = Tile(rects=rects, polygon=polygon)
            tile.metadata = {
                "name": sl.get("name", ""),
                "description": sl.get("description", ""),
                "microns_per_pixel": sl.get("microns_per_pixel", ""),
            }

            session.tiles.append(tile)
            new_indices.append(len(session.tiles) - 1)

        logger.info(
            "GeoJSON imported: %d slices from '%s'",
            len(new_indices),
            path,
        )
        return new_indices

    def load_json(self, path: str, session: ImageSession) -> list[int]:
        """Parse a custom JSON annotation file.  Each annotated region becomes
        its own independent Slice/Tile in *session*.

        Args:
            path: Path to a ``.json`` annotation file.
            session: The :class:`ImageSession` to extend.

        Returns:
            List of indices of the newly appended tiles.

        Raises:
            OSError: If the file cannot be read.
            ValueError: If the JSON is malformed or empty.
        """
        from app.infrastructure.tile_json import read_json_features
        descriptors = read_json_features(path)
        from app.domain.tile import Tile

        new_indices: list[int] = []

        for descriptor in descriptors:
            sl = descriptor.get("slice", {})

            # ── Polygon (authoritative clipping boundary) ─────────────
            raw_polygon = sl.get("polygon")
            polygon = (
                [tuple(pt) for pt in raw_polygon]
                if raw_polygon and len(raw_polygon) >= 3
                else None
            )

            # ── Bounding rect from the polygon ────────────────────────
            if polygon:
                bx1 = int(min(p[0] for p in polygon))
                by1 = int(min(p[1] for p in polygon))
                bx2 = int(math.ceil(max(p[0] for p in polygon)))
                by2 = int(math.ceil(max(p[1] for p in polygon)))
                rects = [(bx1, by1, bx2, by2)]
            else:
                raw_rects = sl.get("rects", [])
                if not raw_rects:
                    b = sl.get("bounds", {})
                    raw_rects = [(b.get("x1", 0), b.get("y1", 0),
                                  b.get("x2", 0), b.get("y2", 0))]
                rects = [tuple(r) for r in raw_rects]

            # ── Build Tile ────────────────────────────────────────────
            tile = Tile(rects=rects, polygon=polygon)
            tile.metadata = {
                "name": sl.get("name", ""),
                "description": sl.get("description", ""),
                "microns_per_pixel": sl.get("microns_per_pixel", ""),
            }

            session.tiles.append(tile)
            new_indices.append(len(session.tiles) - 1)

        logger.info(
            "JSON imported: %d slices from '%s'",
            len(new_indices),
            path,
        )
        return new_indices
