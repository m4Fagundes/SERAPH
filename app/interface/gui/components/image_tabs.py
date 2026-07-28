"""
Browser-style image tabs for SERAPH.

This component owns the visual tab strip and the quick-add button. MainWindow
keeps the session lifecycle; the tab strip only emits intent signals.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTabBar, QWidget

from app.interface.gui.design_system import COLORS, SPACE
from app.interface.gui.theme_manager import themed


class ImageTabStrip(QWidget):
    """VS Code-like strip for open image sessions."""

    currentChanged = pyqtSignal(int)
    tabClicked = pyqtSignal(int)
    closeRequested = pyqtSignal(int)
    addRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("image_tab_strip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.tab_bar = QTabBar(self)
        self.tab_bar.setObjectName("image_tabs_bar")
        self.tab_bar.setTabsClosable(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setUsesScrollButtons(True)
        self.tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        self.tab_bar.setFixedHeight(36)
        self.tab_bar.currentChanged.connect(self.currentChanged)
        self.tab_bar.tabBarClicked.connect(self.tabClicked)
        self.tab_bar.hide()

        self.add_button = QPushButton("+", self)
        self.add_button.setObjectName("image_tab_add")
        self.add_button.setFixedSize(26, 26)
        self.add_button.setToolTip("Add image to project")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(self.addRequested)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE[2], 0, SPACE[2], 0)
        layout.setSpacing(SPACE[1])
        layout.addWidget(self.tab_bar)
        layout.addWidget(self.add_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch()

        self._trailing_layout = QHBoxLayout()
        self._trailing_layout.setContentsMargins(0, 0, 0, 0)
        self._trailing_layout.setSpacing(SPACE[2])
        layout.addLayout(self._trailing_layout)

        themed(self, self._style)

    def add_trailing_widget(self, widget: QWidget) -> None:
        self._trailing_layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def add_session_tab(self, title: str, tooltip: str | None = None) -> int:
        self.tab_bar.show()
        index = self.tab_bar.addTab(title)
        self.tab_bar.setTabToolTip(index, tooltip or title)

        close_cell = QWidget(self.tab_bar)
        close_cell.setObjectName("image_tab_close_cell")
        close_cell.setFixedSize(24, 22)
        close_layout = QHBoxLayout(close_cell)
        close_layout.setContentsMargins(3, 2, 5, 2)
        close_layout.setSpacing(0)

        close_button = QPushButton("×", close_cell)
        close_button.setObjectName("image_tab_close")
        close_button.setFixedSize(16, 16)
        close_button.setToolTip("Close image")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_button.setFlat(True)
        themed(close_button, self._close_button_style)
        close_button.clicked.connect(self._emit_close_for_sender)
        close_layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignCenter)

        self.tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, close_cell)
        return index

    def remove_tab(self, index: int) -> None:
        self.tab_bar.removeTab(index)
        if self.tab_bar.count() == 0:
            self.tab_bar.hide()

    def clear_tabs(self) -> None:
        self.tab_bar.blockSignals(True)
        while self.tab_bar.count() > 0:
            self.tab_bar.removeTab(0)
        self.tab_bar.blockSignals(False)
        self.tab_bar.hide()

    def set_current_index(self, index: int) -> None:
        self.tab_bar.setCurrentIndex(index)

    def count(self) -> int:
        return self.tab_bar.count()

    def _emit_close_for_sender(self) -> None:
        sender = self.sender()
        for index in range(self.tab_bar.count()):
            close_cell = self.tab_bar.tabButton(index, QTabBar.ButtonPosition.RightSide)
            if close_cell is sender or sender in close_cell.findChildren(QPushButton):
                self.closeRequested.emit(index)
                return

    def _close_button_style(self) -> str:
        p = COLORS
        return f"""
        QPushButton#image_tab_close {{
            background: transparent;
            color: {p['text_muted']};
            border: none;
            border-radius: 3px;
            padding: 0;
            margin: 0;
            font-size: 13px;
            font-weight: 500;
            line-height: 16px;
        }}
        QPushButton#image_tab_close:hover {{
            background: {p['bg_hover']};
            color: {p['text_primary']};
        }}
        QPushButton#image_tab_close:pressed {{
            background: {p['accent_danger']};
            color: white;
        }}
        """

    def _style(self) -> str:
        p = COLORS
        return f"""
        QWidget#image_tab_strip {{
            min-height: 36px;
            max-height: 36px;
            background: {p['bg_elevated']};
            border-bottom: 1px solid {p['border_default']};
        }}
        QTabBar#image_tabs_bar {{
            background: transparent;
            border: none;
        }}
        QTabBar#image_tabs_bar::tab {{
            min-width: 96px;
            max-width: 220px;
            height: 35px;
            margin: 0 1px 0 0;
            padding: 0 4px 0 14px;
            background: {p['bg_elevated']};
            color: {p['text_secondary']};
            border: none;
            border-right: 1px solid {p['border_default']};
            border-top: 1px solid transparent;
        }}
        QTabBar#image_tabs_bar::tab:selected {{
            background: {p['bg_canvas']};
            color: {p['text_primary']};
            border-top: 2px solid {p['brand']};
            border-right: 1px solid {p['border_default']};
        }}
        QTabBar#image_tabs_bar::tab:hover:!selected {{
            background: {p['bg_elevated']};
            color: {p['text_primary']};
        }}
        QPushButton#image_tab_add {{
            background: transparent;
            color: {p['text_muted']};
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 0;
            font-size: 18px;
            font-weight: 400;
        }}
        QPushButton#image_tab_add:hover {{
            background: {p['bg_hover']};
            color: {p['text_primary']};
            border: 1px solid {p['border_default']};
        }}
        QPushButton#image_tab_add:pressed {{
            background: {p['bg_elevated']};
        }}
        """
