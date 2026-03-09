import os
import logging
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget, QHBoxLayout, QLabel, QLineEdit
from PyQt6.QtGui import QAction
from app.domain.session import ImageSession

logger = logging.getLogger(__name__)

class ProjectManager:
    def __init__(self, main_window):
        self.mw = main_window

    def setup_toolbar(self, toolbar):
        # Build Project Menus
        new_action = QAction("📄 New", self.mw)
        new_action.triggered.connect(self.new_project)
        toolbar.addAction(new_action)
        
        open_action = QAction("📂 Open", self.mw)
        open_action.triggered.connect(self.open_project)
        toolbar.addAction(open_action)

        save_action = QAction("💾 Save", self.mw)
        save_action.triggered.connect(self.save_project)
        toolbar.addAction(save_action)

    def setup_grid_inputs(self, toolbar):
        lbl_w = QLabel(" W: ")
        lbl_w.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        toolbar.addWidget(lbl_w)
        
        self.entry_w = QLineEdit("1000")
        self.entry_w.setFixedWidth(60)
        self.entry_w.setStyleSheet("background: #2a2a2a; border: 1px solid #444; border-radius: 4px; padding: 3px; color: white;")
        self.entry_w.textChanged.connect(self._grid_changed)
        toolbar.addWidget(self.entry_w)
        
        lbl_h = QLabel("  H: ")
        lbl_h.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        toolbar.addWidget(lbl_h)
        
        self.entry_h = QLineEdit("1000")
        self.entry_h.setFixedWidth(60)
        self.entry_h.setStyleSheet("background: #2a2a2a; border: 1px solid #444; border-radius: 4px; padding: 3px; color: white;")
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
            except Exception as e:
                QMessageBox.critical(self.mw, "Error", f"Could not load project: {e}")

    def save_project(self):
        f, _ = QFileDialog.getSaveFileName(self.mw, "Save As", "", "Lab Project (*.lab)")
        if f:
            self.mw.project_service.save_project(f, self.mw.sessions)
            self.mw.statusBar().showMessage(f"Project saved to {os.path.basename(f)}")

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

    def switch_image_tab(self):
        # Triggered when QListWidget row changes
        row = self.mw.file_list.currentRow()
        if 0 <= row < len(self.mw.sessions):
            self._activate_session(self.mw.sessions[row])

    def _activate_session(self, session):
        self.mw.current_session = session
        self.entry_w.setText(str(session.grid_w))
        self.entry_h.setText(str(session.grid_h))

        # Clear isolated mode to return to full image view
        self.mw.canvas_renderer.isolated_slice_idx = None
        self.mw.slice_previews.list_widget.clearSelection()

        # Reset camera
        if session.zoom_level == 1.0 and session.camera_x == 0:
            view_w = self.mw.canvas_renderer.width()
            view_h = self.mw.canvas_renderer.height()
            if view_w > 10:
                ratio = min(view_w / session.real_width, view_h / session.real_height)
                session.zoom_level = ratio * 0.9

        self.mw.statusBar().showMessage(f"Image: {session.name} | {session.real_width}x{session.real_height}px")
        self.mw.canvas_renderer.redraw()
        self.mw.slice_previews.update_previews()
