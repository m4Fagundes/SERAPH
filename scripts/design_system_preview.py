"""
SERAPH Design System Preview
=============================
Run:  python design_system_preview.py

Shows all design system components side by side for visual validation.
No dependencies on the rest of SERAPH — only imports design_system.py and widgets/.
"""
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt

# Bootstrap sys.path so relative imports from app/ work when run from project root
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.interface.gui.theme import global_stylesheet
from app.interface.gui.design_system import COLORS, SPACE, SIZE
from app.interface.gui.widgets.buttons import (
    PrimaryButton, ActionButton, SuccessButton,
    SecondaryButton, GhostButton, DestructiveButton,
)
from app.interface.gui.widgets.section_header import SectionHeader
from app.interface.gui.widgets.inputs import LabeledInput, LabeledCombobox


# ── Helpers ───────────────────────────────────────────────────────────────────

def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"background: {COLORS['border_default']}; border: none;")
    f.setFixedHeight(1)
    return f


def _group(title: str, content: QWidget) -> QWidget:
    """Wrap a content widget with a SectionHeader."""
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SPACE[2])
    layout.addWidget(SectionHeader(title))
    layout.addWidget(content)
    return w


# ── Model card (duplicated from macro_pipeline_panel for standalone preview) ──

class _PreviewModelCard(QWidget):
    """Standalone preview of the selectable model card (Option B)."""

    def __init__(self, name: str, desc: str, selected: bool = False):
        super().__init__()
        self._selected = selected
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(SIZE["lg"])

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE[3], 0, SPACE[3], 0)
        layout.setSpacing(SPACE[2])

        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600;"
            f" color: {COLORS['text_primary']}; background: transparent;"
        )
        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']}; background: transparent;"
        )
        col.addStretch()
        col.addWidget(name_lbl)
        col.addWidget(desc_lbl)
        col.addStretch()
        layout.addLayout(col, stretch=1)
        self._refresh()

    def _refresh(self) -> None:
        if self._selected:
            self.setStyleSheet(
                f"background: {COLORS['bg_elevated']};"
                f" border-radius: 6px;"
                f" border-left: 2px solid {COLORS['accent_action']};"
            )
        else:
            self.setStyleSheet(
                f"background: {COLORS['bg_panel']};"
                f" border-radius: 6px;"
                f" border: 1px solid {COLORS['border_default']};"
            )

    def mousePressEvent(self, event):
        self._selected = not self._selected
        self._refresh()
        super().mousePressEvent(event)


# ── Sections ──────────────────────────────────────────────────────────────────

def _build_buttons_section() -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(SPACE[3], SPACE[2], SPACE[3], SPACE[2])
    layout.setSpacing(SPACE[2])

    sizes = ["sm", "md", "lg"]

    for size in sizes:
        row = QHBoxLayout()
        row.setSpacing(SPACE[2])
        row.addWidget(PrimaryButton(f"Primary {size}", size=size))
        row.addWidget(ActionButton(f"Action {size}", size=size))
        row.addWidget(SuccessButton(f"Success {size}", size=size))
        row.addWidget(SecondaryButton(f"Secondary {size}", size=size))
        row.addWidget(GhostButton(f"Ghost {size}", size=size))
        row.addWidget(DestructiveButton(f"Destructive {size}", size=size))
        row.addStretch()
        layout.addLayout(row)

    # Disabled states
    row_d = QHBoxLayout()
    row_d.setSpacing(SPACE[2])
    btn_dis1 = ActionButton("Disabled Action", size="md")
    btn_dis1.setEnabled(False)
    btn_dis2 = PrimaryButton("Disabled Primary", size="md")
    btn_dis2.setEnabled(False)
    row_d.addWidget(btn_dis1)
    row_d.addWidget(btn_dis2)
    row_d.addStretch()
    layout.addLayout(row_d)

    return w


def _build_inputs_section() -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(SPACE[3], SPACE[2], SPACE[3], SPACE[2])
    layout.setSpacing(SPACE[2])

    layout.addWidget(LabeledInput("Name", placeholder="Enter name..."))
    layout.addWidget(LabeledInput("Microns", placeholder="e.g. 0.25"))

    combo = LabeledCombobox("Layer")
    combo.combo.addItems(["Macro Cellpose", "Macro NuClick", "CellViT-SAM"])
    layout.addWidget(combo)

    return w


def _build_model_cards_section() -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(SPACE[3], SPACE[2], SPACE[3], SPACE[2])
    layout.setSpacing(SPACE[1])

    models = [
        ("Cellpose (cpsam)", "cpsam · CUDA", True),
        ("NuClick (PyTorch)", "PyTorch", False),
        ("CellViT-SAM", "ViT-SAM", False),
    ]
    for name, desc, selected in models:
        layout.addWidget(_PreviewModelCard(name, desc, selected))

    layout.addSpacing(SPACE[2])
    btn_run = ActionButton("Run on all slices", size="lg")
    layout.addWidget(btn_run)

    return w


def _build_section_headers_section() -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(SPACE[3], SPACE[2], SPACE[3], SPACE[2])
    layout.setSpacing(SPACE[2])

    layout.addWidget(SectionHeader("Section without badge"))
    layout.addWidget(SectionHeader("Slices", badge="0"))

    sh_active = SectionHeader("Models", badge="3")
    sh_active.set_badge("3", active=True)
    layout.addWidget(sh_active)

    return w


# ── Main window ───────────────────────────────────────────────────────────────

class PreviewWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SERAPH Design System Preview")
        self.resize(1100, 760)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)

        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(SPACE[4], SPACE[4], SPACE[4], SPACE[4])
        root.setSpacing(SPACE[4])

        title = QLabel("SERAPH Design System")
        title.setStyleSheet(
            f"color: {COLORS['brand']}; font-size: 20px; font-weight: 700;"
        )
        root.addWidget(title)
        root.addWidget(_divider())

        root.addWidget(_group("Buttons (all sizes + disabled)", _build_buttons_section()))
        root.addWidget(_divider())
        root.addWidget(_group("Labeled Inputs", _build_inputs_section()))
        root.addWidget(_divider())
        root.addWidget(_group("Section Headers", _build_section_headers_section()))
        root.addWidget(_divider())
        root.addWidget(_group("Model Cards — Option B (click to select)", _build_model_cards_section()))

        root.addStretch()
        scroll.setWidget(container)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(global_stylesheet())
    win = PreviewWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
