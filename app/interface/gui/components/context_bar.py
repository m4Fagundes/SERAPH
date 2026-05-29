"""
Context bar for the editor workbench.

Image tabs represent open images. This bar represents the current context
inside the active image: overview or a selected slice.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from app.interface.gui.design_system import COLORS, SPACE


class ContextBar(QWidget):
    """Compact hierarchy bar below image tabs."""

    # Emitted when the user clicks the µm/px badge to edit the resolution.
    mpp_edit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("context_bar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.mode_label = QLabel("", self)
        self.mode_label.setObjectName("context_mode")
        self.mode_label.hide()

        self.meta_label = QLabel("", self)
        self.meta_label.setObjectName("context_meta")
        self.meta_label.hide()

        # WSI-level scale badge. It lives next to the image name because the
        # resolution belongs to the whole slide image, not to an individual slice.
        self._mpp_btn = QPushButton("", self)
        self._mpp_btn.setObjectName("context_mpp_btn")
        self._mpp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mpp_btn.setFlat(True)
        self._mpp_btn.setFixedHeight(28)
        self._mpp_btn.clicked.connect(self.mpp_edit_requested)
        self._mpp_btn.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE[3], 0, SPACE[3], 0)
        layout.setSpacing(SPACE[2])
        layout.addWidget(self.mode_label)
        layout.addWidget(self.meta_label)
        layout.addStretch(1)

        self._actions_layout = QHBoxLayout()
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(SPACE[2])
        self._actions_layout.addWidget(self._mpp_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(self._actions_layout)

        self.setStyleSheet(self._style())

    def add_action_widget(self, widget: QWidget) -> None:
        self._actions_layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def refresh_mpp(self, session) -> None:
        """Update the µm/px badge text and colour from the session value."""
        if session is None:
            self._mpp_btn.setVisible(False)
            return

        mpp_raw = getattr(session, "microns_per_pixel", "") or ""
        try:
            v = float(mpp_raw)
            if v <= 0:
                raise ValueError
            self._mpp_btn.setText(f"WSI: {v:g} µm/px")
            self._mpp_btn.setStyleSheet(self._mpp_style_set())
        except (ValueError, TypeError):
            self._mpp_btn.setText("Set WSI scale")
            self._mpp_btn.setStyleSheet(self._mpp_style_unset())

        self._mpp_btn.setVisible(True)

    def set_overview(self, session, slice_count: int = 0) -> None:
        if session is None:
            self.mode_label.setText("")
            self.mode_label.hide()
            self.meta_label.setText("")
            self.meta_label.hide()
            self.refresh_mpp(None)
            return

        self.mode_label.setText("")
        self.mode_label.hide()
        self.meta_label.setText("")
        self.meta_label.hide()
        self.refresh_mpp(session)

    def set_slice(self, session, slice_label: str, nuclei_count: int | None = None) -> None:
        self.mode_label.setText("")
        self.mode_label.hide()
        self.meta_label.setText("")
        self.meta_label.hide()
        self.refresh_mpp(None)

    def _mpp_style_set(self) -> str:
        p = COLORS
        return f"""
        QPushButton#context_mpp_btn {{
            color: {p['text_secondary']};
            font-size: 11px;
            background: {p['bg_control']};
            border: 1px solid {p['border_default']};
            border-radius: 4px;
            padding: 0px 10px;
        }}
        QPushButton#context_mpp_btn:hover {{
            color: {p['text_primary']};
            background: {p['bg_hover']};
            border-color: {p['border_strong']};
        }}
        """

    def _mpp_style_unset(self) -> str:
        return """
        QPushButton#context_mpp_btn {
            color: #e8a844;
            font-size: 11px;
            background: rgba(245,159,0,0.10);
            border: 1px solid rgba(245,159,0,0.55);
            border-radius: 4px;
            padding: 0px 10px;
        }
        QPushButton#context_mpp_btn:hover {
            color: #f0c070;
            background: rgba(232,168,68,0.10);
            border-color: #f0c070;
        }
        """

    def _style(self) -> str:
        p = COLORS
        return f"""
        QWidget#context_bar {{
            min-height: 40px;
            max-height: 40px;
            background: {p['bg_base']};
            border-bottom: 1px solid {p['border_default']};
        }}
        QLabel#context_mode {{
            color: {p['text_primary']};
            font-size: 12px;
            font-weight: 600;
            background: transparent;
        }}
        QLabel#context_meta {{
            color: {p['text_secondary']};
            font-size: 11px;
            background: {p['bg_control']};
            border: 1px solid {p['border_default']};
            border-radius: 4px;
            padding: 3px 8px;
        }}
        """
