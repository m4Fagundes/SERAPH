"""
Collapsible sidebar shell for SERAPH workbench panels.

The shell provides a compact VS Code-like rail when collapsed while keeping the
wrapped panel responsible for its own domain-specific content.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from app.interface.gui.design_system import COLORS, SPACE


class CollapsibleSidebar(QWidget):
    """A panel wrapper with an expanded header and a compact collapsed rail."""

    collapsedChanged = pyqtSignal(bool)

    def __init__(self, title: str, content: QWidget, parent=None):
        super().__init__(parent)
        self._title = title
        self._content = content
        self._collapsed = False

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_expanded_page())
        self._stack.addWidget(self._build_collapsed_page())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._stack)

        self.setStyleSheet(self._style())

    def set_badge_count(self, count: int) -> None:
        self._badge.setText(str(count))
        active = count > 0
        self._badge.setProperty("active", active)
        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if self._collapsed == collapsed:
            return
        self._collapsed = collapsed
        self._stack.setCurrentIndex(1 if collapsed else 0)
        self.collapsedChanged.emit(collapsed)

    def _build_expanded_page(self) -> QWidget:
        page = QWidget(self)
        page.setObjectName("sidebar_expanded")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget(page)
        header.setObjectName("sidebar_header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(SPACE[3], 0, SPACE[2], 0)
        header_layout.setSpacing(SPACE[2])

        title = QLabel(self._title.upper(), header)
        title.setObjectName("sidebar_title")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self._badge = QLabel("0", header)
        self._badge.setObjectName("sidebar_badge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedHeight(18)
        self._badge.setMinimumWidth(20)
        header_layout.addWidget(self._badge)

        collapse_btn = QPushButton("‹", header)
        collapse_btn.setObjectName("sidebar_icon_button")
        collapse_btn.setToolTip("Collapse sidebar")
        collapse_btn.setFixedSize(26, 26)
        collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        collapse_btn.clicked.connect(self.toggle_collapsed)
        header_layout.addWidget(collapse_btn)

        layout.addWidget(header)
        layout.addWidget(self._content, stretch=1)
        return page

    def _build_collapsed_page(self) -> QWidget:
        page = QWidget(self)
        page.setObjectName("sidebar_collapsed")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, SPACE[2], 0, SPACE[2])
        layout.setSpacing(SPACE[2])

        expand_btn = QPushButton("›", page)
        expand_btn.setObjectName("sidebar_icon_button")
        expand_btn.setToolTip("Expand sidebar")
        expand_btn.setFixedSize(30, 30)
        expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        expand_btn.clicked.connect(self.toggle_collapsed)

        label = QLabel(self._title[:1].upper(), page)
        label.setObjectName("sidebar_rail_label")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(expand_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(label)
        layout.addStretch()
        return page

    def _style(self) -> str:
        p = COLORS
        return f"""
        QWidget#sidebar_expanded,
        QWidget#sidebar_collapsed {{
            background: {p['bg_surface']};
        }}
        QWidget#sidebar_header {{
            min-height: 36px;
            max-height: 36px;
            background: {p['bg_surface']};
            border-bottom: 1px solid {p['border_default']};
        }}
        QLabel#sidebar_title {{
            color: {p['text_muted']};
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.5px;
            border-left: 2px solid {p['brand']};
            padding-left: 6px;
        }}
        QLabel#sidebar_badge {{
            background: {p['bg_control']};
            color: {p['text_muted']};
            border-radius: 9px;
            font-size: 10px;
            font-weight: 700;
            padding: 0 5px;
        }}
        QLabel#sidebar_badge[active="true"] {{
            background: {p['accent_primary']};
            color: white;
        }}
        QPushButton#sidebar_icon_button {{
            background: transparent;
            color: {p['text_muted']};
            border: 1px solid transparent;
            border-radius: 4px;
            font-size: 14px;
            padding: 0;
        }}
        QPushButton#sidebar_icon_button:hover {{
            background: {p['bg_hover']};
            color: {p['text_primary']};
            border-color: {p['border_default']};
        }}
        QLabel#sidebar_rail_label {{
            color: {p['text_muted']};
            font-size: 11px;
            font-weight: 700;
        }}
        """
