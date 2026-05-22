import os
import logging
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from app.domain.session import ImageSession

logger = logging.getLogger(__name__)

class ProjectManager:
    def __init__(self, main_window):
        self.mw = main_window
        self._current_project_path: str | None = None
        self._grid_w: int = 1000
        self._grid_h: int = 1000

    def get_grid_w(self) -> int:
        return self._grid_w

    def get_grid_h(self) -> int:
        return self._grid_h

    def set_grid(self, w: int, h: int) -> None:
        self._grid_w = w
        self._grid_h = h
        s = self.mw.current_session
        if s:
            s.grid_w = w
            s.grid_h = h
            self.mw.canvas_renderer.redraw()

    def new_project(self):
        self.mw.sessions.clear()
        self.mw.file_list.clear()
        self.mw.current_session = None
        self.mw.canvas_renderer.scene.clear()
        self._current_project_path = None
        self.mw.setWindowTitle("SERAPH")

    def open_project(self):
        f, _ = QFileDialog.getOpenFileName(self.mw, "Open Project", "", "Lab Project (*.lab)")
        if f:
            try:
                sessions, missing = self.mw.project_service.load_project(f)
                self.mw.sessions = sessions
                self.mw.file_list.clear()
                for s in self.mw.sessions:
                    self.mw.file_list.addItem(f" {s.name}")
                if self.mw.sessions:
                    self._activate_session(self.mw.sessions[0])
                # Remember path for subsequent auto-saves
                self._current_project_path = f
                self.mw.setWindowTitle(f"SERAPH — {os.path.basename(f)}")
            except Exception as e:
                QMessageBox.critical(self.mw, "Error", f"Could not load project: {e}")

    def save_project(self):
        """Save to the currently open file; if none, prompt for a path."""
        if self._current_project_path:
            self.mw.project_service.save_project(self._current_project_path, self.mw.sessions)
            self.mw.statusBar().showMessage(
                f"✅ Saved — {os.path.basename(self._current_project_path)}"
            )
        else:
            self.save_project_as()

    def save_project_as(self):
        """Always prompt for a new file path."""
        f, _ = QFileDialog.getSaveFileName(self.mw, "Save As", "", "Lab Project (*.lab)")
        if f:
            self.mw.project_service.save_project(f, self.mw.sessions)
            self._current_project_path = f
            self.mw.setWindowTitle(f"SERAPH — {os.path.basename(f)}")
            self.mw.statusBar().showMessage(f"✅ Saved — {os.path.basename(f)}")


    def add_image(self):
        path, _ = QFileDialog.getOpenFileName(self.mw, "Add Image", "", "Images (*.jpg *.png *.tif *.svs *.ndpi *.mrxs *.tiff *.bmp)")
        if path:
            try:
                s = ImageSession(path)
                s.grid_w = self._grid_w
                s.grid_h = self._grid_h
                
                self.mw.sessions.append(s)
                self.mw.file_list.addItem(s.name)
                self._activate_session(s)
            except Exception as e:
                QMessageBox.warning(self.mw, "Load Error", str(e))

    def switch_image_tab(self, *args):
        # Triggered when QListWidget row changes or receives click
        row = self.mw.file_list.currentRow()
        if 0 <= row < len(self.mw.sessions):
            self._activate_session(self.mw.sessions[row])

    def _activate_session(self, session):
        self.mw.current_session = session
        self._grid_w = session.grid_w
        self._grid_h = session.grid_h

        # Return to the Macro environment (full image view)
        self.mw.switch_to_canvas()
        self.mw.slice_previews.list_widget.clearSelection()

        # Reset camera
        if session.zoom_level == 1.0 and session.camera_x == 0:
            view_w = self.mw.canvas_renderer.width()
            view_h = self.mw.canvas_renderer.height()
            if view_w > 10:
                ratio = min(view_w / session.real_width, view_h / session.real_height)
                # Auto-fit zoom ensuring it's not overly huge
                session.zoom_level = min(ratio * 0.95, 2.0)
                # Center the camera coordinates in real pixel space
                session.camera_x = session.real_width // 2
                session.camera_y = session.real_height // 2

        # Sync zoom into renderer
        self.mw.canvas_renderer.viewport_zoom = session.zoom_level
        
        # Move camera to center of scene
        self.mw.canvas_renderer.centerOn(session.camera_x, session.camera_y)

        self.mw.statusBar().showMessage(f"Image: {session.name} | {session.real_width}x{session.real_height}px")
        self.mw.canvas_renderer.redraw()
        self.mw.slice_previews.update_previews()
        if hasattr(self.mw, '_update_breadcrumb'):
            self.mw._update_breadcrumb()

    # ── Tile Import ───────────────────────────────────────────────────────────

    def add_tile(self) -> None:
        """Open a tile descriptor (XML or GeoJSON) and import it into the current session."""
        s = self.mw.current_session
        if not s:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self.mw, "Add Tile", "No image session is active.")
            return

        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        path, _ = QFileDialog.getOpenFileName(
            self.mw,
            "Open Tile Descriptor",
            "",
            "All Supported (*.xml *.geojson *.json);;Tile Descriptor (*.xml);;GeoJSON Annotations (*.geojson);;JSON Annotations (*.json)",
        )
        if not path:
            return

        try:
            ext = os.path.splitext(path)[1].lower()
            if ext == ".geojson":
                new_indices = self.mw.tile_import_service.load_geojson(path, s)
                if not new_indices:
                    QMessageBox.warning(self.mw, "Import", "No valid annotations found.")
                    return
                # Refresh sidebar
                self.mw.slice_previews.update_previews()
                self.mw.statusBar().showMessage(
                    f"GeoJSON imported → {len(new_indices)} slices | {len(s.tiles)} total"
                )
                # Navigate to the first newly imported slice
                self.mw.switch_to_tile(new_indices[0])
                return
            elif ext == ".json":
                new_indices = self.mw.tile_import_service.load_json(path, s)
                if not new_indices:
                    QMessageBox.warning(self.mw, "Import", "No valid annotations found.")
                    return
                # Refresh sidebar
                self.mw.slice_previews.update_previews()
                self.mw.statusBar().showMessage(
                    f"JSON imported → {len(new_indices)} slices | {len(s.tiles)} total"
                )
                # Navigate to the first newly imported slice
                self.mw.switch_to_tile(new_indices[0])
                return
            else:
                new_idx = self.mw.tile_import_service.load_tile_xml(path, s)
        except Exception as exc:
            QMessageBox.critical(self.mw, "Import Error", str(exc))
            return

        # Refresh sidebar (XML path)
        self.mw.slice_previews.update_previews()
        self.mw.statusBar().showMessage(
            f"Tile imported → Slice {new_idx + 1} | {len(s.tiles)} slices total"
        )

        # Navigate to the newly imported slice using the Micro environment
        self.mw.switch_to_tile(new_idx)

