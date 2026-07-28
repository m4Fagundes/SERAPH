"""
SERAPH Design System — Single source of truth for all UI tokens.

Import from here in all components:
    from app.interface.gui.design_system import COLORS, SPACE, SIZE, RADIUS, FONT_FAMILY
    from app.interface.gui.design_system import PALETTE  # backward compat alias

COLORS is a *live* dict: `set_theme()` mutates it in place, so modules that did
`from ... import COLORS` keep seeing the active theme without re-importing. Read
colors at style-application time — never cache a value at import time.

To re-style widgets when the theme flips, use `theme_manager.themed()` instead of
calling `setStyleSheet()` directly.
"""
from __future__ import annotations
from typing import Dict, Tuple

# ── Spacing scale ─────────────────────────────────────────────────────────────
# Used as SPACE[n] — matches Mantine's spacing scale (base 4px)
SPACE: Dict[int, int] = {
    0: 0,
    1: 4,
    2: 8,
    3: 12,
    4: 16,
    5: 24,
    6: 32,
    7: 48,
}

# ── Sizing scale — component heights ─────────────────────────────────────────
SIZE: Dict[str, int] = {
    "xs": 24,
    "sm": 32,
    "md": 36,
    "lg": 44,
}

# ── Border radius ─────────────────────────────────────────────────────────────
RADIUS: Dict[str, int] = {
    "sm":   4,
    "md":   6,
    "lg":   8,
    "full": 999,
}

# ── Typography ────────────────────────────────────────────────────────────────
FONT_FAMILY: str = "'Segoe UI Variable', 'Segoe UI', system-ui, sans-serif"

# (size_css, weight)
TEXT: Dict[str, Tuple[str, int]] = {
    "xs":   ("11px", 400),
    "sm":   ("12px", 400),
    "base": ("13px", 400),   # DEFAULT
    "md":   ("14px", 500),
    "lg":   ("16px", 600),
}

# ── Theme-invariant tokens ────────────────────────────────────────────────────
# The image viewport stays dark in every theme: a dark backdrop maximises the
# perceived contrast of tissue and keeps segmentation overlay colours reading the
# same way regardless of the surrounding chrome.
_VIEWPORT: Dict[str, str] = {
    "canvas_bg": "#0D0F12",   # image viewport backdrop
    "tile_bg":   "#111317",   # tile viewport backdrop

    # Splash screen — always dark, shown before the theme is even applied
    "splash_bg":     "#0d1117",
    "splash_border": "#1e4060",
    "splash_title":  "#4FC3F7",
    "splash_sub":    "#8899aa",
    "splash_status": "#3a5a70",

    # Category colors for export buttons — identical in both themes
    "btn_nuclei":          "#c2185b",
    "btn_nuclei_hover":    "#e91e63",
    "btn_nuclei_press":    "#880e4f",
    "btn_hdf5":            "#7c3aed",
    "btn_hdf5_hover":      "#8b5cf6",
    "btn_hdf5_press":      "#6d28d9",
}

# ── Dark theme ────────────────────────────────────────────────────────────────
DARK: Dict[str, str] = {
    **_VIEWPORT,

    # Backgrounds — darkest to lightest
    "bg_canvas":   "#0D0F12",     # central content area (behind tabs / welcome)
    "bg_base":     "#181A20",     # base window
    "bg_surface":  "#20232A",     # raised surface
    "bg_elevated": "#20232A",     # elevated surface
    "bg_panel":    "#252932",     # sidebars, docks
    "bg_control":  "#303640",     # inputs, neutral buttons
    "bg_muted":    "#303640",     # recessed chips: badges, disabled fills
    "bg_hover":    "#3A424D",     # hover overlay
    "bg_selected": "rgba(34,139,230,0.12)",   # selection overlay
    "bg_selected_brand": "rgba(34,211,238,0.12)",  # brand-tinted selection

    # Neutral overlays — tint a surface without knowing its background
    "overlay_subtle":   "rgba(255,255,255,0.03)",
    "overlay_hover":    "rgba(255,255,255,0.07)",
    "overlay_selected": "rgba(34,139,230,0.15)",

    # Borders
    "border_subtle":  "#252932",
    "border_default": "#343B46",
    "border_strong":  "#228BE6",  # focus ring
    "border":         "#343B46",
    "border_focus":   "#228BE6",
    "border_accent":  "#1a4d8c",

    # Text
    "text_primary":   "#E9ECEF",
    "text_secondary": "#C1C2C5",
    "text_muted":     "#909296",
    "text_disabled":  "#5C5F66",
    "text_on_accent": "#FFFFFF",
    "text_hover":     "#FFFFFF",  # text over a neutral hover surface

    # Semantic button — Primary (Blue): Add, Open, Select
    "accent_primary":       "#228BE6",
    "accent_primary_hover": "#339AF0",
    "accent_primary_press": "#1971C2",

    # Semantic button — Action (Purple): Run, Execute, Process
    "accent_action":        "#7950F2",
    "accent_action_hover":  "#9775FA",
    "accent_action_press":  "#6741D9",

    # Semantic button — Success (Green): Save, Apply, Done
    "accent_success":       "#40C057",
    "accent_success_hover": "#51CF66",
    "accent_success_press": "#2F9E44",

    # Semantic button — Warning (Yellow): reversible alerts
    "accent_warning":       "#F59F00",
    "accent_warning_hover": "#FAB005",
    "accent_warning_press": "#E67700",

    # Semantic button — Danger (Red): Delete, Remove, Clear
    "accent_danger":        "#FA5252",
    "accent_danger_hover":  "#FF6B6B",
    "accent_danger_press":  "#E03131",

    # Brand
    "brand":     "#22D3EE",    # SERAPH cyan
    "brand_dim": "#164E63",
    "accent":     "#22D3EE",
    "accent_dim": "#164E63",

    # Status readouts
    "progress_chunk":  "#00d68f",
    "timer_label":     "#F1C40F",
    "exec_time_done":  "#00FF88",
    "exec_time_error": "#E74C3C",

    # ── Legacy button aliases — imported across the codebase ──────────────────
    "btn_primary":       "#228BE6",
    "btn_primary_hover": "#339AF0",
    "btn_primary_press": "#1971C2",
    "btn_success":       "#40C057",
    "btn_success_hover": "#51CF66",
    "btn_success_press": "#2F9E44",
    "btn_danger":        "#FA5252",
    "btn_danger_hover":  "#FF6B6B",
    "btn_danger_press":  "#E03131",
}

# ── Light theme ───────────────────────────────────────────────────────────────
LIGHT: Dict[str, str] = {
    **_VIEWPORT,

    # Backgrounds — lightest to darkest
    "bg_canvas":   "#FFFFFF",
    "bg_base":     "#F1F3F5",
    "bg_surface":  "#FFFFFF",
    "bg_elevated": "#FFFFFF",
    "bg_panel":    "#F8F9FA",
    "bg_control":  "#FFFFFF",
    # Inputs are white against the grey page, so chips need their own recessed
    # surface — a white badge on a near-white panel would read as nothing at all.
    "bg_muted":    "#E9ECEF",
    "bg_hover":    "#E9ECEF",
    "bg_selected": "rgba(34,139,230,0.12)",
    "bg_selected_brand": "rgba(14,116,144,0.10)",

    "overlay_subtle":   "rgba(0,0,0,0.02)",
    "overlay_hover":    "rgba(0,0,0,0.05)",
    "overlay_selected": "rgba(34,139,230,0.12)",

    # Borders
    "border_subtle":  "#F1F3F5",
    "border_default": "#DEE2E6",
    "border_strong":  "#228BE6",
    "border":         "#DEE2E6",
    "border_focus":   "#228BE6",
    "border_accent":  "#A5D8FF",

    # Text
    "text_primary":   "#1A1B1E",
    "text_secondary": "#495057",
    "text_muted":     "#868E96",
    "text_disabled":  "#ADB5BD",
    "text_on_accent": "#FFFFFF",
    "text_hover":     "#1A1B1E",

    # Accents — same hues; the darker press shades carry contrast on white
    "accent_primary":       "#228BE6",
    "accent_primary_hover": "#1C7ED6",
    "accent_primary_press": "#1864AB",

    "accent_action":        "#7950F2",
    "accent_action_hover":  "#6741D9",
    "accent_action_press":  "#5F3DC4",

    "accent_success":       "#37B24D",
    "accent_success_hover": "#2F9E44",
    "accent_success_press": "#2B8A3E",

    "accent_warning":       "#F08C00",
    "accent_warning_hover": "#E67700",
    "accent_warning_press": "#D9480F",

    "accent_danger":        "#F03E3E",
    "accent_danger_hover":  "#E03131",
    "accent_danger_press":  "#C92A2A",

    # Brand — the dark-theme cyan is illegible on white, so it darkens
    "brand":     "#0E7490",
    "brand_dim": "#A5F3FC",
    "accent":     "#0E7490",
    "accent_dim": "#A5F3FC",

    # Status readouts — darkened so they stay legible on light surfaces
    "progress_chunk":  "#12B886",
    "timer_label":     "#B7791F",
    "exec_time_done":  "#2F9E44",
    "exec_time_error": "#E03131",

    # ── Legacy button aliases ────────────────────────────────────────────────
    "btn_primary":       "#228BE6",
    "btn_primary_hover": "#1C7ED6",
    "btn_primary_press": "#1864AB",
    "btn_success":       "#37B24D",
    "btn_success_hover": "#2F9E44",
    "btn_success_press": "#2B8A3E",
    "btn_danger":        "#F03E3E",
    "btn_danger_hover":  "#E03131",
    "btn_danger_press":  "#C92A2A",
}

THEMES: Dict[str, Dict[str, str]] = {"dark": DARK, "light": LIGHT}
DEFAULT_THEME = "dark"

_active_theme = DEFAULT_THEME

# ── Live color table ──────────────────────────────────────────────────────────
# Mutated in place by set_theme() so `from ... import COLORS` stays valid.
COLORS: Dict[str, str] = dict(DARK)

# Backward-compat alias — PALETTE is imported by theme.py and all components
PALETTE = COLORS


def set_theme(name: str) -> str:
    """
    Swap the active palette in place. Returns the theme actually applied.

    Only updates the token table — call `theme_manager.apply_theme()` to also
    refresh the stylesheet and already-built widgets.
    """
    global _active_theme
    key = (name or "").lower()
    if key not in THEMES:
        key = DEFAULT_THEME
    COLORS.clear()
    COLORS.update(THEMES[key])
    _active_theme = key
    return key


def current_theme() -> str:
    """Name of the active theme: "dark" or "light"."""
    return _active_theme


def is_dark() -> bool:
    return _active_theme == "dark"


# ── Button semantics documentation ───────────────────────────────────────────
BUTTON_SEMANTICS: Dict[str, str] = {
    "primary":     "Creation/navigation. Ex: + Add Image, + Add Slice, Open.",
    "action":      "Heavy computation. Ex: Run Segmentation, Start Pipeline, Export.",
    "success":     "Confirmation/finalization. Ex: Save, Apply Changes.",
    "secondary":   "Secondary actions. Ex: Cancel, Re-run.",
    "ghost":       "Tertiary actions. Ex: links, + Add Layer.",
    "destructive": "Delete, Clear. Filled only in confirmation dialogs.",
}
