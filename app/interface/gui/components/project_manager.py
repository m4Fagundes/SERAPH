import os
import logging
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from app.domain.session import ImageSession, TILE_COLORS
from app.domain.tile import Tile

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
        self._clear_tabs()
        self.mw.current_session = None
        self.mw.canvas_renderer.scene.clear()
        self.mw.canvas_renderer.on_session_closed()
        self.mw.slice_previews.update_previews()
        if hasattr(self.mw, '_show_welcome_page'):
            self.mw._show_welcome_page()
        if hasattr(self.mw, '_update_breadcrumb'):
            self.mw._update_breadcrumb()
        if hasattr(self.mw, '_update_context_bar'):
            self.mw._update_context_bar()
        self._current_project_path = None
        self.mw.setWindowTitle("SERAPH")

    def open_project(self):
        f, _ = QFileDialog.getOpenFileName(self.mw, "Open Project", "", "Lab Project (*.lab)")
        if f:
            try:
                sessions, missing = self.mw.project_service.load_project(f)
                self.mw.sessions = sessions
                self._clear_tabs()
                self.mw.image_tabs.tab_bar.blockSignals(True)
                for s in self.mw.sessions:
                    self.mw.image_tabs.add_session_tab(s.name, tooltip=s.path)
                if self.mw.sessions:
                    self.mw.image_tabs.set_current_index(0)
                self.mw.image_tabs.tab_bar.blockSignals(False)
                if self.mw.sessions:
                    self._activate_session(self.mw.sessions[0])
                elif hasattr(self.mw, '_show_welcome_page'):
                    self.mw._show_welcome_page()
                self._current_project_path = f
                self.mw.setWindowTitle(f"SERAPH — {os.path.basename(f)}")
            except Exception as e:
                QMessageBox.critical(self.mw, "Error", f"Could not load project: {e}")

    def save_project(self):
        if self._current_project_path:
            self.mw.project_service.save_project(self._current_project_path, self.mw.sessions)
            self.mw.statusBar().showMessage(
                f"Saved — {os.path.basename(self._current_project_path)}"
            )
        else:
            self.save_project_as()

    def save_project_as(self):
        f, _ = QFileDialog.getSaveFileName(self.mw, "Save As", "", "Lab Project (*.lab)")
        if f:
            self.mw.project_service.save_project(f, self.mw.sessions)
            self._current_project_path = f
            self.mw.setWindowTitle(f"SERAPH — {os.path.basename(f)}")
            self.mw.statusBar().showMessage(f"Saved — {os.path.basename(f)}")

    def add_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self.mw, "Add Image", "",
            "Images (*.jpg *.png *.tif *.svs *.ndpi *.mrxs *.tiff *.bmp)"
        )
        if path:
            try:
                s = ImageSession(path)
                s.grid_w = self._grid_w
                s.grid_h = self._grid_h
                self.mw.sessions.append(s)
                self.mw.image_tabs.tab_bar.blockSignals(True)
                self.mw.image_tabs.add_session_tab(s.name, tooltip=path)
                self.mw.image_tabs.set_current_index(self.mw.image_tabs.count() - 1)
                self.mw.image_tabs.tab_bar.blockSignals(False)
                self._activate_session(s)
            except Exception as e:
                QMessageBox.warning(self.mw, "Load Error", str(e))

    def import_slice_images_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self.mw,
            "Import Slice Images Folder",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if not folder:
            return

        try:
            s = ImageSession(folder)
            s.name = os.path.basename(os.path.normpath(folder)) or "Image slices"
            s.grid_w = self._grid_w
            s.grid_h = self._grid_h
            s.tiles = []

            items = getattr(s.pyramid, "items", [])
            if not items:
                QMessageBox.warning(self.mw, "Import Slice Images", "No supported image files found in this folder.")
                return

            for idx, item in enumerate(items):
                x1 = int(item["x"])
                y1 = int(item["y"])
                x2 = x1 + int(item["width"])
                y2 = y1 + int(item["height"])
                tile = Tile(rects=[(x1, y1, x2, y2)])
                tile.color = TILE_COLORS[idx % len(TILE_COLORS)]
                tile.metadata["name"] = item.get("name", f"Slice {idx + 1}")
                tile.metadata["description"] = os.path.basename(item.get("path", ""))
                tile.metadata["source_image_path"] = item.get("path", "")
                s.tiles.append(tile)

            self.mw.sessions.append(s)
            self.mw.image_tabs.tab_bar.blockSignals(True)
            self.mw.image_tabs.add_session_tab(s.name, tooltip=folder)
            self.mw.image_tabs.set_current_index(self.mw.image_tabs.count() - 1)
            self.mw.image_tabs.tab_bar.blockSignals(False)
            self._activate_session(s)
            self.mw.statusBar().showMessage(
                f"Imported {len(s.tiles)} image slice{'s' if len(s.tiles) != 1 else ''} from {os.path.basename(folder)}"
            )
        except Exception as e:
            logger.exception("Failed to import image slice folder: %s", e)
            QMessageBox.warning(self.mw, "Import Slice Images Error", str(e))

    def _activate_session(self, session):
        self.mw.current_session = session
        self._grid_w = session.grid_w
        self._grid_h = session.grid_h

        self.mw.switch_to_canvas()
        self.mw.slice_previews.list_widget.clearSelection()

        if session.zoom_level == 1.0 and session.camera_x == 0:
            view_w = self.mw.canvas_renderer.width()
            view_h = self.mw.canvas_renderer.height()
            if view_w > 10:
                ratio = min(view_w / session.real_width, view_h / session.real_height)
                session.zoom_level = min(ratio * 0.95, 2.0)
                session.camera_x = session.real_width // 2
                session.camera_y = session.real_height // 2

        self.mw.canvas_renderer.viewport_zoom = session.zoom_level
        self.mw.canvas_renderer.centerOn(session.camera_x, session.camera_y)
        self.mw.statusBar().showMessage(
            f"Image: {session.name} | {session.real_width}x{session.real_height}px"
        )
        self.mw.canvas_renderer.redraw()
        self.mw.slice_previews.update_previews()
        if hasattr(self.mw, '_update_breadcrumb'):
            self.mw._update_breadcrumb()
        if hasattr(self.mw, '_update_context_bar'):
            self.mw._update_context_bar()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clear_tabs(self) -> None:
        self.mw.image_tabs.clear_tabs()

    # ── Tile Import ───────────────────────────────────────────────────────────

    def add_tile(self) -> None:
        s = self.mw.current_session
        if not s:
            QMessageBox.warning(self.mw, "Add Tile", "No image session is active.")
            return

        paths, _ = QFileDialog.getOpenFileNames(
            self.mw,
            "Open Tile Descriptor(s)",
            "",
            "All Supported (*.xml *.geojson *.json);;Tile Descriptor (*.xml);;GeoJSON Annotations (*.geojson);;JSON Annotations (*.json)",
        )
        if not paths:
            return

        imported_indices: list[int] = []
        failures: list[tuple[str, str]] = []

        for path in paths:
            ext = os.path.splitext(path)[1].lower()
            try:
                if ext == ".geojson":
                    imported_indices.extend(self.mw.tile_import_service.load_geojson(path, s))
                elif ext == ".json":
                    imported_indices.extend(self.mw.tile_import_service.load_json(path, s))
                else:
                    imported_indices.append(self.mw.tile_import_service.load_tile_xml(path, s))
            except Exception as exc:
                failures.append((os.path.basename(path), str(exc)))

        if not imported_indices:
            if failures:
                msg = "\n".join(f"{name}: {err}" for name, err in failures[:8])
                if len(failures) > 8:
                    msg += f"\n...and {len(failures) - 8} more."
                QMessageBox.critical(self.mw, "Import Error", msg)
            else:
                QMessageBox.warning(self.mw, "Import", "No valid annotations found.")
            return

        self.mw.slice_previews.update_previews()
        self.mw.statusBar().showMessage(
            f"Imported {len(imported_indices)} slice{'s' if len(imported_indices) != 1 else ''} "
            f"from {len(paths)} file{'s' if len(paths) != 1 else ''} | {len(s.tiles)} slices total"
        )
        self.mw.switch_to_tile(imported_indices[0])

        if failures:
            msg = "\n".join(f"{name}: {err}" for name, err in failures[:8])
            if len(failures) > 8:
                msg += f"\n...and {len(failures) - 8} more."
            QMessageBox.warning(
                self.mw,
                "Partial Import",
                f"Imported {len(imported_indices)} slice(s), but {len(failures)} file(s) failed:\n\n{msg}",
            )
