"""
Collapsible sidebar shell for SERAPH workbench panels.

The shell provides a compact VS Code-like rail when collapsed while keeping the
wrapped panel responsible for its own domain-specific content.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from app.interface.gui.design_system import COLORS, SPACE
from app.interface.gui.theme_manager import themed


class CollapsibleSidebar(QWidget):
    """A panel wrapper with an expanded header and a compact collapsed rail."""

    collapsedChanged = pyqtSignal(bool)

    def __init__(self, title: str, content: QWidget, parent=None):
        super().__init__(parent)
        self._title = title
        self._content = content
        self._collapsed = False
        self.setObjectName("CollapsibleSidebar")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Build header
        self.header = QWidget(self)
        self.header.setObjectName("sidebar_header")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.mousePressEvent = lambda event: self.toggle_collapsed()  # type: ignore

        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(SPACE[2], 0, SPACE[3], 0)
        header_layout.setSpacing(SPACE[1])

        self.collapse_btn = QPushButton("▼", self.header)
        self.collapse_btn.setObjectName("sidebar_icon_button")
        self.collapse_btn.setToolTip("Collapse section")
        self.collapse_btn.setFixedSize(20, 20)
        self.collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse_btn.clicked.connect(self.toggle_collapsed)
        header_layout.addWidget(self.collapse_btn)

        title_lbl = QLabel(self._title.upper(), self.header)
        title_lbl.setObjectName("sidebar_title")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        layout.addWidget(self.header)
        layout.addWidget(self._content, stretch=1)

        themed(self, self._style)

    def set_badge_count(self, count: int) -> None:
        return

    def is_collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if self._collapsed == collapsed:
            return
        self._collapsed = collapsed
        
        self._content.setVisible(not collapsed)
        self.collapse_btn.setText("▶" if collapsed else "▼")
        self.collapsedChanged.emit(collapsed)

    def _style(self) -> str:
        p = COLORS
        return f"""
        QWidget#CollapsibleSidebar {{
            background: {p['bg_surface']};
        }}
        QWidget#sidebar_header {{
            min-height: 36px;
            max-height: 36px;
            background: {p['bg_surface']};
            border-bottom: 1px solid {p['border_default']};
        }}
        QLabel#sidebar_title {{
            color: {p['text_primary']};
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.5px;
            border: none;
            padding-left: 2px;
        }}
        QPushButton#sidebar_icon_button {{
            background: transparent;
            color: {p['text_muted']};
            border: 1px solid transparent;
            border-radius: 4px;
            font-size: 11px;
            padding: 0;
        }}
        QPushButton#sidebar_icon_button:hover {{
            background: {p['bg_hover']};
            color: {p['text_primary']};
            border-color: {p['border_default']};
        }}
        """
