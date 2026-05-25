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
  appends footer actions via self.slice_previews.add_footer_widget().
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
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from app.application.pixel_mask_service import PixelMaskService
from app.interface.gui.theme import PALETTE
from app.interface.gui.design_system import COLORS, SPACE, FONT_FAMILY
from app.interface.gui.widgets.section_header import SectionHeader
from app.interface.gui.widgets.buttons import PrimaryButton

logger = logging.getLogger(__name__)

_FONT = FONT_FAMILY
_ROW_H = 44  # px — compact single-line row


def _btn_edit_style() -> str:
    p = COLORS
    return (
        f"QPushButton {{ background: transparent; color: {p['text_muted']};"
        f" border: 1px solid transparent; border-radius: 4px;"
        f" padding: 0; margin: 0; font-size: 11px; font-weight: 600; }}"
        f"QPushButton:hover {{ background: {p['bg_hover']}; color: {p['text_primary']};"
        f" border-color: {p['border_default']}; }}"
        f"QPushButton:pressed {{ background: {p['bg_control']}; }}"
    )


def _btn_delete_style() -> str:
    p = COLORS
    # Destructive action: neutral by default, red only on hover
    return (
        f"QPushButton {{ background: transparent; color: {p['accent_danger']};"
        f" border: 1px solid transparent; border-radius: 4px;"
        f" padding: 0; margin: 0; font-size: 11px; font-weight: 600; }}"
        f"QPushButton:hover {{ background: {p['accent_danger']}; color: white; }}"
        f"QPushButton:pressed {{ background: {p['accent_danger_press']}; color: white; }}"
    )


# ── Row widget ────────────────────────────────────────────────────────────────

class _SliceRow(QWidget):
    """
    One row in the slice sidebar list.

    Visual structure (left → right):
      [swatch] [slice name] [edit] [delete]

    Action buttons are always visible for discoverability.
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
        self._selected = False

        self.setFixedHeight(_ROW_H)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._refresh_style()

        root = QHBoxLayout(self)
        root.setContentsMargins(SPACE[2], 0, SPACE[2], 0)
        root.setSpacing(SPACE[2])

        # ── Colour swatch ─────────────────────────────────────────────────────
        swatch = QLabel()
        swatch.setFixedSize(9, 9)
        swatch.setStyleSheet(
            f"background-color: {color_hex}; border-radius: 3px;"
            f" border: 1px solid rgba(255,255,255,0.15);"
        )
        root.addWidget(swatch, 0, Qt.AlignmentFlag.AlignVCenter)

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
            f" background: transparent; color: {COLORS['text_primary']};"
            f" border: none; font-weight: 600; font-size: 12px;"
            f" font-family: {_FONT}; padding: 0; margin: 0; min-height: 20px;"
            f" max-height: 20px; }}"
            f' QLineEdit[readOnly="false"] {{'
            f" background: {COLORS['bg_surface']}; color: {COLORS['text_primary']};"
            f" border: 1px solid {COLORS['border_strong']}; border-radius: 3px;"
            f" padding: 1px 4px; font-size: 12px; font-family: {_FONT}; }}"
        )
        self.name_edit.editingFinished.connect(self._finish_edit)
        root.addWidget(self.name_edit, stretch=1, alignment=Qt.AlignmentFlag.AlignVCenter)

        # ── Action buttons ───────────────────────────────────────────────────
        self._edit_btn = QPushButton("✎")
        self._edit_btn.setFixedSize(20, 20)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setToolTip("Rename slice  (double-click also works)")
        self._edit_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._edit_btn.setFlat(True)
        self._edit_btn.setStyleSheet(_btn_edit_style())
        self._edit_btn.clicked.connect(self._start_edit)

        self._del_btn = QPushButton("×")
        self._del_btn.setFixedSize(20, 20)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setToolTip("Delete slice")
        self._del_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._del_btn.setFlat(True)
        self._del_btn.setStyleSheet(_btn_delete_style())
        self._del_btn.clicked.connect(on_delete)

        root.addWidget(self._edit_btn)
        root.addWidget(self._del_btn)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._refresh_style()

    def _refresh_style(self) -> None:
        if self._selected:
            self.setStyleSheet(
                f"background: rgba(34, 211, 238, 0.12);"
                f" border: 1px solid {COLORS['brand']};"
                f" border-radius: 5px;"
            )
        else:
            self.setStyleSheet(
                f"background: {COLORS['bg_elevated']};"
                f" border: 1px solid {COLORS['border_default']};"
                f" border-radius: 5px;"
            )

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
        self.clearFocus()


# ── Empty-state widget ────────────────────────────────────────────────────────

class _EmptyState(QWidget):
    """Placeholder displayed when the session has no slices."""

    def __init__(self, mode: str, on_open_image=None):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 18, 16, 18)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Simple geometric placeholder using box-drawing: lighter and more
        # reliable than emoji on Windows across all font configurations.
        icon = QLabel("□")  # U+25A1 WHITE SQUARE — universally available
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"color: {PALETTE['text_disabled']}; font-size: 22pt; background: transparent;"
        )

        if mode == "no_image":
            msg_text = "No image open.\nOpen an image to start."
        else:
            msg_text = "No slices yet.\nDraw a region or import a tile."

        msg = QLabel(msg_text)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        msg.setStyleSheet(
            f"color: {PALETTE['text_disabled']}; font-size: 8pt;"
            f" font-family: {_FONT}; background: transparent; line-height: 160%;"
        )

        layout.addWidget(icon)
        layout.addWidget(msg)

        if mode == "no_image" and on_open_image is not None:
            btn = PrimaryButton("Open Image", size="sm")
            btn.clicked.connect(on_open_image)
            layout.addWidget(btn)


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

    countChanged = pyqtSignal(int)

    def __init__(self, main_window, show_header: bool = True):
        super().__init__()
        self.mw = main_window
        self._pms = PixelMaskService()

        # self.layout is intentionally an attribute, not just a local variable,
        # because older integrations may still append widgets to it.
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        # SectionHeader exposes set_badge(value, active) — used in update_previews()
        if show_header:
            self._section_header = SectionHeader("Slices", badge="0")
            # Alias for backward-compat in case something references _count_badge directly
            self._count_badge = self._section_header._badge
            self.layout.addWidget(self._section_header)
        else:
            self._section_header = None
            self._count_badge = None

        # ── List ──────────────────────────────────────────────────────────────
        self.list_widget = QListWidget()
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # 2 px gap between items — visible breathing without border lines
        self.list_widget.setSpacing(2)
        self.list_widget.setContentsMargins(SPACE[3], SPACE[3], SPACE[3], SPACE[3])
        self.list_widget.setStyleSheet(
            f"QListWidget {{ background: transparent; border: none;"
            f" padding: {SPACE[3]}px; }}"
            f"QListWidget::item {{ background: transparent; border: none;"
            f" padding: 0; margin: 0 0 {SPACE[2]}px 0; }}"
            f"QListWidget::item:selected {{ background: transparent; border: none; }}"
            f"QListWidget::item:hover {{ background: transparent; border: none; }}"
        )
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        self.list_widget.itemSelectionChanged.connect(self._sync_row_selection)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.layout.addWidget(self.list_widget, stretch=1)

        self._footer = QWidget()
        self._footer.setObjectName("slice_footer")
        self._footer_layout = QVBoxLayout(self._footer)
        self._footer_layout.setContentsMargins(SPACE[3], SPACE[3], SPACE[3], SPACE[3])
        self._footer_layout.setSpacing(SPACE[2])
        self.layout.addWidget(self._footer)

        self._footer.setStyleSheet(
            f"QWidget#slice_footer {{ background: {COLORS['bg_surface']};"
            f" border-top: 1px solid {COLORS['border_default']}; }}"
        )

    def add_footer_widget(self, widget: QWidget) -> None:
        self._footer_layout.addWidget(widget)

    # ── Public ────────────────────────────────────────────────────────────────

    def update_previews(self):
        self.list_widget.clear()
        s = self.mw.current_session
        count = len(s.tiles) if s else 0
        self.countChanged.emit(count)

        if self._section_header is not None:
            self._section_header.set_badge(str(count), active=count > 0)

        if not s:
            self._add_empty_state("no_image")
            return

        if not s.tiles:
            self._add_empty_state("no_slices")
            return

        for i, tile in enumerate(s.tiles):
            name = tile.metadata.get("name") or f"Slice {i + 1}"
            color_hex = tile.color

            def make_delete(idx=i):
                return lambda: self._delete_slice(idx)

            def make_rename(idx=i):
                return lambda new_name: self._rename_slice_inline(idx, new_name)

            row = _SliceRow(
                name, len(tile.rects), color_hex,
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

        self._sync_row_selection()

    def select_slice(self, idx: int | None) -> None:
        self.list_widget.blockSignals(True)
        if idx is None or idx < 0 or idx >= self.list_widget.count():
            self.list_widget.clearSelection()
            self.list_widget.setCurrentRow(-1)
        else:
            self.list_widget.setCurrentRow(idx)
        self.list_widget.blockSignals(False)
        self._sync_row_selection()

    # ── Private ───────────────────────────────────────────────────────────────

    def _add_empty_state(self, mode: str):
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        height = 170 if mode == "no_image" else 140
        item.setSizeHint(QSize(0, height))
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(
            item,
            _EmptyState(mode, on_open_image=self.mw.project_manager.add_image)
        )

    def _sync_row_selection(self) -> None:
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            row = self.list_widget.itemWidget(item)
            if hasattr(row, "set_selected"):
                row.set_selected(item.isSelected())

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
