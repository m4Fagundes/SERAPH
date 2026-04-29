"""
Layer visibility dropdown for the toolbar.

Displays a checkable menu of segmentation layers for the active tile.
Each layer can be toggled independently, allowing multiple segmentation
strategies (NuClick, Cellpose, Manual) to coexist without deletion.
"""
import logging
from PyQt6.QtWidgets import (
    QToolButton, QMenu, QWidgetAction, QWidget,
    QHBoxLayout, QCheckBox, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPixmap, QPainter

logger = logging.getLogger(__name__)


def _color_icon(hex_color: str, size: int = 12) -> QIcon:
    """Generate a tiny square icon filled with *hex_color*."""
    pix = QPixmap(size, size)
    pix.fill(QColor(hex_color))
    # Rounded corners
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(hex_color))
    painter.drawRoundedRect(0, 0, size, size, 3, 3)
    painter.end()
    return QIcon(pix)


class LayerDropdown(QToolButton):
    """Toolbar button that shows a popup menu with per-layer visibility toggles.

    Signals:
        layerVisibilityChanged: emitted when any layer's visibility changes.
    """
    layerVisibilityChanged = pyqtSignal()

    _BUTTON_STYLE = """
        QToolButton {
            background-color: #3c3c3c;
            color: #ffffff;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 4px 12px 4px 8px;
            font-size: 8pt;
            font-family: 'Segoe UI', Tahoma, sans-serif;
            min-width: 120px;
            text-align: left;
        }
        QToolButton:hover { border: 1px solid #007acc; background-color: #444; }
        QToolButton::menu-indicator {
            subcontrol-origin: padding;
            subcontrol-position: center right;
            right: 6px;
        }
    """

    _MENU_STYLE = """
        QMenu {
            background-color: #2d2d2d;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 4px 0;
            font-family: 'Segoe UI', Tahoma, sans-serif;
        }
        QMenu::item {
            padding: 6px 16px 6px 8px;
            color: #cccccc;
            font-size: 8pt;
        }
        QMenu::item:selected {
            background-color: #0e639c;
            color: #ffffff;
        }
        QMenu::separator {
            height: 1px;
            background-color: #444;
            margin: 4px 8px;
        }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_window = parent
        self._current_tile = None

        self.setText("Layers (0)")
        self.setToolTip("Toggle segmentation layer visibility")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setStyleSheet(self._BUTTON_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._menu = QMenu(self)
        self._menu.setStyleSheet(self._MENU_STYLE)
        self.setMenu(self._menu)

        # Actions stored for cleanup
        self._layer_actions: list = []

    # ── Public API ────────────────────────────────────────────────────────────

    def set_tile(self, tile):
        """Bind to a tile and rebuild the layer menu."""
        self._current_tile = tile
        self._rebuild_menu()

    def clear(self):
        """Unbind and show empty state."""
        self._current_tile = None
        self._menu.clear()
        self._layer_actions.clear()
        self.setText("Layers (0)")

    def refresh(self):
        """Rebuild menu from current tile (call after layers change)."""
        self._rebuild_menu()

    # ── Menu builder ──────────────────────────────────────────────────────────

    def _delete_layer(self, idx: int):
        if not self._current_tile:
            return
        if idx < len(self._current_tile.segmentation_layers):
            del self._current_tile.segmentation_layers[idx]
            self._rebuild_menu()
            self.layerVisibilityChanged.emit()

    def _rebuild_menu(self):
        """Reconstruct the popup menu from the tile's segmentation_layers."""
        self._menu.clear()
        self._layer_actions.clear()

        tile = self._current_tile
        if not tile:
            self.setText("Layers (0)")
            return

        layers = tile.segmentation_layers
        visible_count = sum(1 for l in layers if l.get("visible", True))
        self.setText(f"Layers ({visible_count}/{len(layers)})")

        if not layers:
            no_layers = self._menu.addAction("No layers yet")
            no_layers.setEnabled(False)
            return

        # ── Per-layer checkable actions ───────────────────────────────────────
        for i, layer in enumerate(layers):
            name = layer.get("name", f"Layer {i+1}")
            poly_count = len(layer.get("polygons", []))
            is_visible = layer.get("visible", True)
            color_hex = layer.get("color", "#FFFF00")

            action = QWidgetAction(self._menu)
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(8, 2, 8, 2)
            row_layout.setSpacing(8)

            chk_visible = QCheckBox(f"  {name}  ({poly_count})")
            chk_visible.setIcon(_color_icon(color_hex))
            chk_visible.setChecked(is_visible)
            chk_visible.setStyleSheet("""
                QCheckBox { color: #cccccc; font-size: 8pt; font-family: 'Segoe UI', Tahoma, sans-serif; }
                QCheckBox::indicator { width: 14px; height: 14px; background-color: #3c3c3c; border: 1px solid #555; border-radius: 3px; }
                QCheckBox::indicator:checked { background-color: #0e639c; border: 1px solid #0e639c; }
            """)

            # Capture index by value
            def make_handler(idx=i):
                def handler(checked):
                    if self._current_tile and idx < len(self._current_tile.segmentation_layers):
                        self._current_tile.segmentation_layers[idx]["visible"] = checked
                        self._update_label()
                        self.layerVisibilityChanged.emit()
                return handler

            chk_visible.toggled.connect(make_handler())
            
            btn_delete = QToolButton()
            btn_delete.setText("🗑️")
            btn_delete.setToolTip("Apagar esta segmentação")
            btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_delete.setStyleSheet("""
                QToolButton { border: none; background: transparent; font-size: 10pt; }
                QToolButton:hover { background-color: #c0392b; border-radius: 3px; }
            """)
            
            def make_delete_handler(idx=i):
                def handler():
                    self._delete_layer(idx)
                return handler
                
            btn_delete.clicked.connect(make_delete_handler())

            row_layout.addWidget(chk_visible)
            row_layout.addStretch()
            row_layout.addWidget(btn_delete)
            
            action.setDefaultWidget(row_widget)
            self._menu.addAction(action)
            self._layer_actions.append(action)

        # ── Separator + bulk actions ──────────────────────────────────────────
        self._menu.addSeparator()

        show_all = self._menu.addAction("👁  Show All")
        show_all.triggered.connect(lambda: self._set_all(True))

        hide_all = self._menu.addAction("🚫  Hide All")
        hide_all.triggered.connect(lambda: self._set_all(False))

    def _update_label(self):
        """Update button text to reflect current visibility state."""
        tile = self._current_tile
        if not tile:
            self.setText("Layers (0)")
            return
        layers = tile.segmentation_layers
        visible = sum(1 for l in layers if l.get("visible", True))
        self.setText(f"Layers ({visible}/{len(layers)})")

    def _set_all(self, visible: bool):
        """Show or hide all layers at once."""
        if not self._current_tile:
            return
        for layer in self._current_tile.segmentation_layers:
            layer["visible"] = visible
        self._rebuild_menu()
        self.layerVisibilityChanged.emit()
