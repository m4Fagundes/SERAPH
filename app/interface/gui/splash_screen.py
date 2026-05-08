from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


class SeraphSplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(560, 310)
        self._center_on_screen()
        self._setup_ui()

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2,
        )

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QWidget()
        container.setObjectName("splash_container")
        container.setStyleSheet("""
            QWidget#splash_container {
                background-color: #0d1117;
                border: 1px solid #1e4060;
                border-radius: 14px;
            }
        """)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(52, 38, 52, 26)
        layout.setSpacing(0)

        title = QLabel("SERAPH")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(54)
        font.setWeight(QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 12)
        title.setFont(font)
        title.setStyleSheet("color: #4FC3F7; background: transparent;")

        divider = QLabel()
        divider.setFixedHeight(1)
        divider.setStyleSheet(
            "background-color: #1e4060; border: none;"
            "margin-left: 30px; margin-right: 30px;"
        )

        acronym_html = (
            '<span style="color:#4FC3F7;font-weight:700">S</span>egmentation&nbsp;'
            '<span style="color:#4FC3F7;font-weight:700">E</span>ngine for&nbsp;'
            '<span style="color:#4FC3F7;font-weight:700">R</span>esearch in&nbsp;'
            '<span style="color:#4FC3F7;font-weight:700">A</span>natomical&nbsp;'
            '<span style="color:#4FC3F7;font-weight:700">P</span>athology and&nbsp;'
            '<span style="color:#4FC3F7;font-weight:700">H</span>istology'
        )
        subtitle = QLabel(acronym_html)
        subtitle.setTextFormat(Qt.TextFormat.RichText)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #8899aa; font-size: 13px; background: transparent;")

        self._status_label = QLabel("Initializing…")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(
            "color: #3a5a70; font-size: 10px; background: transparent;"
        )

        layout.addStretch(1)
        layout.addWidget(title)
        layout.addSpacing(16)
        layout.addWidget(divider)
        layout.addSpacing(16)
        layout.addWidget(subtitle)
        layout.addStretch(1)
        layout.addWidget(self._status_label)

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)
        QApplication.processEvents()

    def finish(self, main_window: QWidget) -> None:
        main_window.show()
        QTimer.singleShot(180, self.close)
