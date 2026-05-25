"""
Context bar for the editor workbench.

Image tabs represent open images. This bar represents the current context
inside the active image: overview or a selected slice.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.interface.gui.design_system import COLORS, SPACE


class ContextBar(QWidget):
    """Compact hierarchy bar below image tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("context_bar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.mode_label = QLabel("Overview", self)
        self.mode_label.setObjectName("context_mode")

        self.image_label = QLabel("No image open", self)
        self.image_label.setObjectName("context_image")
        self.image_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.meta_label = QLabel("", self)
        self.meta_label.setObjectName("context_meta")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE[3], 0, SPACE[3], 0)
        layout.setSpacing(SPACE[2])
        layout.addWidget(self.mode_label)
        layout.addWidget(self._separator())
        layout.addWidget(self.image_label, stretch=1)
        layout.addWidget(self.meta_label)

        self._actions_layout = QHBoxLayout()
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(SPACE[2])
        layout.addLayout(self._actions_layout)

        self.setStyleSheet(self._style())

    def add_action_widget(self, widget: QWidget) -> None:
        self._actions_layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_overview(self, session, slice_count: int = 0) -> None:
        if session is None:
            self.mode_label.setText("Overview")
            self.image_label.setText("No image open")
            self.image_label.setToolTip("")
            self.meta_label.setText("")
            return

        self.mode_label.setText("Overview")
        self.image_label.setText(session.name)
        self.image_label.setToolTip(session.path)
        self.meta_label.setText(
            f"{slice_count} slice{'s' if slice_count != 1 else ''}"
        )

    def set_slice(self, session, slice_label: str, nuclei_count: int | None = None) -> None:
        self.mode_label.setText(slice_label)
        if session is None:
            self.image_label.setText("No image open")
            self.image_label.setToolTip("")
        else:
            self.image_label.setText(session.name)
            self.image_label.setToolTip(session.path)
        self.meta_label.setText(
            f"{nuclei_count:,} nuclei" if nuclei_count is not None else "Tile view"
        )

    def _separator(self) -> QLabel:
        sep = QLabel("/", self)
        sep.setObjectName("context_separator")
        return sep

    def _style(self) -> str:
        p = COLORS
        return f"""
        QWidget#context_bar {{
            min-height: 32px;
            max-height: 32px;
            background: {p['bg_surface']};
            border-bottom: 1px solid {p['border_default']};
        }}
        QLabel#context_mode {{
            color: {p['text_primary']};
            font-size: 12px;
            font-weight: 600;
            background: transparent;
        }}
        QLabel#context_image,
        QLabel#context_meta,
        QLabel#context_separator {{
            color: {p['text_muted']};
            font-size: 11px;
            background: transparent;
        }}
        """
