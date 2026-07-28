"""
Welcome page for SERAPH.

Shown when no image/project is open. It gives users a calm starting point
without competing with the technical workbench once data is loaded.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.interface.gui.design_system import COLORS, FONT_FAMILY, SPACE
from app.interface.gui.theme import create_seraph_icon
from app.interface.gui.theme_manager import theme_manager, themed
from app.interface.gui.widgets.buttons import PrimaryButton, SecondaryButton


class WelcomePage(QWidget):
    """Centered start screen with primary project/image actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("welcome_page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(48, 40, 48, 48)
        root.setSpacing(0)
        root.addStretch(1)

        panel = QWidget(self)
        panel.setObjectName("welcome_content")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(SPACE[4])

        self._logo = QLabel()
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh_logo()
        # The mark's body is filled with the page background, so it has to be
        # re-rendered when the theme flips — a pixmap can't follow the QSS.
        theme_manager.theme_changed.connect(self._refresh_logo)
        panel_layout.addWidget(self._logo, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("SERAPH")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("welcome_title")
        panel_layout.addWidget(title)

        subtitle = QLabel("Segmentation Engine for Research in Anatomical Pathology and Histology")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setObjectName("welcome_subtitle")
        panel_layout.addWidget(subtitle)

        actions_box = QWidget()
        actions_box.setFixedSize(360, 100)
        actions = QVBoxLayout(actions_box)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(0)

        self.btn_open_project = PrimaryButton("Load Project", size="lg")
        self.btn_open_project.setObjectName("welcome_primary_action")
        self.btn_open_project.setIcon(QIcon.fromTheme("document-open"))
        self.btn_open_project.setFixedSize(360, 44)
        self.btn_open_project.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_open_project.setToolTip("Open an existing SERAPH .lab project")

        self.btn_open_image = SecondaryButton("Open Image", size="lg")
        self.btn_open_image.setObjectName("welcome_secondary_action")
        self.btn_open_image.setFixedSize(360, 44)
        self.btn_open_image.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_open_image.setToolTip("Start from a whole-slide image or microscopy image")

        actions.addWidget(self.btn_open_project)
        button_gap = QWidget()
        button_gap.setFixedHeight(SPACE[3])
        actions.addWidget(button_gap)
        actions.addWidget(self.btn_open_image)
        panel_layout.addWidget(actions_box, 0, Qt.AlignmentFlag.AlignHCenter)

        hint = QLabel("Open a project to continue previous work, or open an image to start a new analysis workspace.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        hint.setObjectName("welcome_hint")
        panel_layout.addWidget(hint)

        root.addWidget(panel, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(2)
        themed(self, self._style)

    def _refresh_logo(self) -> None:
        self._logo.setPixmap(create_seraph_icon(72, bg=COLORS["bg_canvas"]))

    def _style(self) -> str:
        return f"""
        QWidget#welcome_page {{
            background: {COLORS['bg_canvas']};
            font-family: {FONT_FAMILY};
        }}
        QWidget#welcome_content {{
            background: transparent;
            max-width: 620px;
        }}
        QLabel#welcome_title {{
            color: {COLORS['text_primary']};
            font-size: 28px;
            font-weight: 700;
            letter-spacing: 0px;
            background: transparent;
        }}
        QLabel#welcome_subtitle {{
            color: {COLORS['text_muted']};
            font-size: 13px;
            background: transparent;
        }}
        QLabel#welcome_hint {{
            color: {COLORS['text_disabled']};
            font-size: 11px;
            background: transparent;
            padding-top: {SPACE[3]}px;
        }}
        QPushButton#welcome_primary_action {{
            background: {COLORS['accent_primary']};
            color: {COLORS['text_on_accent']};
            border: 1px solid {COLORS['accent_primary']};
            border-radius: 6px;
            padding: 0 16px;
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton#welcome_primary_action:hover {{
            background: {COLORS['accent_primary_hover']};
            border-color: {COLORS['accent_primary_hover']};
        }}
        QPushButton#welcome_primary_action:pressed {{
            background: {COLORS['accent_primary_press']};
            border-color: {COLORS['accent_primary_press']};
        }}
        QPushButton#welcome_secondary_action {{
            background: transparent;
            color: {COLORS['text_primary']};
            border: 1px solid {COLORS['border_default']};
            border-radius: 6px;
            padding: 0 16px;
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton#welcome_secondary_action:hover {{
            background: {COLORS['bg_hover']};
            border-color: {COLORS['border_strong']};
        }}
        QPushButton#welcome_secondary_action:pressed {{
            background: {COLORS['bg_elevated']};
        }}
        """
