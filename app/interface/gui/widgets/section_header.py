"""
SectionHeader — standardized section title widget for SERAPH panels.

Renders: uppercase label with a subtle horizontal divider + optional badge pill.
Fixed height 36px.
"""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QFrame, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt
from app.interface.gui.design_system import COLORS, SPACE


class SectionHeader(QWidget):
    """
    Section header: uppercase, muted, subtle horizontal divider, optional count badge.
    Fixed height 36px.

    Usage:
        header = SectionHeader("Slices", badge="0")
        header.set_badge("3", active=True)
    """

    def __init__(self, title: str, badge: str = "", parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(
            f"background: transparent;"
            f" border-bottom: 1px solid {COLORS['border_default']};"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACE[2])

        lbl = QLabel(title.upper())
        lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: 600;"
            f" letter-spacing: 0.5px; background: transparent;"
            f" border: none; padding-left: 0;"
        )
        row.addWidget(lbl)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setStyleSheet(
            f"background: {COLORS['border_default']};"
            f" color: {COLORS['border_default']};"
            f" border: none;"
        )
        line.setFixedHeight(1)
        row.addWidget(line, stretch=1)

        if badge:
            self._badge = QLabel(badge)
            self._badge.setFixedHeight(18)
            self._badge.setMinimumWidth(20)
            self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._badge.setStyleSheet(self._inactive_style())
            row.addWidget(self._badge)
        else:
            self._badge = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_badge(self, value: str, active: bool = False) -> None:
        """Update badge text and toggle active (blue) / inactive (muted) style."""
        if self._badge is None:
            return
        self._badge.setStyleSheet(
            self._active_style() if active else self._inactive_style()
        )
        self._badge.setText(value)

    # ── Style helpers ─────────────────────────────────────────────────────────

    def _active_style(self) -> str:
        return (
            f"background: {COLORS['accent_primary']}; color: white;"
            f" font-size: 10px; font-weight: 700; border-radius: 9px; padding: 0 5px;"
        )

    def _inactive_style(self) -> str:
        return (
            f"background: {COLORS['bg_control']}; color: {COLORS['text_muted']};"
            f" font-size: 10px; font-weight: 700; border-radius: 9px; padding: 0 5px;"
        )
