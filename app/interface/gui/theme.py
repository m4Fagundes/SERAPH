"""
SERAPH Design System — Theme layer.
====================================
Applies the global QSS stylesheet and exposes backward-compatible helpers.

Tokens now live in design_system.py. Import from there in new code:
    from app.interface.gui.design_system import COLORS, SPACE, SIZE, RADIUS

Apply global stylesheet once at startup:
    from app.interface.gui.theme import global_stylesheet
    app.setStyleSheet(global_stylesheet())
"""
from __future__ import annotations
from typing import Dict

# Re-export everything from design_system for backward compatibility
from app.interface.gui.design_system import (
    COLORS as PALETTE,
    COLORS,
    SPACE,
    SIZE,
    RADIUS,
    FONT_FAMILY,
)

_FONT = FONT_FAMILY


# ── SERAPH Icon ───────────────────────────────────────────────────────────────

def create_seraph_icon(size: int = 64, bg: str | None = None) -> "QPixmap":
    """
    Render the SERAPH symbol as a QPixmap at any resolution.

    Design: flat-top hexagon (cell cross-section) with a filled cyan nucleus at
    the centre and three organelle dots at alternating vertices. Transparent
    background so it composites cleanly over any surface.

    `bg` fills the hexagon body. It defaults to the dark splash colour, which is
    what the OS window icon and the splash screen want; callers rendering the mark
    onto a themed surface should pass that surface's colour instead.
    """
    import math
    from PyQt6.QtCore import Qt, QPointF
    from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF

    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    c = size / 2
    stroke = max(1.5, size * 0.055)
    cyan   = QColor("#4FC3F7")
    bg     = QColor(bg or PALETTE["splash_bg"])

    # Flat-top regular hexagon
    hex_r = c * 0.87
    pts = [
        QPointF(c + hex_r * math.cos(math.radians(60 * i - 30)), c + hex_r * math.sin(math.radians(60 * i - 30)))
        for i in range(6)
    ]
    hex_poly = QPolygonF(pts)

    # Dark fill inside hexagon
    p.setBrush(QBrush(bg))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPolygon(hex_poly)

    # Cyan hexagon border
    pen = QPen(cyan, stroke)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.GlobalColor.transparent)
    p.drawPolygon(hex_poly)

    # Nucleus — filled cyan circle at centre
    p.setBrush(QBrush(cyan))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(c, c), c * 0.27, c * 0.27)

    # Three organelle dots at every other vertex (inner orbit)
    dot_r   = max(1.0, c * 0.09)
    orbit_r = c * 0.56
    for i in range(3):
        angle = math.radians(60 * (i * 2) - 30)
        p.drawEllipse(QPointF(c + orbit_r * math.cos(angle), c + orbit_r * math.sin(angle)), dot_r, dot_r)

    p.end()
    return px


def create_layout_sidebar_right_icon(size: int = 16, active: bool = False) -> "QPixmap":
    """
    Render VS Code's Codicon `layout-sidebar-right`.

    Source shape: Microsoft VS Code Codicons, `layout-sidebar-right`.
    The pixmap is generated at runtime so the icon can follow the active theme's
    active/inactive colors without shipping extra assets.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPixmap

    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)

    color = QColor(PALETTE["text_hover"] if active else PALETTE["text_muted"])

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.scale(size / 16, size / 16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)

    # SVG path:
    # M2 1L1 2V14L2 15H14L15 14V2L14 1H2ZM2 14V2H9V14H2Z
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    path.moveTo(2, 1)
    path.lineTo(1, 2)
    path.lineTo(1, 14)
    path.lineTo(2, 15)
    path.lineTo(14, 15)
    path.lineTo(15, 14)
    path.lineTo(15, 2)
    path.lineTo(14, 1)
    path.lineTo(2, 1)
    path.closeSubpath()

    path.moveTo(2, 14)
    path.lineTo(2, 2)
    path.lineTo(9, 2)
    path.lineTo(9, 14)
    path.lineTo(2, 14)
    path.closeSubpath()

    p.drawPath(path)
    p.end()
    return px


# ── Global Stylesheet ─────────────────────────────────────────────────────────

def global_stylesheet() -> str:
    """Return the full application QSS. Apply once via app.setStyleSheet()."""
    p = PALETTE
    r = RADIUS
    s = SPACE
    return f"""

/* ── Base ─────────────────────────────────────────────────────────────────── */
QMainWindow, QDialog, QWidget {{
    background-color: {p['bg_base']};
    color: {p['text_primary']};
    font-family: {_FONT};
    font-size: 9pt;
}}

/* ── Toolbar ──────────────────────────────────────────────────────────────── */
QToolBar {{
    background-color: {p['bg_elevated']};
    border-top: 1px solid {p['border_subtle']};
    border-bottom: 1px solid {p['border_default']};
    spacing: 6px;
    padding: 4px 8px;
}}
QToolBar::separator {{
    width: 1px;
    background-color: {p['border_default']};
    margin: 4px 2px;
}}
QToolButton {{
    background-color: transparent;
    color: {p['text_primary']};
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 5px 10px;
    font-family: {_FONT};
    font-size: 8pt;
    font-weight: 500;
}}
QToolButton:hover {{
    background-color: {p['bg_hover']};
    border: 1px solid {p['border']};
    color: {p['text_hover']};
}}
QToolButton:checked {{
    background-color: {p['btn_primary']};
    color: {p['text_on_accent']};
    border: 1px solid {p['border_focus']};
}}
QToolButton:pressed {{
    background-color: {p['btn_primary_press']};
}}
QToolButton:disabled {{
    color: {p['text_disabled']};
}}

/* ── Menu Bar ─────────────────────────────────────────────────────────────── */
QMenuBar {{
    background-color: {p['bg_base']};
    color: {p['text_secondary']};
    border-bottom: 1px solid {p['border_default']};
    font-family: {_FONT};
    font-size: 9pt;
    padding: 2px 4px;
}}
QMenuBar::item {{
    background-color: transparent;
    padding: 4px 10px;
    border-radius: 3px;
}}
QMenuBar::item:selected {{
    background-color: {p['bg_elevated']};
    color: {p['text_primary']};
}}
QMenuBar::item:pressed {{
    background-color: {p['btn_primary']};
    color: {p['text_on_accent']};
}}

/* ── Menus ────────────────────────────────────────────────────────────────── */
QMenu {{
    background-color: {p['bg_panel']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    padding: 4px 0;
    font-family: {_FONT};
    color: {p['text_primary']};
}}
QMenu::item {{
    padding: 6px 24px 6px 14px;
    font-size: 9pt;
    border-radius: 3px;
    margin: 1px 4px;
}}
QMenu::item:selected {{
    background-color: {p['btn_primary']};
    color: {p['text_on_accent']};
}}
QMenu::separator {{
    height: 1px;
    background-color: {p['border']};
    margin: 4px 8px;
}}

/* ── Dock Widgets ─────────────────────────────────────────────────────────── */
QDockWidget {{
    background-color: {p['bg_elevated']};
    color: {p['text_primary']};
    font-family: {_FONT};
    font-weight: bold;
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background-color: {p['bg_elevated']};
    padding: 6px 10px;
    border-bottom: 1px solid {p['border']};
    color: {p['text_muted']};
    font-size: 8pt;
    font-weight: bold;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

/* ── Labels ───────────────────────────────────────────────────────────────── */
QLabel {{
    color: {p['text_primary']};
    font-family: {_FONT};
    background: transparent;
}}

/* ── Inputs ───────────────────────────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {p['bg_control']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: {p['btn_primary']};
    font-family: {_FONT};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {p['border_focus']};
    background-color: {p['bg_hover']};
}}
QLineEdit:read-only {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {p['text_primary']};
}}

/* ── Spin Boxes ───────────────────────────────────────────────────────────── */
QDoubleSpinBox, QSpinBox {{
    background-color: {p['bg_control']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
    border-radius: 3px;
    padding: 2px 4px;
    font-family: {_FONT};
}}
QDoubleSpinBox:focus, QSpinBox:focus {{
    border: 1px solid {p['border_focus']};
}}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {p['bg_hover']};
    border: none;
    border-radius: 2px;
    width: 16px;
}}
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover,
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: {p['border_focus']};
}}

/* ── ComboBox ─────────────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {p['bg_control']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
    border-radius: 4px;
    padding: 4px 8px;
    font-family: {_FONT};
}}
QComboBox:focus {{
    border: 1px solid {p['border_focus']};
    background-color: {p['bg_hover']};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {p['bg_panel']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
    selection-background-color: {p['btn_primary']};
    outline: none;
}}

/* ── Buttons (default neutral) ────────────────────────────────────────────── */
QPushButton {{
    background-color: {p['bg_control']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
    border-radius: 4px;
    padding: 5px 14px;
    font-weight: 500;
    font-family: {_FONT};
}}
QPushButton:hover {{
    background-color: {p['bg_hover']};
    border: 1px solid {p['border_focus']};
    color: {p['text_hover']};
}}
QPushButton:pressed {{
    background-color: {p['bg_surface']};
}}
QPushButton:disabled {{
    background-color: {p['bg_panel']};
    color: {p['text_disabled']};
    border: 1px solid {p['border']};
}}

/* ── GroupBox ─────────────────────────────────────────────────────────────── */
QGroupBox {{
    color: {p['text_muted']};
    font-size: 8pt;
    font-weight: bold;
    letter-spacing: 1px;
    border: 1px solid {p['border']};
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {p['text_muted']};
}}

/* ── List Widgets ─────────────────────────────────────────────────────────── */
QListWidget {{
    background-color: transparent;
    border: none;
    color: {p['text_primary']};
    outline: none;
}}
QListWidget::item {{
    background-color: {p['overlay_subtle']};
    border-radius: 5px;
    padding: 6px;
    margin-bottom: 3px;
    border: 1px solid transparent;
}}
QListWidget::item:hover {{
    background-color: {p['overlay_hover']};
    border: 1px solid {p['border']};
}}
QListWidget::item:selected {{
    background-color: {p['overlay_selected']};
    border-left: 3px solid {p['accent']};
    color: {p['text_primary']};
}}

/* ── Progress Bar ─────────────────────────────────────────────────────────── */
QProgressBar {{
    border: 1px solid {p['border']};
    border-radius: 4px;
    text-align: center;
    color: {p['text_primary']};
    background-color: {p['bg_control']};
    font-size: 8pt;
    min-height: 14px;
}}
QProgressBar::chunk {{
    background-color: {p['progress_chunk']};
    border-radius: 4px;
}}

/* ── Slider ───────────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    border: none;
    height: 6px;
    background: {p['bg_control']};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {p['btn_primary']};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {p['text_primary']};
    border: 2px solid {p['bg_panel']};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    background: {p['accent_primary']};
    border: 2px solid {p['border_focus']};
}}

/* ── CheckBox ─────────────────────────────────────────────────────────────── */
QCheckBox {{
    color: {p['text_primary']};
    font-family: {_FONT};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    background-color: {p['bg_control']};
    border: 1px solid {p['border']};
    border-radius: 3px;
}}
QCheckBox::indicator:checked {{
    background-color: {p['btn_primary']};
    border: 1px solid {p['border_focus']};
}}
QCheckBox::indicator:hover {{
    border: 1px solid {p['border_focus']};
}}

/* ── Scrollbar ────────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background-color: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {p['border']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {p['text_muted']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background-color: transparent;
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background-color: {p['border']};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {p['text_muted']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Status Bar ───────────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {p['bg_elevated']};
    color: {p['text_muted']};
    border-top: 1px solid {p['border']};
    font-size: 8pt;
    font-family: {_FONT};
}}
QStatusBar::item {{
    border: none;
}}

/* ── Splitter ─────────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {p['border']};
    width: 1px;
    height: 1px;
}}

/* ── Scroll Area ──────────────────────────────────────────────────────────── */
QScrollArea {{
    border: none;
    background-color: transparent;
}}

/* ── Image Tab Bar ────────────────────────────────────────────────────────── */
QTabBar {{
    background: transparent;
    border: none;
}}
QTabBar::tab {{
    background: {p['bg_panel']};
    color: {p['text_muted']};
    border: 1px solid {p['border']};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 5px 14px 6px 14px;
    margin-right: 2px;
    font-size: 9pt;
    font-family: {_FONT};
    min-width: 80px;
    max-width: 200px;
}}
QTabBar::tab:selected {{
    background: {p['bg_elevated']};
    color: {p['text_primary']};
    border-top: 2px solid {p['btn_primary']};
    border-bottom: 1px solid {p['bg_elevated']};
}}
QTabBar::tab:hover:!selected {{
    background: {p['bg_hover']};
    color: {p['text_primary']};
}}
QTabBar::close-button {{
    subcontrol-position: right;
    width: 14px;
    height: 14px;
    padding: 0 2px;
    border-radius: 3px;
}}
QTabBar::close-button:hover {{
    background: {p['btn_danger']};
}}

/* ── Tooltips ─────────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {p['bg_panel']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 8pt;
    font-family: {_FONT};
}}

/* ── Semantic buttons (via objectName) ────────────────────────────────────── */
QPushButton#btn_primary {{
    background-color: {p['accent_primary']};
    color: {p['text_on_accent']}; border: none;
    border-radius: {r['md']}px;
    padding: {s[2]}px {s[3]}px;
    font-size: 13px; font-weight: 500;
}}
QPushButton#btn_primary:hover {{ background-color: {p['accent_primary_hover']}; }}
QPushButton#btn_primary:pressed {{ background-color: {p['accent_primary_press']}; }}
QPushButton#btn_primary:disabled {{
    background-color: {p['bg_muted']};
    color: {p['text_disabled']};
}}

QPushButton#btn_action {{
    background-color: {p['accent_action']};
    color: {p['text_on_accent']}; border: none;
    border-radius: {r['md']}px;
    padding: {s[2]}px {s[3]}px;
    font-size: 13px; font-weight: 500;
}}
QPushButton#btn_action:hover {{ background-color: {p['accent_action_hover']}; }}
QPushButton#btn_action:pressed {{ background-color: {p['accent_action_press']}; }}
QPushButton#btn_action:disabled {{
    background-color: {p['bg_muted']};
    color: {p['text_disabled']};
}}

QPushButton#btn_success {{
    background-color: {p['accent_success']};
    color: {p['text_on_accent']}; border: none;
    border-radius: {r['md']}px;
    padding: {s[2]}px {s[3]}px;
    font-size: 13px; font-weight: 500;
}}
QPushButton#btn_success:hover {{ background-color: {p['accent_success_hover']}; }}
QPushButton#btn_success:pressed {{ background-color: {p['accent_success_press']}; }}

QPushButton#btn_secondary {{
    background-color: transparent;
    color: {p['text_secondary']};
    border: 1px solid {p['border_default']};
    border-radius: {r['md']}px;
    padding: 0 {s[3]}px;
    font-size: 13px; font-weight: 400;
}}
QPushButton#btn_secondary:hover {{
    background-color: {p['bg_hover']};
    color: {p['text_hover']};
    border-color: {p['border_strong']};
}}
QPushButton#btn_secondary:pressed {{ background-color: {p['bg_elevated']}; }}

QPushButton#btn_ghost {{
    background-color: transparent;
    color: {p['text_muted']};
    border: none;
    padding: {s[2]}px {s[3]}px;
    font-size: 13px;
}}
QPushButton#btn_ghost:hover {{
    background-color: {p['bg_hover']};
    color: {p['text_primary']};
}}

QPushButton#btn_destructive {{
    background-color: transparent;
    color: {p['accent_danger']};
    border: 1px solid {p['accent_danger']};
    border-radius: {r['md']}px;
    padding: {s[2]}px {s[3]}px;
    font-size: 13px;
}}
QPushButton#btn_destructive:hover {{
    background-color: {p['accent_danger']};
    color: {p['text_on_accent']};
}}
QPushButton#btn_destructive:pressed {{
    background-color: {p['accent_danger_press']};
    color: {p['text_on_accent']};
}}

/* ── Chrome panel toggles ─────────────────────────────────────────────────── */
QPushButton#panel_toggle {{
    background: transparent;
    color: {p['text_muted']};
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 0;
}}
QPushButton#panel_toggle:hover {{
    background: {p['bg_hover']};
    color: {p['text_primary']};
    border-color: {p['border_default']};
}}
QPushButton#panel_toggle:checked {{
    background: {p['bg_hover']};
    color: {p['text_primary']};
    border-color: {p['brand']};
}}

"""


# ── Button Variant Helpers ────────────────────────────────────────────────────
# Use these for buttons that need a semantic color beyond the neutral default.

def btn_primary() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_primary']}; color: {p['text_on_accent']}; border: none; "
        f"border-radius: 4px; padding: 6px 14px; font-weight: bold; font-family: {_FONT}; }} "
        f"QPushButton:hover {{ background-color: {p['btn_primary_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['btn_primary_press']}; }} "
        f"QPushButton:disabled {{ background-color: {p['bg_control']}; color: {p['text_disabled']}; border: 1px solid {p['border']}; }}"
    )


def btn_success() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_success']}; color: {p['text_on_accent']}; border: none; "
        f"border-radius: 4px; padding: 6px 14px; font-weight: bold; font-family: {_FONT}; }} "
        f"QPushButton:hover {{ background-color: {p['btn_success_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['btn_success_press']}; }}"
    )


def btn_danger() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_danger']}; color: {p['text_on_accent']}; border: none; "
        f"border-radius: 4px; padding: 6px 14px; font-weight: bold; font-family: {_FONT}; }} "
        f"QPushButton:hover {{ background-color: {p['btn_danger_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['btn_danger_press']}; }}"
    )


def btn_nuclei() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_nuclei']}; color: {p['text_on_accent']}; border: none; "
        f"border-radius: 4px; padding: 6px 14px; font-weight: bold; font-family: {_FONT}; margin-left: 4px; }} "
        f"QPushButton:hover {{ background-color: {p['btn_nuclei_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['btn_nuclei_press']}; }}"
    )


def btn_hdf5() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_hdf5']}; color: {p['text_on_accent']}; border: none; "
        f"border-radius: 4px; padding: 6px 14px; font-weight: bold; font-family: {_FONT}; margin-left: 4px; }} "
        f"QPushButton:hover {{ background-color: {p['btn_hdf5_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['btn_hdf5_press']}; }}"
    )


def btn_add() -> str:
    """Sidebar '+ Add ...' action buttons."""
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_primary']}; color: {p['text_on_accent']}; border: none; "
        f"border-radius: 4px; padding: 7px; font-weight: bold; font-family: {_FONT}; }} "
        f"QPushButton:hover {{ background-color: {p['btn_primary_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['btn_primary_press']}; }}"
    )


def btn_add_tile() -> str:
    """Sidebar '+ Add Tile' — green variant."""
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_success']}; color: {p['text_on_accent']}; border: none; "
        f"border-radius: 4px; padding: 6px; font-weight: bold; font-family: {_FONT}; margin-top: 4px; }} "
        f"QPushButton:hover {{ background-color: {p['btn_success_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['btn_success_press']}; }}"
    )


# ── Label Helpers ─────────────────────────────────────────────────────────────

def label_section() -> str:
    """Section header label — uppercase, muted, with accent left-border."""
    p = PALETTE
    return (
        f"color: {p['text_muted']}; font-size: 8pt; font-weight: bold; "
        f"letter-spacing: 1px; background: transparent; "
        f"border-left: 2px solid {p['accent']}; padding-left: 6px;"
    )


def label_value() -> str:
    """Value readout label."""
    p = PALETTE
    return f"color: {p['text_primary']}; font-size: 8pt; background: transparent;"


def label_accent() -> str:
    """Accent-colored readout (e.g. execution time)."""
    p = PALETTE
    return f"color: {p['accent']}; font-size: 9pt; font-weight: bold; background: transparent;"


def label_timer() -> str:
    """Pipeline phase timer label."""
    p = PALETTE
    return f"color: {p['timer_label']}; font-weight: bold; background: transparent;"


# ── Topbar Component Styles ───────────────────────────────────────────────────

def logo_wordmark() -> str:
    p = PALETTE
    return (
        f"color: {p['brand']}; font-size: 11pt; font-weight: 700; "
        f"font-family: {_FONT}; letter-spacing: 1.5px; background: transparent;"
    )


def breadcrumb_label() -> str:
    p = PALETTE
    return (
        f"color: {p['text_secondary']}; font-size: 9pt; "
        f"font-family: {_FONT}; background: transparent;"
    )


def tool_pill() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['bg_control']}; color: {p['text_primary']}; "
        f"border: 1px solid {p['border_default']}; border-radius: 5px; "
        f"padding: 3px 12px; font-size: 8pt; font-weight: 500; font-family: {_FONT}; min-width: 90px; }} "
        f"QPushButton:hover {{ background-color: {p['bg_hover']}; border: 1px solid {p['border_strong']}; color: {p['text_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['bg_elevated']}; }}"
    )


def overflow_btn() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: transparent; color: {p['text_muted']}; "
        f"border: 1px solid transparent; border-radius: 5px; "
        f"padding: 3px 10px; font-size: 13pt; font-weight: 700; font-family: {_FONT}; }} "
        f"QPushButton:hover {{ background-color: {p['bg_hover']}; border: 1px solid {p['border_default']}; color: {p['text_primary']}; }} "
        f"QPushButton:pressed {{ background-color: {p['bg_elevated']}; }}"
    )
