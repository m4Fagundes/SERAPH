import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QAbstractItemView, QMenu, QPushButton, QDialog, QFormLayout, QLineEdit,
    QTextEdit, QDialogButtonBox, QStackedWidget
)
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtCore import Qt
from app.application.pixel_mask_service import PixelMaskService

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
        self.name_edit.setStyleSheet("""
            QLineEdit[readOnly="true"] {
                background: transparent;
                color: #ffffff;
                border: none;
                font-weight: bold;
                font-size: 10pt;
                font-family: 'Segoe UI', Tahoma, sans-serif;
            }
            QLineEdit[readOnly="false"] {
                background: #1e1e1e;
                color: #ffffff;
                border: 1px solid #0e639c;
                border-radius: 3px;
                padding: 2px 4px;
                font-size: 10pt;
                font-family: 'Segoe UI', Tahoma, sans-serif;
            }
        """)
        self.name_edit.editingFinished.connect(self.finish_edit)
        row.addWidget(self.name_edit, stretch=1)

        # Tile count
        count_lbl = QLabel(f"({tile_count} tiles)")
        count_lbl.setStyleSheet("color: #aaaaaa; font-size: 8pt; font-family: 'Segoe UI', Tahoma, sans-serif;")
        row.addWidget(count_lbl)

        # Edit button
        edit_btn = QPushButton("✏️")
        edit_btn.setFixedSize(24, 24)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setToolTip("Rename slice")
        edit_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #cccccc;
                border: none;
                font-size: 11pt;
                border-radius: 4px;
            }
            QPushButton:hover { background: #3e3e42; }
            QPushButton:pressed { background: #252526; }
        """)
        edit_btn.clicked.connect(self.start_edit)
        row.addWidget(edit_btn)

        # Delete button
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("Delete this slice")
        del_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #bbbbbb;
                border: none;
                font-size: 12pt;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover { background: #e81123; color: white; }
            QPushButton:pressed { background: #b00b1b; }
        """)
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
        lbl.setStyleSheet(
            "color: #aaaaaa; font-size: 8pt; font-weight: bold; letter-spacing: 1px;"
        )
        self.layout.addWidget(lbl)

        self.list_widget = QListWidget()
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                color: #cccccc;
                outline: none;
            }
            QListWidget::item {
                background-color: rgba(255, 255, 255, 0.03);
                border-radius: 6px;
                margin-bottom: 6px;
                border: 1px solid transparent;
            }
            QListWidget::item:hover {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            QListWidget::item:selected {
                background-color: rgba(14, 99, 156, 0.3);
                border: 1px solid #0e639c;
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
        menu.setStyleSheet("""
            QMenu { background-color: #2d2d2d; color: #eeeeee; border: 1px solid #555; }
            QMenu::item:selected { background-color: #3e3e4f; }
        """)
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
        dialog.setStyleSheet("QDialog { background-color: #1e1e1e; color: #cccccc; } QLabel { color: #cccccc; } QLineEdit, QTextEdit { background-color: #333; color: white; border: 1px solid #555;}")
        
        layout = QFormLayout(dialog)
        
        name_input = QLineEdit(meta.get("name", ""))
        microns_input = QLineEdit(meta.get("microns_per_pixel", ""))
        
        desc_input = QTextEdit()
        desc_input.setPlainText(meta.get("description", ""))
        desc_input.setMaximumHeight(80)
        
        comment_input = QTextEdit()
        comment_input.setPlainText(meta.get("comment", ""))
        comment_input.setMaximumHeight(80)
        
        layout.addRow("Name:", name_input)
        layout.addRow("Microns/Pixel:", microns_input)
        layout.addRow("Description:", desc_input)
        layout.addRow("Comment:", comment_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            meta["name"] = name_input.text().strip()
            meta["microns_per_pixel"] = microns_input.text().strip()
            meta["description"] = desc_input.toPlainText().strip()
            meta["comment"] = comment_input.toPlainText().strip()
            # Force UI update if name changed
            self.update_previews()
