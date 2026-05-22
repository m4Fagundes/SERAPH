"""
SERAPH Design System
====================
Single source of truth for all UI design tokens and stylesheets.

Apply the global stylesheet once at application startup:

    from app.interface.gui.theme import global_stylesheet
    app.setStyleSheet(global_stylesheet())

Use PALETTE and helper functions for component-specific overrides only.
"""
from __future__ import annotations
from typing import Dict

# ── Design Tokens ────────────────────────────────────────────────────────────

PALETTE: Dict[str, str] = {
    # Backgrounds — darkest to lightest
    "bg_base":    "#0d1117",   # deepest canvas/window base
    "bg_surface": "#161b22",   # elevated surface
    "bg_panel":   "#21262d",   # toolbars, docks, sidebars
    "bg_control": "#2d333b",   # inputs, buttons, dropdowns
    "bg_hover":   "#373e47",   # hover state for controls

    # Borders
    "border":        "#444c56",  # default separator
    "border_focus":  "#1f6feb",  # keyboard focus ring
    "border_accent": "#1e4060",  # SERAPH brand accent border

    # Text
    "text_primary":   "#cdd9e5",  # body text
    "text_muted":     "#8b949e",  # labels, section headers
    "text_disabled":  "#545d68",  # disabled state

    # Brand
    "accent":     "#4FC3F7",  # SERAPH cyan — titles, selection indicators
    "accent_dim": "#1e4060",  # dimmed accent for dividers / subtle borders

    # Primary action — blue
    "btn_primary":       "#1f6feb",
    "btn_primary_hover": "#388bfd",
    "btn_primary_press": "#0d419d",

    # Success — green
    "btn_success":       "#238636",
    "btn_success_hover": "#2ea043",
    "btn_success_press": "#196127",

    # Danger — red
    "btn_danger":       "#da3633",
    "btn_danger_hover": "#f85149",
    "btn_danger_press": "#b62324",

    # Export — nuclei (magenta)
    "btn_nuclei":       "#c2185b",
    "btn_nuclei_hover": "#e91e63",
    "btn_nuclei_press": "#880e4f",

    # Export — HDF5 (purple)
    "btn_hdf5":       "#7c3aed",
    "btn_hdf5_hover": "#8b5cf6",
    "btn_hdf5_press": "#6d28d9",

    # Semantic / status
    "progress_chunk":    "#00d68f",  # pipeline progress bar fill
    "timer_label":       "#F1C40F",  # phase timer yellow
    "exec_time_done":    "#00FF88",  # completed timing readout
    "exec_time_error":   "#E74C3C",  # error timing readout

    # Canvas (used programmatically via QColor, not CSS)
    "canvas_bg": "#111111",
    "tile_bg":   "#1a1a1a",

    # Splash screen (intentionally distinct — deepest dark)
    "splash_bg":     "#0d1117",
    "splash_border": "#1e4060",
    "splash_title":  "#4FC3F7",
    "splash_sub":    "#8899aa",
    "splash_status": "#3a5a70",
}

_FONT = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"


# ── SERAPH Icon ───────────────────────────────────────────────────────────────

def create_seraph_icon(size: int = 64) -> "QPixmap":
    """
    Render the SERAPH symbol as a QPixmap at any resolution.

    Design: flat-top hexagon (cell cross-section) with a filled cyan nucleus at
    the centre and three organelle dots at alternating vertices. Transparent
    background so it composites cleanly over any surface.
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
    bg     = QColor("#0d1117")

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


# ── Global Stylesheet ─────────────────────────────────────────────────────────

def global_stylesheet() -> str:
    """Return the full application QSS. Apply once via app.setStyleSheet()."""
    p = PALETTE
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
    background-color: {p['bg_panel']};
    border-bottom: 1px solid {p['border']};
    spacing: 6px;
    padding: 4px 8px;
}}
QToolBar::separator {{
    width: 1px;
    background-color: {p['border']};
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
    color: #ffffff;
}}
QToolButton:checked {{
    background-color: {p['btn_primary']};
    color: #ffffff;
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
    background-color: {p['bg_panel']};
    color: {p['text_primary']};
    border-bottom: 1px solid {p['border']};
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
    background-color: {p['bg_hover']};
}}
QMenuBar::item:pressed {{
    background-color: {p['btn_primary']};
    color: #ffffff;
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
    color: #ffffff;
}}
QMenu::separator {{
    height: 1px;
    background-color: {p['border']};
    margin: 4px 8px;
}}

/* ── Dock Widgets ─────────────────────────────────────────────────────────── */
QDockWidget {{
    background-color: {p['bg_panel']};
    color: {p['text_primary']};
    font-family: {_FONT};
    font-weight: bold;
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background-color: {p['bg_panel']};
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
    color: #ffffff;
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
    background-color: rgba(255, 255, 255, 0.03);
    border-radius: 5px;
    padding: 6px;
    margin-bottom: 3px;
    border: 1px solid transparent;
}}
QListWidget::item:hover {{
    background-color: rgba(255, 255, 255, 0.07);
    border: 1px solid {p['border']};
}}
QListWidget::item:selected {{
    background-color: rgba(31, 111, 235, 0.22);
    border-left: 3px solid {p['accent']};
    color: #ffffff;
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
    background: #ffffff;
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
    background-color: {p['bg_panel']};
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

"""


# ── Button Variant Helpers ────────────────────────────────────────────────────
# Use these for buttons that need a semantic color beyond the neutral default.

def btn_primary() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_primary']}; color: white; border: none; "
        f"border-radius: 4px; padding: 6px 14px; font-weight: bold; font-family: {_FONT}; }} "
        f"QPushButton:hover {{ background-color: {p['btn_primary_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['btn_primary_press']}; }} "
        f"QPushButton:disabled {{ background-color: {p['bg_control']}; color: {p['text_disabled']}; border: 1px solid {p['border']}; }}"
    )


def btn_success() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_success']}; color: white; border: none; "
        f"border-radius: 4px; padding: 6px 14px; font-weight: bold; font-family: {_FONT}; }} "
        f"QPushButton:hover {{ background-color: {p['btn_success_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['btn_success_press']}; }}"
    )


def btn_danger() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_danger']}; color: white; border: none; "
        f"border-radius: 4px; padding: 6px 14px; font-weight: bold; font-family: {_FONT}; }} "
        f"QPushButton:hover {{ background-color: {p['btn_danger_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['btn_danger_press']}; }}"
    )


def btn_nuclei() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_nuclei']}; color: white; border: none; "
        f"border-radius: 4px; padding: 6px 14px; font-weight: bold; font-family: {_FONT}; margin-left: 4px; }} "
        f"QPushButton:hover {{ background-color: {p['btn_nuclei_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['btn_nuclei_press']}; }}"
    )


def btn_hdf5() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_hdf5']}; color: white; border: none; "
        f"border-radius: 4px; padding: 6px 14px; font-weight: bold; font-family: {_FONT}; margin-left: 4px; }} "
        f"QPushButton:hover {{ background-color: {p['btn_hdf5_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['btn_hdf5_press']}; }}"
    )


def btn_add() -> str:
    """Sidebar '+ Add ...' action buttons."""
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_primary']}; color: white; border: none; "
        f"border-radius: 4px; padding: 7px; font-weight: bold; font-family: {_FONT}; }} "
        f"QPushButton:hover {{ background-color: {p['btn_primary_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {p['btn_primary_press']}; }}"
    )


def btn_add_tile() -> str:
    """Sidebar '+ Add Tile' — green variant."""
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['btn_success']}; color: white; border: none; "
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
        f"color: {p['accent']}; font-size: 11pt; font-weight: 700; "
        f"font-family: {_FONT}; letter-spacing: 1.5px; background: transparent;"
    )


def breadcrumb_label() -> str:
    p = PALETTE
    return (
        f"color: {p['text_muted']}; font-size: 9pt; "
        f"font-family: {_FONT}; background: transparent;"
    )


def tool_pill() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: {p['bg_control']}; color: {p['text_primary']}; "
        f"border: 1px solid {p['border']}; border-radius: 5px; "
        f"padding: 3px 12px; font-size: 8pt; font-weight: 500; font-family: {_FONT}; min-width: 90px; }} "
        f"QPushButton:hover {{ background-color: {p['bg_hover']}; border: 1px solid {p['border_focus']}; color: #ffffff; }} "
        f"QPushButton:pressed {{ background-color: {p['bg_surface']}; }}"
    )


def overflow_btn() -> str:
    p = PALETTE
    return (
        f"QPushButton {{ background-color: transparent; color: {p['text_muted']}; "
        f"border: 1px solid transparent; border-radius: 5px; "
        f"padding: 3px 10px; font-size: 13pt; font-weight: 700; font-family: {_FONT}; }} "
        f"QPushButton:hover {{ background-color: {p['bg_hover']}; border: 1px solid {p['border']}; color: {p['text_primary']}; }} "
        f"QPushButton:pressed {{ background-color: {p['bg_surface']}; }}"
    )
