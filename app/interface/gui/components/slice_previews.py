import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QAbstractItemView, QMenu, QPushButton,
)
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtCore import Qt
from app.application.services import PixelMaskService
from app.interface.gui.components.tile_preview_dialog import TilePreviewDialog

logger = logging.getLogger(__name__)


class _SliceRow(QWidget):
    """Custom row widget: [colour swatch] [name / tile count] ... [✕ delete]"""

    def __init__(self, name: str, tile_count: int, color_hex: str, on_delete):
        super().__init__()
        self.setStyleSheet("background: transparent;")

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 4, 4)
        row.setSpacing(6)

        # Colour swatch
        swatch = QLabel()
        pix = QPixmap(12, 12)
        pix.fill(QColor(color_hex))
        swatch.setPixmap(pix)
        swatch.setFixedSize(12, 12)
        row.addWidget(swatch)

        # Name + tile count
        lbl = QLabel(
            f"{name}  <span style='color:#666;font-size:10px;'>({tile_count} tiles)</span>"
        )
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet("color: #cccccc; font-size: 12px;")
        row.addWidget(lbl, stretch=1)

        # Delete button
        btn = QPushButton("✕")
        btn.setFixedSize(20, 20)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Delete this slice")
        btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                border: none;
                font-size: 13px;
                padding: 0;
            }
            QPushButton:hover  { color: #ff5555; }
            QPushButton:pressed { color: #cc0000; }
        """)
        btn.clicked.connect(on_delete)
        row.addWidget(btn)


class SlicePreviews(QWidget):
    """Shows the list of extracted slice regions in the left panel."""

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._pms = PixelMaskService()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 10, 0, 0)

        lbl = QLabel("PROJECT SLICES")
        lbl.setStyleSheet(
            "color: #aaaaaa; font-size: 11px; font-weight: bold; margin-bottom: 5px;"
        )
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
                padding: 0px;
                border-bottom: 1px solid #333333;
            }
            QListWidget::item:hover {
                background-color: #3e3e42;
            }
            QListWidget::item:selected {
                background-color: #37373d;
            }
        """)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.layout.addWidget(self.list_widget)

    # ── Public ────────────────────────────────────────────────────────────────

    def update_previews(self):
        self.list_widget.clear()
        s = self.mw.current_session
        if not s:
            return

        for i, slice_rects in enumerate(s.selected_cells):
            meta = s.slice_metadata[i] if i < len(s.slice_metadata) else {}
            name = meta.get("name") or f"Slice {i + 1}"
            color_hex = s.tile_colors[i] if i < len(s.tile_colors) else "#00FFFF"
            tile_count = len(slice_rects)

            # Capture `i` by value so the lambda closes over the right index
            def make_delete(idx=i):
                return lambda: self._delete_slice(idx)

            row_widget = _SliceRow(name, tile_count, color_hex, on_delete=make_delete())

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setSizeHint(row_widget.sizeHint())

            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row_widget)

    # ── Slice actions ─────────────────────────────────────────────────────────

    def _delete_slice(self, idx: int) -> None:
        """Remove slice *idx* from the session and refresh the UI."""
        s = self.mw.current_session
        if not s or idx >= len(s.selected_cells):
            return

        cr = self.mw.canvas_renderer

        # Adjust or clear isolation mode
        if cr.isolated_slice_idx == idx:
            cr.isolated_slice_idx = None
        elif cr.isolated_slice_idx is not None and cr.isolated_slice_idx > idx:
            cr.isolated_slice_idx -= 1

        # Remove from all parallel lists
        s.selected_cells.pop(idx)
        if hasattr(s, "selected_polygons") and idx < len(s.selected_polygons):
            s.selected_polygons.pop(idx)
        if hasattr(s, "pixel_masks") and idx < len(s.pixel_masks):
            s.pixel_masks.pop(idx)
        if idx < len(s.slice_metadata):
            s.slice_metadata.pop(idx)
        if idx < len(s.tile_colors):
            s.tile_colors.pop(idx)

        s.sync_metadata()
        self.update_previews()
        cr.redraw()

    def on_item_clicked(self, item):
        """Navigate to the slice when clicked in the sidebar."""
        idx = item.data(Qt.ItemDataRole.UserRole)
        s = self.mw.current_session
        if not s or idx >= len(s.selected_cells):
            return

        self.mw.canvas_renderer.isolated_slice_idx = idx

        slice_rects = s.selected_cells[idx]
        if slice_rects:
            min_x = min(r[0] for r in slice_rects)
            min_y = min(r[1] for r in slice_rects)
            max_x = max(r[2] for r in slice_rects)
            max_y = max(r[3] for r in slice_rects)

            w = max_x - min_x
            h = max_y - min_y
            cx = min_x + w / 2
            cy = min_y + h / 2

            view_w = self.mw.canvas_renderer.viewport().width()
            view_h = self.mw.canvas_renderer.viewport().height()
            fit_zoom = min((view_w * 0.9) / w, (view_h * 0.9) / h, 5.0) if w > 0 and h > 0 else 1.0

            self.mw.canvas_renderer.viewport_zoom = fit_zoom
            self.mw.canvas_renderer.resetTransform()
            self.mw.canvas_renderer.scale(fit_zoom, fit_zoom)
            self.mw.canvas_renderer.centerOn(cx, cy)

        self.mw.canvas_renderer.redraw()

    # ── Context Menu ──────────────────────────────────────────────────────────

    def _show_context_menu(self, pos) -> None:
        """Show a right-click context menu on a slice list item."""
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #2d2d2d; color: #eeeeee; border: 1px solid #555; }
            QMenu::item:selected { background-color: #3e3e4f; }
        """)
        action_nav   = menu.addAction("🔍 Focar no Canvas")
        action_real  = menu.addAction("🖼️ Ver em Resolução Real")
        action_pixel = menu.addAction("🎨 Abrir Editor de Pixel")
        menu.addSeparator()
        action_del = menu.addAction("🗑️ Deletar Slice")

        chosen = menu.exec(self.list_widget.mapToGlobal(pos))
        if chosen == action_nav:
            self.on_item_clicked(item)
        elif chosen == action_real:
            self.open_tile_preview(idx)
        elif chosen == action_pixel:
            self.open_pixel_editor(idx)
        elif chosen == action_del:
            self._delete_slice(idx)

    def open_tile_preview(self, idx: int) -> None:
        """Open the 1:1 real-resolution tile viewer for slice *idx*."""
        s = self.mw.current_session
        if not s or idx >= len(s.selected_cells):
            return
        dialog = TilePreviewDialog(session=s, slice_idx=idx, parent=self.mw)
        dialog.exec()

    def open_pixel_editor(self, idx: int) -> None:
        """Open the pixel-level editor dialog for slice *idx*."""
        from app.interface.gui.components.pixel_editor import SlicePixelEditorDialog

        s = self.mw.current_session
        if not s or idx >= len(s.selected_cells):
            return

        undo_manager = getattr(self.mw, "undo_manager", None)
        dialog = SlicePixelEditorDialog(
            main_window=self.mw,
            slice_idx=idx,
            pixel_mask_service=self._pms,
            undo_manager=undo_manager,
        )
        dialog.exec()
