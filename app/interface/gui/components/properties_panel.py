import logging
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QFormLayout, QLineEdit, QTextEdit, QLabel,
    QVBoxLayout, QScrollArea
)
from PyQt6.QtCore import Qt

logger = logging.getLogger(__name__)

class PropertiesPanel(QDockWidget):
    """
    Persistent sidebar for viewing and editing Tile metadata.
    Automatically syncs changes back to the underlying Tile domain entity.
    """
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.setStyleSheet("""
            QDockWidget { 
                background-color: #252526; 
                color: #ccc; 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }
            QLabel { 
                color: #cccccc; 
                font-size: 8pt;
            }
            QLineEdit, QTextEdit { 
                background-color: #3c3c3c; 
                color: #ffffff; 
                border: 1px solid #555555; 
                border-radius: 4px;
                padding: 4px;
                selection-background-color: #007acc;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 1px solid #007acc;
                background-color: #444444;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QWidget#ScrollContent {
                background-color: #252526;
            }
        """)
        
        self._current_tile = None
        
        # Create a scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Inner container for the scroll area
        self.container = QWidget()
        self.container.setObjectName("ScrollContent")
        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(12)
        
        # Title Label
        self.lbl_title = QLabel("TILE PROPERTIES")
        self.lbl_title.setStyleSheet("color: #aaaaaa; font-size: 8pt; font-weight: bold; letter-spacing: 1px;")
        self.main_layout.addWidget(self.lbl_title)
        
        # Form Layout for inputs
        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(10)
        
        # Inputs
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Enter tile name...")
        
        self.input_microns = QLineEdit()
        self.input_microns.setPlaceholderText("e.g. 0.25")
        
        self.input_desc = QTextEdit()
        self.input_desc.setMaximumHeight(80)
        self.input_desc.setPlaceholderText("Detailed description of this slice...")
        
        self.input_comment = QTextEdit()
        self.input_comment.setMaximumHeight(80)
        self.input_comment.setPlaceholderText("Any additional comments...")
        
        self.form_layout.addRow("Nome (Name):", self.input_name)
        self.form_layout.addRow("Microns/Pixel:", self.input_microns)
        self.form_layout.addRow("Descrição:", self.input_desc)
        self.form_layout.addRow("Comentário:", self.input_comment)
        
        self.main_layout.addLayout(self.form_layout)
        
        # Stretch spacer at the bottom to force everything to align to the TOP
        self.main_layout.addStretch(1)
        
        self.scroll_area.setWidget(self.container)
        self.setWidget(self.scroll_area)
        
        # Connect signals for auto-save
        self.input_name.textChanged.connect(self._save_metadata)
        self.input_microns.textChanged.connect(self._save_metadata)
        self.input_desc.textChanged.connect(self._save_metadata)
        self.input_comment.textChanged.connect(self._save_metadata)
        
        self.clear() # Start disabled and clear
        
    def load_tile(self, tile):
        """Populate the panel with a specific Tile's metadata block and enable edits."""
        self._current_tile = None # unbind temporarily to prevent auto-save triggering on load
        
        # Default fallback
        meta = tile.metadata
        self.input_name.setText(meta.get("name", ""))
        self.input_microns.setText(meta.get("microns_per_pixel", ""))
        self.input_desc.setPlainText(meta.get("description", ""))
        self.input_comment.setPlainText(meta.get("comment", ""))
        
        self.container.setEnabled(True)
        self._current_tile = tile

    def clear(self):
        """Clear fields and disable panel when no tile is selected."""
        self._current_tile = None
        self.input_name.clear()
        self.input_microns.clear()
        self.input_desc.clear()
        self.input_comment.clear()
        self.container.setEnabled(False)
        
    def _save_metadata(self):
        """Auto-save changes to the currently bound Tile entity."""
        if self._current_tile is None:
            return
            
        m = self._current_tile.metadata
        m["name"] = self.input_name.text()
        m["microns_per_pixel"] = self.input_microns.text()
        m["description"] = self.input_desc.toPlainText()
        m["comment"] = self.input_comment.toPlainText()
