"""
Labeled input widgets for SERAPH.

Composite widgets pairing a QLabel with a QLineEdit or QComboBox,
using standardized height and spacing tokens.
"""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QLineEdit, QComboBox
from app.interface.gui.design_system import SIZE, COLORS, SPACE


class LabeledInput(QWidget):
    """QLineEdit with inline label. Height standardized to SIZE['md'] (36px)."""

    def __init__(self, label: str, placeholder: str = "", parent=None):
        super().__init__(parent)
        h = SIZE["md"]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE[2])

        lbl = QLabel(label)
        lbl.setFixedWidth(80)
        lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px; background: transparent;"
        )
        self._input = QLineEdit()
        self._input.setPlaceholderText(placeholder)
        self._input.setFixedHeight(h)
        self._input.setObjectName("input_labeled")
        layout.addWidget(lbl)
        layout.addWidget(self._input, stretch=1)
        self.setFixedHeight(h)

    @property
    def input(self) -> QLineEdit:
        return self._input

    def text(self) -> str:
        return self._input.text()

    def setText(self, t: str) -> None:
        self._input.setText(t)


class LabeledCombobox(QWidget):
    """QComboBox with inline label. Height standardized to SIZE['md'] (36px)."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        h = SIZE["md"]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE[2])

        lbl = QLabel(label)
        lbl.setFixedWidth(80)
        lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px; background: transparent;"
        )
        self._combo = QComboBox()
        self._combo.setFixedHeight(h)
        self._combo.setObjectName("combo_labeled")
        layout.addWidget(lbl)
        layout.addWidget(self._combo, stretch=1)
        self.setFixedHeight(h)

    @property
    def combo(self) -> QComboBox:
        return self._combo
