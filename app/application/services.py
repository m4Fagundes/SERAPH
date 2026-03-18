import logging
import os
from PIL import Image, ImageDraw
from app.domain.session import ImageSession
from app.domain.selection import rect_to_cells, draw_exclusion_rects
from app.infrastructure.exceptions import ProjectIOError
from app.infrastructure.io import load_project_file, save_project_file, save_image_tile

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
                "tile_colors": s.tile_colors,
                "grid_color": s.grid_color,
                "export_dir": rel_export_dir,
                "export_format": s.export_format,
                "zoom_level": s.zoom_level,
                "camera_x": s.camera_x,
                "camera_y": s.camera_y
            })
        save_project_file(path, data)

class ExportService:
    def _get_export_filename(self, image_name, row, col, format_ext):
        base = os.path.splitext(image_name)[0]
        return f"{base}_row{row}_col{col}{format_ext}"

    def save_selected_cells(self, session, output_dir, format_ext, progress_callback=None):
        """Saves selected regions, one file per slice group."""
        if not session or not output_dir: return 0

        count = 0
        total = len(session.selected_cells)
        base = os.path.splitext(session.name)[0]
        for i, slice_rects in enumerate(session.selected_cells):
            # Bounding box of this slice
            bx1 = min(r[0] for r in slice_rects)
            by1 = min(r[1] for r in slice_rects)
            bx2 = max(r[2] for r in slice_rects)
            by2 = max(r[3] for r in slice_rects)

            w, h = bx2 - bx1, by2 - by1
            # Always use RGBA internally so we can apply polygon mask
            out_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))

            for (rx1, ry1, rx2, ry2) in slice_rects:
                crop = session.pyramid.get_region_fullres(rx1, ry1, rx2 - rx1, ry2 - ry1)
                crop = crop.convert("RGBA")
                out_img.paste(crop, (rx1 - bx1, ry1 - by1))

            # Apply freehand polygon mask if this is a brush slice
            poly = session.selected_polygons[i] if i < len(session.selected_polygons) else None
            if poly and len(poly) >= 3:
                mask = Image.new("L", (w, h), 0)
                draw = ImageDraw.Draw(mask)
                local_pts = [(x - bx1, y - by1) for (x, y) in poly]
                draw.polygon(local_pts, fill=255)
                # Apply exclusion strokes (eraser brush holes)
                exclusions = session.slice_exclusions[i] if i < len(session.slice_exclusions) else []
                draw_exclusion_rects(draw, exclusions, bx1, by1, 1.0)
                out_img.putalpha(mask)

            # Flatten to white for non-transparent output formats
            if format_ext not in ('.png', '.webp'):
                bg = Image.new("RGB", (w, h), (255, 255, 255))
                alpha = out_img.split()[3]
                bg.paste(out_img.convert("RGB"), mask=alpha)
                out_img = bg

            filename = f"{base}_slice{i + 1}{format_ext}"
            full_path = os.path.join(output_dir, filename)
            if save_image_tile(out_img, full_path, format_ext):
                count += 1
            if progress_callback:
                progress_callback(i + 1, total)
        return count

    def slice_all(self, session, output_dir, format_ext, progress_callback=None):
        """Slices the entire image into grid tiles."""
        if not session or not output_dir: return 0
        
        cols = (session.real_width + session.grid_w - 1) // session.grid_w
        rows = (session.real_height + session.grid_h - 1) // session.grid_h
        total = cols * rows
        
        count = 0
        for row in range(rows):
            for col in range(cols):
                x1 = col * session.grid_w
                y1 = row * session.grid_h
                x2 = min(x1 + session.grid_w, session.real_width)
                y2 = min(y1 + session.grid_h, session.real_height)
                
                filename = self._get_export_filename(session.name, row, col, format_ext)
                full_path = os.path.join(output_dir, filename)
                
                # Use pyramid for streaming full-res crop (no full image in RAM)
                tile = session.pyramid.get_region_fullres(x1, y1, x2 - x1, y2 - y1)
                if save_image_tile(tile, full_path, format_ext):
                    count += 1
                if progress_callback:
                    progress_callback(count, total)
        return count

    def export_metadata(self, session, output_dir):
        """Export tile metadata as CSV and JSON alongside the tiles."""
        import csv
        import json as _json

        base = os.path.splitext(session.name)[0]
        rows = []

        for i, slice_rects in enumerate(session.selected_cells):
            bx1 = min(r[0] for r in slice_rects)
            by1 = min(r[1] for r in slice_rects)
            bx2 = max(r[2] for r in slice_rects)
            by2 = max(r[3] for r in slice_rects)
            w_px, h_px = bx2 - bx1, by2 - by1

            meta = session.slice_metadata[i] if i < len(session.slice_metadata) else {}
            mpp_str = meta.get("microns_per_pixel", "")
            try:
                mpp = float(mpp_str) if mpp_str else None
            except (ValueError, TypeError):
                mpp = None

            phys_w = f"{w_px * mpp:.1f} µm" if mpp else ""
            phys_h = f"{h_px * mpp:.1f} µm" if mpp else ""

            rows.append({
                "index": i + 1,
                "name": meta.get("name", f"Tile {i+1}"),
                "x1": bx1, "y1": by1, "x2": bx2, "y2": by2,
                "width_px": w_px, "height_px": h_px,
                "microns_per_pixel": mpp_str,
                "physical_width": phys_w,
                "physical_height": phys_h,
                "description": meta.get("description", ""),
                "source": session.name,
            })

        # CSV
        csv_path = os.path.join(output_dir, f"{base}_metadata.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

        # JSON
        json_path = os.path.join(output_dir, f"{base}_metadata.json")
        with open(json_path, "w", encoding="utf-8") as f:
            _json.dump(rows, f, indent=2, ensure_ascii=False)
