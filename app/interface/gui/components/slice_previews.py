import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QAbstractItemView, QMenu, QPushButton, QDialog, QFormLayout, QLineEdit,
    QTextEdit, QDialogButtonBox, QStackedWidget
)
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtCore import Qt
from app.application.pixel_mask_service import PixelMaskService
from app.interface.gui.theme import PALETTE, label_section

logger = logging.getLogger(__name__)


class _SliceRow(QWidget):
    """Custom row widget: [colour swatch] [name / tile count] ... [✏️ edit] [✕ delete]"""

    def __init__(self, name: str, tile_count: int, color_hex: str, on_delete, on_rename):
        super().__init__()
        self.setStyleSheet("background: transparent;")
        self.setMinimumHeight(38)

        self.on_rename = on_rename

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(8)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Colour swatch
        swatch = QLabel()
        swatch.setFixedSize(14, 14)
        swatch.setStyleSheet(f"""
            background-color: {color_hex};
            border-radius: 4px;
            border: 1px solid rgba(255,255,255,0.15);
        """)
        row.addWidget(swatch)

        # Name Edit (Acts as a Label when read-only)
        from PyQt6.QtWidgets import QSizePolicy
        self.name_edit = QLineEdit(name)
        self.name_edit.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.name_edit.setMinimumWidth(20)
        self.name_edit.setReadOnly(True)
        self.name_edit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.name_edit.setCursorPosition(0)
        self.name_edit.setStyleSheet(
            f'QLineEdit[readOnly="true"] {{'
            f' background: transparent;'
            f" color: {PALETTE['text_primary']};"
            f' border: none;'
            f' font-weight: bold;'
            f' font-size: 10pt;'
            f" font-family: 'Segoe UI', Tahoma, sans-serif;"
            f' }}'
            f' QLineEdit[readOnly="false"] {{'
            f" background: {PALETTE['bg_surface']};"
            f" color: {PALETTE['text_primary']};"
            f" border: 1px solid {PALETTE['border_focus']};"
            f' border-radius: 3px;'
            f' padding: 2px 4px;'
            f' font-size: 10pt;'
            f" font-family: 'Segoe UI', Tahoma, sans-serif;"
            f' }}'
        )
        self.name_edit.editingFinished.connect(self.finish_edit)
        row.addWidget(self.name_edit, stretch=1)

        # Tile count
        count_lbl = QLabel(f"({tile_count} tiles)")
        count_lbl.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 8pt; font-family: 'Segoe UI', Tahoma, sans-serif;")
        row.addWidget(count_lbl)

        # Edit button
        edit_btn = QPushButton("✏️")
        edit_btn.setFixedSize(24, 24)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setToolTip("Rename slice")
        edit_btn.setStyleSheet(
            f"QPushButton {{"
            f" background: transparent;"
            f" color: {PALETTE['text_muted']};"
            f" border: none;"
            f" font-size: 11pt;"
            f" border-radius: 4px;"
            f" }}"
            f" QPushButton:hover {{ background: {PALETTE['bg_hover']}; }}"
            f" QPushButton:pressed {{ background: {PALETTE['bg_panel']}; }}"
        )
        edit_btn.clicked.connect(self.start_edit)
        row.addWidget(edit_btn)

        # Delete button
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("Delete this slice")
        del_btn.setStyleSheet(
            f"QPushButton {{"
            f" background: transparent;"
            f" color: {PALETTE['text_muted']};"
            f" border: none;"
            f" font-size: 12pt;"
            f" font-weight: bold;"
            f" border-radius: 4px;"
            f" }}"
            f" QPushButton:hover {{ background: {PALETTE['btn_danger_hover']}; color: white; }}"
            f" QPushButton:pressed {{ background: {PALETTE['btn_danger_press']}; }}"
        )
        del_btn.clicked.connect(on_delete)
        row.addWidget(del_btn)

    def mouseDoubleClickEvent(self, event):
        self.start_edit()
        super().mouseDoubleClickEvent(event)

    def start_edit(self):
        self.name_edit.setReadOnly(False)
        self.name_edit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.name_edit.style().unpolish(self.name_edit)
        self.name_edit.style().polish(self.name_edit)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def finish_edit(self):
        new_name = self.name_edit.text().strip()
        if new_name:
            self.on_rename(new_name)
            self.name_edit.setText(new_name)
        
        self.name_edit.setReadOnly(True)
        self.name_edit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.name_edit.setCursorPosition(0)
        self.name_edit.style().unpolish(self.name_edit)
        self.name_edit.style().polish(self.name_edit)
        self.clearFocus()


class SlicePreviews(QWidget):
    """Shows the list of extracted slice regions in the left panel."""

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._pms = PixelMaskService()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(10)

        lbl = QLabel("PROJECT SLICES")
        lbl.setStyleSheet(label_section())
        self.layout.addWidget(lbl)

        self.list_widget = QListWidget()
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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

        if not s.tiles:
            placeholder = QListWidgetItem("No slices — import a tile to get started")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            font = placeholder.font()
            font.setItalic(True)
            placeholder.setFont(font)
            self.list_widget.addItem(placeholder)
            return

        for i, tile in enumerate(s.tiles):
            name = tile.metadata.get("name") or f"Slice {i + 1}"
            color_hex = tile.color
            tile_count = len(tile.rects)

            # Capture `i` by value so the lambda closes over the right index
            def make_delete(idx=i):
                return lambda: self._delete_slice(idx)

            def make_rename(idx=i):
                return lambda new_name: self._rename_slice_inline(idx, new_name)

            row_widget = _SliceRow(name, tile_count, color_hex, on_delete=make_delete(), on_rename=make_rename())

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setSizeHint(row_widget.sizeHint())

            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row_widget)

    # ── Slice actions ─────────────────────────────────────────────────────────

    def _rename_slice_inline(self, idx: int, new_name: str) -> None:
        """Inline rename handler from the list item."""
        s = self.mw.current_session
        if not s or idx >= len(s.tiles):
            return
        s.tiles[idx].metadata["name"] = new_name

    def _delete_slice(self, idx: int) -> None:
        """Remove slice *idx* from the session and refresh the UI."""
        s = self.mw.current_session
        if not s or idx >= len(s.tiles):
            return

        tr = self.mw.tile_renderer

        # If we are currently editing this tile, leave isolation mode
        if tr.slice_idx == idx:
            self.mw.switch_to_canvas()
        elif tr.slice_idx is not None and tr.slice_idx > idx:
            # Adjust tracked index since everything shifts down
            tr._slice_idx -= 1

        # Release cached pixels before removal
        if hasattr(s.tiles[idx], "clear_cache"):
            s.tiles[idx].clear_cache()

        # Remove from unified tile list
        s.tiles.pop(idx)

        self.update_previews()
        self.mw.canvas_renderer.redraw()

    def on_item_clicked(self, item):
        """Navigate to the slice when clicked in the sidebar."""
        idx = item.data(Qt.ItemDataRole.UserRole)
        s = self.mw.current_session
        if not s or idx >= len(s.tiles):
            return

        # Delegate to MainWindow bounded-context transition
        self.mw.switch_to_tile(idx)

    # ── Context Menu ──────────────────────────────────────────────────────────

    def _show_context_menu(self, pos) -> None:
        """Show a right-click context menu on a slice list item."""
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        action_nav   = menu.addAction("🔍 Focus on Canvas")
        action_edit  = menu.addAction("✏️ Edit Properties")
        menu.addSeparator()
        action_del = menu.addAction("🗑️ Delete Slice")

        chosen = menu.exec(self.list_widget.mapToGlobal(pos))
        if chosen == action_nav:
            self.on_item_clicked(item)
        elif chosen == action_edit:
            self._edit_slice_properties(idx)
        elif chosen == action_del:
            self._delete_slice(idx)

    def _edit_slice_properties(self, idx: int) -> None:
        s = self.mw.current_session
        if not s or idx >= len(s.tiles):
            return
        
        tile = s.tiles[idx]
        meta = tile.metadata
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Properties")
        dialog.setMinimumWidth(350)
        
        layout = QFormLayout(dialog)
        
        name_input = QLineEdit(meta.get("name", ""))
        # Resolution is WSI-level — read from session
        microns_input = QLineEdit(s.microns_per_pixel)

        desc_input = QTextEdit()
        desc_input.setPlainText(meta.get("description", ""))
        desc_input.setMaximumHeight(80)

        comment_input = QTextEdit()
        comment_input.setPlainText(meta.get("comment", ""))
        comment_input.setMaximumHeight(80)

        layout.addRow("Name:", name_input)
        layout.addRow("µm/px (WSI):", microns_input)
        layout.addRow("Description:", desc_input)
        layout.addRow("Comment:", comment_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            meta["name"] = name_input.text().strip()
            meta["description"] = desc_input.toPlainText().strip()
            meta["comment"] = comment_input.toPlainText().strip()
            # Resolution is WSI-level — propagate to all tiles
            s.set_microns_per_pixel(microns_input.text().strip())
            # Force UI update if name changed
            self.update_previews()
