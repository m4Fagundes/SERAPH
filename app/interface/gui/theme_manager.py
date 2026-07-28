"""
SERAPH Theme Manager — live dark/light switching.

The global QSS is re-generated on every switch, but widgets that carry an *inline*
stylesheet keep whatever colors they were built with. `themed()` solves that: it
registers the style function instead of its output, so the widget can be re-styled
from the new palette whenever the theme flips.

    from app.interface.gui.theme_manager import themed
    themed(lbl, lambda: f"color: {COLORS['text_muted']}; font-size: 11px;")

Calling `themed()` again on the same widget replaces its registered style function,
so state-dependent styles (selected/unselected, active/inactive) work unchanged.

Widgets are held weakly — no need to unregister on destroy.
"""
from __future__ import annotations

from typing import Callable
from weakref import WeakKeyDictionary

from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

from app.interface.gui.design_system import (
    DEFAULT_THEME,
    THEMES,
    current_theme,
    set_theme,
)

_SETTINGS_ORG = "SERAPH"
_SETTINGS_APP = "SERAPH"
_SETTINGS_KEY = "ui/theme"


class _ThemeManager(QObject):
    """Emits the new theme name ("dark" / "light") after a switch is applied."""

    theme_changed = pyqtSignal(str)


theme_manager = _ThemeManager()

# widget -> callable returning its QSS. Weak keys: entries vanish with the widget.
_styled: "WeakKeyDictionary[QWidget, Callable[[], str]]" = WeakKeyDictionary()


def themed(widget: QWidget, style_fn: Callable[[], str]) -> QWidget:
    """
    Apply `style_fn()` to `widget` now and re-apply it on every theme change.

    `style_fn` must read colors from COLORS at call time — a pre-formatted string
    would freeze the palette it was built with, which is exactly the bug this
    exists to prevent.
    """
    widget.setStyleSheet(style_fn())
    _styled[widget] = style_fn
    return widget


def _restyle_all() -> None:
    for widget, style_fn in list(_styled.items()):
        try:
            widget.setStyleSheet(style_fn())
        except RuntimeError:
            # Underlying C++ widget already deleted — drop the stale entry.
            _styled.pop(widget, None)


def apply_theme(name: str, *, persist: bool = True) -> str:
    """
    Switch the palette, rebuild the global stylesheet, re-style inline widgets.

    Returns the theme actually applied (falls back to the default if `name` is
    unknown). Safe to call before a QApplication exists — it then only swaps the
    token table, which is what startup needs.
    """
    key = set_theme(name)

    app = QApplication.instance()
    if app is not None:
        from app.interface.gui.theme import global_stylesheet

        app.setStyleSheet(global_stylesheet())
        _restyle_all()

    if persist:
        QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue(_SETTINGS_KEY, key)

    theme_manager.theme_changed.emit(key)
    return key


def toggle_theme() -> str:
    """Flip between dark and light. Returns the newly applied theme."""
    return apply_theme("light" if current_theme() == "dark" else "dark")


def saved_theme() -> str:
    """The user's persisted theme, or the default when unset/invalid."""
    value = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(_SETTINGS_KEY, DEFAULT_THEME)
    return value if isinstance(value, str) and value in THEMES else DEFAULT_THEME
