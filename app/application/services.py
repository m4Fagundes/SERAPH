import os
from PIL import Image
from app.domain.session import ImageSession
from app.domain.selection import rect_to_cells
from app.infrastructure.io import load_project_file, save_project_file, save_image_tile

class ProjectService:
    def load_project(self, path):
        """Loads a project and returns a list of ImageSession objects."""
        data = load_project_file(path)
        sessions = []
        for item in data:
            if "path" not in item: continue
            if not os.path.exists(item["path"]): continue
            
            s = ImageSession(item["path"])
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
            s.sync_metadata()
            s.grid_color = item.get("grid_color", "#FFFF00")
            s.export_dir = item.get("export_dir", None)
            s.export_format = item.get("export_format", None)
            sessions.append(s)
        return sessions

    def save_project(self, path, sessions):
        """Converts sessions to data and saves to file."""
        data = []
        for s in sessions:
            data.append({
                "path": s.path,
                "grid_w": s.grid_w,
                "grid_h": s.grid_h,
                "selected_regions": [[list(r) for r in group] for group in s.selected_cells],
                "slice_metadata": s.slice_metadata,
                "grid_color": s.grid_color,
                "export_dir": s.export_dir,
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

    def save_selected_cells(self, session, output_dir, format_ext):
        """Saves selected regions, one file per slice group."""
        if not session or not output_dir: return 0

        count = 0
        base = os.path.splitext(session.name)[0]
        for i, slice_rects in enumerate(session.selected_cells):
            # Bounding box of this slice
            bx1 = min(r[0] for r in slice_rects)
            by1 = min(r[1] for r in slice_rects)
            bx2 = max(r[2] for r in slice_rects)
            by2 = max(r[3] for r in slice_rects)

            w, h = bx2 - bx1, by2 - by1
            if format_ext in ('.png', '.webp'):
                out_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            else:
                out_img = Image.new("RGB", (w, h), (255, 255, 255))

            for (rx1, ry1, rx2, ry2) in slice_rects:
                # Use pyramid for streaming full-res crop (no full image in RAM)
                crop = session.pyramid.get_region_fullres(rx1, ry1, rx2 - rx1, ry2 - ry1)
                if out_img.mode == "RGBA" and crop.mode != "RGBA":
                    crop = crop.convert("RGBA")
                out_img.paste(crop, (rx1 - bx1, ry1 - by1))

            filename = f"{base}_slice{i + 1}{format_ext}"
            full_path = os.path.join(output_dir, filename)
            if save_image_tile(out_img, full_path, format_ext):
                count += 1
        return count

    def slice_all(self, session, output_dir, format_ext):
        """Slices the entire image into grid tiles."""
        if not session or not output_dir: return 0
        
        cols = (session.real_width + session.grid_w - 1) // session.grid_w
        rows = (session.real_height + session.grid_h - 1) // session.grid_h
        
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
        return count
