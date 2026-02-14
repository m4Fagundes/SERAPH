import os
from app.domain.session import ImageSession
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
            
            sel = item.get("selected_cells", [])
            s.selected_cells = set(tuple(x) for x in sel)
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
                "selected_cells": list(s.selected_cells),
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
        """Saves only the selected cells for a given session."""
        if not session or not output_dir: return 0
        
        count = 0
        for (c, r) in session.selected_cells:
            x1 = c * session.grid_w
            y1 = r * session.grid_h
            x2 = min(x1 + session.grid_w, session.real_width)
            y2 = min(y1 + session.grid_h, session.real_height)
            
            filename = self._get_export_filename(session.name, r, c, format_ext)
            full_path = os.path.join(output_dir, filename)
            
            tile = session.original_image.crop((x1, y1, x2, y2))
            if save_image_tile(tile, full_path, format_ext):
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
                
                tile = session.original_image.crop((x1, y1, x2, y2))
                if save_image_tile(tile, full_path, format_ext):
                    count += 1
        return count
