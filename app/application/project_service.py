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
            
            sel = item.get("selected_regions", item.get("selected_cells", []))
            if sel and isinstance(sel[0], (list, tuple)):
                if sel[0] and isinstance(sel[0][0], (list, tuple)):
                    s.selected_cells = [set(tuple(r) for r in group) for group in sel]
                else:
                    s.selected_cells = [{tuple(r)} for r in sel if len(r) == 4]
            s.slice_metadata = item.get("slice_metadata", [])
            # Load polygon data (brush-drawn slices)
            raw_polys = item.get("selected_polygons", [])
            s.selected_polygons = [
                [tuple(pt) for pt in poly] if poly else None
                for poly in raw_polys
            ]
            s.sync_metadata()
            # Restore exclusion rects
            raw_excls = item.get("slice_exclusions", [])
            s.slice_exclusions = [
                [tuple(r) for r in tile_excls] if tile_excls else []
                for tile_excls in raw_excls
            ]
            s.sync_metadata()
            # Restore tile colors if saved
            saved_colors = item.get("tile_colors", [])
            if saved_colors:
                s.tile_colors = saved_colors[:len(s.selected_cells)]
                s.sync_metadata()  # fills remaining colors from palette
            s.grid_color = item.get("grid_color", "#FFFF00")
            # Resolve export_dir relative path
            raw_export_dir = item.get("export_dir", None)
            if raw_export_dir:
                resolved_ed = os.path.normpath(os.path.join(project_dir, raw_export_dir))
                s.export_dir = resolved_ed if os.path.isdir(resolved_ed) else raw_export_dir
            else:
                s.export_dir = None
            s.export_format = item.get("export_format", None)
            # Restore pixel masks (per-slice set of (px, py) removed coords)
            raw_masks = item.get("pixel_masks", [])
            s.pixel_masks = [
                {tuple(p) for p in m} for m in raw_masks
            ]
            # Pad pixel_masks to match selected_cells length
            while len(s.pixel_masks) < len(s.selected_cells):
                s.pixel_masks.append(set())
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
                "selected_regions": [[list(r) for r in group] for group in s.selected_cells],
                "selected_polygons": [
                    [list(pt) for pt in poly] if poly else None
                    for poly in s.selected_polygons
                ],
                "slice_metadata": s.slice_metadata,
                "slice_exclusions": [
                    [list(r) for r in excl] if excl else []
                    for excl in s.slice_exclusions
                ],
                "pixel_masks": [
                    [list(p) for p in m]
                    for m in (s.pixel_masks if hasattr(s, 'pixel_masks') else [])
                ],
                "tile_colors": s.tile_colors,
                "grid_color": s.grid_color,
                "export_dir": rel_export_dir,
                "export_format": s.export_format,
                "zoom_level": s.zoom_level,
                "camera_x": s.camera_x,
                "camera_y": s.camera_y
            })
        save_project_file(path, data)
