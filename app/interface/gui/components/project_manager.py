import os
import logging
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget, QHBoxLayout, QLabel, QLineEdit
from PyQt6.QtGui import QAction
from app.domain.session import ImageSession

logger = logging.getLogger(__name__)

class ProjectManager:
    def __init__(self, main_window):
        self.mw = main_window
        # Track the currently open .lab file path for auto-save
        self._current_project_path: str | None = None

    def setup_toolbar(self, toolbar):
        new_action = QAction("📄 New", self.mw)
        new_action.triggered.connect(self.new_project)
        toolbar.addAction(new_action)

        open_action = QAction("📂 Open", self.mw)
        open_action.triggered.connect(self.open_project)
        toolbar.addAction(open_action)

        # 💾 Save — saves to current file if open, otherwise prompts
        save_action = QAction("💾 Save", self.mw)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_project)
        toolbar.addAction(save_action)

        # 💾 Save As — always prompts for a new path
        saveas_action = QAction("💾 Save As", self.mw)
        saveas_action.triggered.connect(self.save_project_as)
        toolbar.addAction(saveas_action)

    def setup_grid_inputs(self, toolbar):
        lbl_w = QLabel(" W: ")
        lbl_w.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        toolbar.addWidget(lbl_w)
        
        self.entry_w = QLineEdit("1000")
        self.entry_w.setFixedWidth(60)
        self.entry_w.setStyleSheet("background: #3c3c3c; border: 1px solid #555555; border-radius: 4px; padding: 4px; color: white; font-family: 'Segoe UI', Tahoma, sans-serif;")
        self.entry_w.textChanged.connect(self._grid_changed)
        toolbar.addWidget(self.entry_w)
        
        lbl_h = QLabel("  H: ")
        lbl_h.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        toolbar.addWidget(lbl_h)
        
        self.entry_h = QLineEdit("1000")
        self.entry_h.setFixedWidth(60)
        self.entry_h.setStyleSheet("background: #3c3c3c; border: 1px solid #555555; border-radius: 4px; padding: 4px; color: white; font-family: 'Segoe UI', Tahoma, sans-serif;")
        self.entry_h.textChanged.connect(self._grid_changed)
        toolbar.addWidget(self.entry_h)

    def _grid_changed(self):
        s = self.mw.current_session
        if s:
            try:
                s.grid_w = int(self.entry_w.text())
                s.grid_h = int(self.entry_h.text())
                self.mw.canvas_renderer.redraw()
            except ValueError:
                pass

    def new_project(self):
        self.mw.sessions.clear()
        self.mw.file_list.clear()
        self.mw.current_session = None
        self.mw.canvas_renderer.scene.clear()
        self._current_project_path = None
        self.mw.setWindowTitle("Tiles Grid Analyzer")

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
                self.mw.setWindowTitle(f"Tiles Grid Analyzer — {os.path.basename(f)}")
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
            self.mw.setWindowTitle(f"Tiles Grid Analyzer — {os.path.basename(f)}")
            self.mw.statusBar().showMessage(f"✅ Saved — {os.path.basename(f)}")


    def add_image(self):
        path, _ = QFileDialog.getOpenFileName(self.mw, "Add Image", "", "Images (*.jpg *.png *.tif *.svs *.ndpi *.mrxs *.tiff *.bmp)")
        if path:
            try:
                s = ImageSession(path)
                s.grid_w = int(self.entry_w.text())
                s.grid_h = int(self.entry_h.text())
                
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
        self.entry_w.setText(str(session.grid_w))
        self.entry_h.setText(str(session.grid_h))

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

    # ── Tile Import ───────────────────────────────────────────────────────────

    def add_tile(self) -> None:
        """Open a tile XML descriptor and import it into the current session."""
        s = self.mw.current_session
        if not s:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self.mw, "Add Tile", "No image session is active.")
            return

        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        path, _ = QFileDialog.getOpenFileName(
            self.mw, "Open Tile Descriptor", "", "Tile Descriptor (*.xml)"
        )
        if not path:
            return

        try:
            new_idx = self.mw.tile_import_service.load_tile_xml(path, s)
        except Exception as exc:
            QMessageBox.critical(self.mw, "Import Error", str(exc))
            return

        # Refresh sidebar
        self.mw.slice_previews.update_previews()
        self.mw.statusBar().showMessage(
            f"Tile imported → Slice {new_idx + 1} | {len(s.tiles)} slices total"
        )

        # Navigate to the newly imported slice using the Micro environment
        self.mw.switch_to_tile(new_idx)

