import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QAbstractItemView
from PyQt6.QtGui import QColor, QPixmap, QIcon
from PyQt6.QtCore import Qt

logger = logging.getLogger(__name__)

class SlicePreviews(QWidget):
    """
    Shows small thumbnails of extracted regions.
    """
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 10, 0, 0)
        
        lbl = QLabel("PROJECT SLICES")
        lbl.setStyleSheet("color: #aaaaaa; font-size: 11px; font-weight: bold; margin-bottom: 5px;")
        self.layout.addWidget(lbl)
        
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget { 
                background-color: #2a2a2a; 
                border: none; 
                color: #cccccc; 
                outline: none; 
            }
            QListWidget::item { 
                padding: 8px; 
                border-bottom: 1px solid #333333; 
            }
            QListWidget::item:selected { 
                background-color: #37373d; 
            }
        """)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        self.layout.addWidget(self.list_widget)
        
    def update_previews(self):
        self.list_widget.clear()
        s = self.mw.current_session
        if not s: return
        
        for i, slice_rects in enumerate(s.selected_cells):
            meta = s.slice_metadata[i] if i < len(s.slice_metadata) else {}
            name = meta.get("name") or f"Slice {i+1}"
            
            color_hex = s.tile_colors[i] if i < len(s.tile_colors) else "#00FFFF"
            
            # Create a small colored icon for the sidebar instead of reading full pixels to keep it fast
            pix = QPixmap(16, 16)
            pix.fill(QColor(color_hex))
            icon = QIcon(pix)
            
            # Count logical tiles within this slice region
            tile_count = sum(1 for _ in slice_rects)
            
            item = QListWidgetItem(icon, f" {name} ({tile_count} tiles)")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list_widget.addItem(item)

    def on_item_clicked(self, item):
        """Navigate to the slice when clicked in the sidebar"""
        idx = item.data(Qt.ItemDataRole.UserRole)
        s = self.mw.current_session
        if not s or idx >= len(s.selected_cells): return
        
        # Enable Isolation Mode on the Main Canvas instead of a Popup
        self.mw.canvas_renderer.isolated_slice_idx = idx
        
        # Calculate Bounding Box Math for the Slice
        slice_rects = s.selected_cells[idx]
        if slice_rects:
            min_x = min(r[0] for r in slice_rects)
            min_y = min(r[1] for r in slice_rects)
            max_x = max(r[2] for r in slice_rects)
            max_y = max(r[3] for r in slice_rects)
            
            w = max_x - min_x
            h = max_y - min_y
            cx = min_x + (w / 2)
            cy = min_y + (h / 2)
            
            # Viewport dimensions to perform Auto-Zoom fit
            view_w = self.mw.canvas_renderer.viewport().width()
            view_h = self.mw.canvas_renderer.viewport().height()
            
            # Allow 10% padding so the edges of the vignette are visible
            fit_zoom = min((view_w * 0.9) / w, (view_h * 0.9) / h, 5.0) if w > 0 and h > 0 else 1.0
            
            self.mw.canvas_renderer.viewport_zoom = fit_zoom
            
            # Force the GPU camera to apply the new matrix and re-center
            self.mw.canvas_renderer.resetTransform()
            self.mw.canvas_renderer.scale(fit_zoom, fit_zoom)
            self.mw.canvas_renderer.centerOn(cx, cy)
            
        self.mw.canvas_renderer.redraw()
