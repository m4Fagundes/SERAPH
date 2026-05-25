"""
Semantic button classes for SERAPH.

Each class is a QPushButton with:
- Standardized height via SIZE scale
- objectName-based styling from global QSS (no inline setStyleSheet)
- Pointing-hand cursor for discoverability

Usage:
    from app.interface.gui.widgets.buttons import ActionButton, PrimaryButton
    btn = ActionButton("Run Segmentation")
"""
from __future__ import annotations
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import Qt
from app.interface.gui.design_system import SIZE


class _SeraphButton(QPushButton):
    """Base for all semantic SERAPH buttons. Do not instantiate directly."""
    _variant: str = "secondary"

    def __init__(self, text: str = "", parent=None, size: str = "md"):
        super().__init__(text, parent)
        h = SIZE.get(size, SIZE["md"])
        self.setMinimumHeight(h)
        self.setMaximumHeight(h)
        self.setObjectName(f"btn_{self._variant}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class PrimaryButton(_SeraphButton):
    """Creation/navigation actions — blue filled. Ex: + Add Image, Open."""
    _variant = "primary"


class ActionButton(_SeraphButton):
    """Heavy computation — purple filled. Ex: Run Segmentation, Start Pipeline."""
    _variant = "action"


class SuccessButton(_SeraphButton):
    """Confirmation/finalization — green filled. Ex: Save, Apply Changes."""
    _variant = "success"


class SecondaryButton(_SeraphButton):
    """Secondary actions — outline without fill. Ex: Cancel, Re-run."""
    _variant = "secondary"


class GhostButton(_SeraphButton):
    """Tertiary actions — text-only, no border. Ex: links, + Add Layer."""
    _variant = "ghost"


class DestructiveButton(_SeraphButton):
    """Destructive actions — red outline. Ex: Delete, Clear."""
    _variant = "destructive"
