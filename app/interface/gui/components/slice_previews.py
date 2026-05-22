"""
Slice list sidebar for SERAPH.

Design decisions
----------------
- Row height 56 px: enough vertical breathing room without wasting space
  (VS Code Explorer items are ~22px; we carry a colour swatch + two text
  lines, so 56px is the minimum that avoids a cramped look).
- Hover-reveal for action buttons: keeps the list scannable at a glance;
  users discover the actions on first hover — pattern used by Linear,
  Figma Layers, VS Code's Explorer.
- Transparent buttons made visible via stylesheet swap rather than
  setVisible(False/True) — avoids layout reflow that would shift the name
  text left/right on every hover event.
- Count badge in header turns blue when items exist — a subtle affordance
  that the panel is populated and clickable.
- self.layout kept as an attribute (not renamed) because main_window.py
  appends the "Add Tile" button via self.slice_previews.layout.addWidget().
"""
from __future__ import annotations

import logging
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QCursor

from app.application.pixel_mask_service import PixelMaskService
from app.interface.gui.theme import PALETTE

logger = logging.getLogger(__name__)

_FONT = "'Segoe UI', Tahoma, sans-serif"
_ROW_H = 56  # px — content height of each list row


# ── Icon-button stylesheet helpers ────────────────────────────────────────────
# Buttons are always present in the layout (no reflow), but rendered
# invisible via transparent colour.  enterEvent / leaveEvent swaps the sheet.

def _btn_hidden() -> str:
    return "QPushButton { background: transparent; color: transparent; border: none; }"


def _btn_edit_style() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background: transparent; color: {p['text_muted']};"
        f" border: none; border-radius: 4px; font-size: 11pt; }}"
        f"QPushButton:hover {{ background: {p['bg_hover']}; color: {p['text_primary']}; }}"
        f"QPushButton:pressed {{ background: {p['bg_control']}; }}"
    )


def _btn_delete_style() -> str:
    p = PALETTE
    # Destructive action: neutral by default, red only on hover
    return (
        f"QPushButton {{ background: transparent; color: {p['text_muted']};"
        f" border: none; border-radius: 4px; font-size: 11pt; }}"
        f"QPushButton:hover {{ background: {p['btn_danger_hover']}; color: white; }}"
        f"QPushButton:pressed {{ background: {p['btn_danger_press']}; color: white; }}"
    )


# ── Row widget ────────────────────────────────────────────────────────────────

class _SliceRow(QWidget):
    """
    One row in the slice sidebar list.

    Visual structure (left → right):
      [10px] [swatch 10×10] [10px] [name 9pt bold / count 7.5pt muted] [✎ 26px] [2px] [✕ 26px] [8px]

    Action buttons (✎ ✕) are colour-hidden by default and revealed on hover.
    """

    def __init__(
        self,
        name: str,
        tile_count: int,
        color_hex: str,
        on_delete,
        on_rename,
    ):
        super().__init__()
        self.on_rename = on_rename

        self.setFixedHeight(_ROW_H)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 0, 8, 0)
        root.setSpacing(0)

        # ── Colour swatch ─────────────────────────────────────────────────────
        swatch = QLabel()
        swatch.setFixedSize(10, 10)
        swatch.setStyleSheet(
            f"background-color: {color_hex}; border-radius: 3px;"
            f" border: 1px solid rgba(255,255,255,0.15);"
        )
        root.addWidget(swatch, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addSpacing(10)

        # ── Text block: name (primary) stacked above count (secondary) ────────
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        # Name — doubles as an inline editor when double-clicked or ✎ pressed.
        # WA_TransparentForMouseEvents lets mouse events fall through to the
        # parent row so hover/click still register on the row, not the field.
        self.name_edit = QLineEdit(name)
        self.name_edit.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.name_edit.setMinimumWidth(20)
        self.name_edit.setReadOnly(True)
        self.name_edit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.name_edit.setCursorPosition(0)
        self.name_edit.setStyleSheet(
            f'QLineEdit[readOnly="true"] {{'
            f" background: transparent; color: {PALETTE['text_primary']};"
            f" border: none; font-weight: 600; font-size: 9pt;"
            f" font-family: {_FONT}; padding: 0; margin: 0; }}"
            f' QLineEdit[readOnly="false"] {{'
            f" background: {PALETTE['bg_surface']}; color: {PALETTE['text_primary']};"
            f" border: 1px solid {PALETTE['border_focus']}; border-radius: 3px;"
            f" padding: 1px 4px; font-size: 9pt; font-family: {_FONT}; }}"
        )
        self.name_edit.editingFinished.connect(self._finish_edit)

        # Secondary metadata — tile count
        count_text = f"{tile_count} tile{'s' if tile_count != 1 else ''}"
        self._count_lbl = QLabel(count_text)
        self._count_lbl.setStyleSheet(
            f"color: {PALETTE['text_disabled']}; font-size: 7.5pt;"
            f" font-family: {_FONT}; background: transparent; padding: 0; margin: 0;"
        )

        text_col.addStretch()
        text_col.addWidget(self.name_edit)
        text_col.addWidget(self._count_lbl)
        text_col.addStretch()
        root.addLayout(text_col, stretch=1)
        root.addSpacing(4)

        # ── Action buttons (hover-revealed) ───────────────────────────────────
        # ✎ U+270E (LOWER RIGHT PENCIL) — clean Unicode, no emoji variation
        # ✕ U+2715 (MULTIPLICATION X)   — slightly heavier than ×, lighter than ✗
        self._edit_btn = QPushButton("✎")
        self._edit_btn.setFixedSize(26, 26)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setToolTip("Rename slice  (double-click also works)")
        self._edit_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._edit_btn.setStyleSheet(_btn_hidden())
        self._edit_btn.clicked.connect(self._start_edit)

        self._del_btn = QPushButton("✕")
        self._del_btn.setFixedSize(26, 26)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setToolTip("Delete slice")
        self._del_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._del_btn.setStyleSheet(_btn_hidden())
        self._del_btn.clicked.connect(on_delete)

        root.addWidget(self._edit_btn)
        root.addSpacing(2)
        root.addWidget(self._del_btn)

    # ── Hover-reveal ──────────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._set_actions_visible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Qt fires leaveEvent on the parent when the cursor moves into a child
        # widget. We check the cursor is actually outside the row's bounding
        # rect before hiding — prevents the buttons from flickering as the
        # mouse crosses from the row background onto a button.
        cursor_local = self.mapFromGlobal(QCursor.pos())
        if not self.rect().contains(cursor_local) and not self.name_edit.hasFocus():
            self._set_actions_visible(False)
        super().leaveEvent(event)

    def _set_actions_visible(self, visible: bool) -> None:
        self._edit_btn.setStyleSheet(_btn_edit_style() if visible else _btn_hidden())
        self._del_btn.setStyleSheet(_btn_delete_style() if visible else _btn_hidden())

    # ── Inline rename ─────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event):
        self._start_edit()
        super().mouseDoubleClickEvent(event)

    def _start_edit(self):
        self.name_edit.setReadOnly(False)
        self.name_edit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.name_edit.style().unpolish(self.name_edit)
        self.name_edit.style().polish(self.name_edit)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _finish_edit(self):
        new_name = self.name_edit.text().strip()
        if new_name:
            self.on_rename(new_name)
            self.name_edit.setText(new_name)
        self.name_edit.setReadOnly(True)
        self.name_edit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.name_edit.setCursorPosition(0)
        self.name_edit.style().unpolish(self.name_edit)
        self.name_edit.style().polish(self.name_edit)
        self._set_actions_visible(False)
        self.clearFocus()


# ── Empty-state widget ────────────────────────────────────────────────────────

class _EmptyState(QWidget):
    """Placeholder displayed when the session has no slices."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Simple geometric placeholder using box-drawing: lighter and more
        # reliable than emoji on Windows across all font configurations.
        icon = QLabel("□")  # U+25A1 WHITE SQUARE — universally available
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"color: {PALETTE['text_disabled']}; font-size: 22pt; background: transparent;"
        )

        msg = QLabel("No slices yet.\nDraw a rectangle on the canvas\nto add one.")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        msg.setStyleSheet(
            f"color: {PALETTE['text_disabled']}; font-size: 8pt;"
            f" font-family: {_FONT}; background: transparent; line-height: 160%;"
        )

        layout.addWidget(icon)
        layout.addWidget(msg)


# ── Main sidebar widget ───────────────────────────────────────────────────────

class SlicePreviews(QWidget):
    """
    Left-panel slice list.

    Public API (consumed by main_window.py):
      • SlicePreviews(main_window)
      • .update_previews()
      • .on_item_clicked(item)
      • .list_widget       — QListWidget
      • .layout            — outer QVBoxLayout; main_window appends "Add Tile" here
    """

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._pms = PixelMaskService()

        # self.layout is intentionally an attribute, not just a local variable,
        # because main_window.py does: self.slice_previews.layout.addWidget(btn)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(40)
        header.setStyleSheet(
            f"background: transparent; border-bottom: 1px solid {PALETTE['border']};"
        )
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(14, 0, 10, 0)
        header_row.setSpacing(8)

        section_lbl = QLabel("SLICES")
        section_lbl.setStyleSheet(
            f"color: {PALETTE['text_muted']}; font-size: 8pt; font-weight: bold;"
            f" letter-spacing: 1px; background: transparent;"
            f" border-left: 2px solid {PALETTE['accent']}; padding-left: 6px;"
            f" border-bottom: none;"  # override the parent widget's border-bottom
        )
        header_row.addWidget(section_lbl)
        header_row.addStretch()

        # Count badge — pill shape; colour changes when items exist
        self._count_badge = QLabel("0")
        self._count_badge.setFixedHeight(18)
        self._count_badge.setMinimumWidth(20)
        self._count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_badge.setStyleSheet(self._badge_style(0))
        header_row.addWidget(self._count_badge)

        self.layout.addWidget(header)

        # ── List ──────────────────────────────────────────────────────────────
        self.list_widget = QListWidget()
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # 2 px gap between items — visible breathing without border lines
        self.list_widget.setSpacing(2)
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.layout.addWidget(self.list_widget, stretch=1)

    # ── Badge helper ──────────────────────────────────────────────────────────

    @staticmethod
    def _badge_style(count: int) -> str:
        p = PALETTE
        if count:
            # Active: accent-tinted blue pill to signal the panel is populated
            bg, fg = p["btn_primary"], "white"
        else:
            bg, fg = p["bg_control"], p["text_muted"]
        return (
            f"background: {bg}; color: {fg}; font-size: 7.5pt; font-weight: bold;"
            f" font-family: {_FONT}; border-radius: 9px; padding: 0 5px;"
        )

    # ── Public ────────────────────────────────────────────────────────────────

    def update_previews(self):
        self.list_widget.clear()
        s = self.mw.current_session
        count = len(s.tiles) if s else 0

        self._count_badge.setText(str(count))
        self._count_badge.setStyleSheet(self._badge_style(count))

        if not s or not s.tiles:
            self._add_empty_state()
            return

        for i, tile in enumerate(s.tiles):
            name = tile.metadata.get("name") or f"Slice {i + 1}"
            color_hex = tile.color
            tile_count = len(tile.rects)

            def make_delete(idx=i):
                return lambda: self._delete_slice(idx)

            def make_rename(idx=i):
                return lambda new_name: self._rename_slice_inline(idx, new_name)

            row = _SliceRow(
                name, tile_count, color_hex,
                on_delete=make_delete(),
                on_rename=make_rename(),
            )

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, i)
            # sizeHint height = _ROW_H; QListWidget.setSpacing(2) adds 2px above+below
            item.setSizeHint(QSize(0, _ROW_H))
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )

            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row)

    # ── Private ───────────────────────────────────────────────────────────────

    def _add_empty_state(self):
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setSizeHint(QSize(0, 100))
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, _EmptyState())

    # ── Slice actions ─────────────────────────────────────────────────────────

    def _rename_slice_inline(self, idx: int, new_name: str) -> None:
        s = self.mw.current_session
        if not s or idx >= len(s.tiles):
            return
        s.tiles[idx].metadata["name"] = new_name

    def _delete_slice(self, idx: int) -> None:
        s = self.mw.current_session
        if not s or idx >= len(s.tiles):
            return

        tr = self.mw.tile_renderer

        if tr.slice_idx == idx:
            self.mw.switch_to_canvas()
        elif tr.slice_idx is not None and tr.slice_idx > idx:
            tr._slice_idx -= 1

        if hasattr(s.tiles[idx], "clear_cache"):
            s.tiles[idx].clear_cache()

        s.tiles.pop(idx)
        self.update_previews()
        self.mw.canvas_renderer.redraw()

    def on_item_clicked(self, item):
        idx = item.data(Qt.ItemDataRole.UserRole)
        s = self.mw.current_session
        if not s or idx is None or idx >= len(s.tiles):
            return
        self.mw.switch_to_tile(idx)

    # ── Context Menu ──────────────────────────────────────────────────────────

    def _show_context_menu(self, pos) -> None:
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None:
            return

        menu = QMenu(self)
        action_nav  = menu.addAction("\U0001f50d  Focus on Canvas")
        action_edit = menu.addAction("✏️  Edit Properties")
        menu.addSeparator()
        action_del  = menu.addAction("\U0001f5d1️  Delete Slice")

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
        dialog.setWindowTitle("Edit Slice Properties")
        dialog.setMinimumWidth(350)

        form = QFormLayout(dialog)

        name_input    = QLineEdit(meta.get("name", ""))
        microns_input = QLineEdit(s.microns_per_pixel)

        desc_input = QTextEdit()
        desc_input.setPlainText(meta.get("description", ""))
        desc_input.setMaximumHeight(80)

        comment_input = QTextEdit()
        comment_input.setPlainText(meta.get("comment", ""))
        comment_input.setMaximumHeight(80)

        form.addRow("Name:", name_input)
        form.addRow("µm/px (WSI):", microns_input)
        form.addRow("Description:", desc_input)
        form.addRow("Comment:", comment_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            meta["name"]        = name_input.text().strip()
            meta["description"] = desc_input.toPlainText().strip()
            meta["comment"]     = comment_input.toPlainText().strip()
            s.set_microns_per_pixel(microns_input.text().strip())
            self.update_previews()
