import logging
import os
from app.domain.session import ImageSession
from app.infrastructure.exceptions import ProjectIOError
from app.infrastructure.io import load_project_file, save_project_file

logger = logging.getLogger(__name__)

class ProjectService:
    def load_project(self, path):
        """Loads a project and returns a list of ImageSession objects.

        Returns (sessions, missing_items) where missing_items is a list of
        dicts with 'rel_path', 'abs_path', and 'item' for images that were
        not found.

        Raises:
            ProjectIOError: propagated from the I/O layer on read failure.
        """
        logger.debug("Loading project from service layer: %s", path)
        data = load_project_file(path)  # raises ProjectIOError on failure
        project_dir = os.path.dirname(os.path.abspath(path))
        sessions = []
        missing = []
        for item in data:
            if "path" not in item:
                continue

            # Resolve image path: try relative first, then abs_path fallback
            rel_path = item["path"]
            abs_path = item.get("abs_path", "")
            resolved = os.path.normpath(os.path.join(project_dir, rel_path))

            if os.path.exists(resolved):
                img_path = resolved
            elif abs_path and os.path.exists(abs_path):
                img_path = abs_path
            else:
                # Image not found — collect for re-link dialog
                missing.append({"rel_path": rel_path, "abs_path": abs_path, "item": item})
                continue

            s = ImageSession(img_path)
            s.grid_w = item.get("grid_w", 1000)
            s.grid_h = item.get("grid_h", 1000)
            s.zoom_level = item.get("zoom_level", 1.0)
            s.camera_x = item.get("camera_x", 0)
            s.camera_y = item.get("camera_y", 0)
            s.camera_y = item.get("camera_y", 0)
            
            # Legacy session-level segmentations → migrate to tiles
            legacy_segs = []
            if "segmentations" in item:
                for s_poly in item["segmentations"]:
                    if isinstance(s_poly, dict):
                        legacy_segs.append(s_poly)
                    elif isinstance(s_poly, list):
                        legacy_segs.append({"polygon": [tuple(pt) for pt in s_poly], "model": "Imported", "visible": True})

            # --- Schema Migration: Old Parallel Arrays -> unified Tile objects ---
            from app.domain.tile import Tile
            s.tiles = []
            
            if "tiles" in item:
                s.tiles = [Tile.deserialize(t_data) for t_data in item["tiles"]]
            else:
                # Old schema loader
                sel = item.get("selected_regions", item.get("selected_cells", []))
                rects_list = []
                if sel and isinstance(sel[0], (list, tuple)):
                    if sel[0] and isinstance(sel[0][0], (list, tuple)):
                        rects_list = [[tuple(r) for r in group] for group in sel]
                    else:
                        rects_list = [[tuple(r)] for r in sel if len(r) == 4]
                
                raw_polys = item.get("selected_polygons", [])
                slice_metadata = item.get("slice_metadata", [])
                raw_excls = item.get("slice_exclusions", [])
                saved_colors = item.get("tile_colors", [])
                raw_masks = item.get("pixel_masks", [])
                
                for i, rects in enumerate(rects_list):
                    t = Tile(rects=rects)
                    if i < len(raw_polys) and raw_polys[i]:
                        t.polygon = [tuple(pt) for pt in raw_polys[i]]
                    if i < len(slice_metadata):
                        t.metadata = slice_metadata[i]
                    if i < len(raw_excls) and raw_excls[i]:
                        t.exclusions = [tuple(r) for r in raw_excls[i]]
                    if i < len(saved_colors):
                        t.color = saved_colors[i]
                    if i < len(raw_masks) and raw_masks[i]:
                        t.pixel_mask = {tuple(p) for p in raw_masks[i]}
                    s.tiles.append(t)

            # Migrate legacy session-level segmentations to the first tile as layers
            if legacy_segs and s.tiles:
                from collections import defaultdict
                from app.domain.tile import LAYER_COLORS
                grouped = defaultdict(list)
                for seg in legacy_segs:
                    model = seg.get("model", "Imported")
                    poly = seg.get("polygon", [])
                    if poly:
                        grouped[model].append(poly)
                for i, (model, polys) in enumerate(grouped.items()):
                    color = LAYER_COLORS[i % len(LAYER_COLORS)]
                    s.tiles[0].add_layer(model, model, polys, color)
            
            s.grid_color = item.get("grid_color", "#FFFF00")
            # Resolve export_dir relative path
            raw_export_dir = item.get("export_dir", None)
            if raw_export_dir:
                resolved_ed = os.path.normpath(os.path.join(project_dir, raw_export_dir))
                s.export_dir = resolved_ed if os.path.isdir(resolved_ed) else raw_export_dir
            else:
                s.export_dir = None
            s.export_format = item.get("export_format", None)
            sessions.append(s)
        return sessions, missing

    def save_project(self, path, sessions):
        """Converts sessions to data and saves to file.

        Image paths are stored relative to the .lab file directory
        for portability. The original absolute path is kept as fallback.

        Raises:
            ProjectIOError: propagated from the I/O layer on write failure.
        """
        project_dir = os.path.dirname(os.path.abspath(path))
        data = []
        for s in sessions:
            # Store relative path for portability + absolute as fallback
            try:
                rel_path = os.path.relpath(s.path, project_dir)
            except ValueError:
                # relpath fails across drives on Windows
                rel_path = s.path

            # Relative export_dir
            rel_export_dir = None
            if s.export_dir:
                try:
                    rel_export_dir = os.path.relpath(s.export_dir, project_dir)
                except ValueError:
                    rel_export_dir = s.export_dir

            data.append({
                "path": rel_path,
                "abs_path": os.path.abspath(s.path),
                "grid_w": s.grid_w,
                "grid_h": s.grid_h,
                "tiles": [t.serialize() for t in s.tiles],
                "segmentations": [],  # kept empty for backward compat; actual data is in tiles
                "grid_color": s.grid_color,
                "export_dir": rel_export_dir,
                "export_format": s.export_format,
                "zoom_level": s.zoom_level,
                "camera_x": s.camera_x,
                "camera_y": s.camera_y
            })
        save_project_file(path, data)
