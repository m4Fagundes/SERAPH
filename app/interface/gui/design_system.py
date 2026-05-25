"""
SERAPH Design System — Single source of truth for all UI tokens.

Import from here in all components:
    from app.interface.gui.design_system import COLORS, SPACE, SIZE, RADIUS, FONT_FAMILY
    from app.interface.gui.design_system import PALETTE  # backward compat alias
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

# ── Color tokens — semantic ───────────────────────────────────────────────────
COLORS: Dict[str, str] = {
    # Backgrounds — darkest to lightest
    "bg_canvas":   "#0D0F12",     # image area
    "bg_surface":  "#181A20",     # base window
    "bg_elevated": "#20232A",     # elevated surface
    "bg_panel":    "#252932",     # sidebars, docks
    "bg_control":  "#303640",     # inputs, neutral buttons
    "bg_hover":    "#3A424D",     # hover overlay
    "bg_selected": "rgba(34,139,230,0.12)",  # selection overlay

    # Borders
    "border_subtle":  "#252932",
    "border_default": "#343B46",
    "border_strong":  "#228BE6",  # focus ring

    # Text
    "text_primary":   "#E9ECEF",
    "text_secondary": "#C1C2C5",
    "text_muted":     "#909296",
    "text_disabled":  "#5C5F66",
    "text_on_accent": "#FFFFFF",

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

    # Canvas specific
    "canvas_bg": "#0D0F12",
    "tile_bg":   "#111317",

    # Splash screen
    "splash_bg":     "#0d1117",
    "splash_border": "#1e4060",
    "splash_title":  "#4FC3F7",
    "splash_sub":    "#8899aa",
    "splash_status": "#3a5a70",

    # ── Legacy compatibility — DO NOT remove; imported across codebase ────────
    "bg_base":       "#181A20",
    "bg_surface":    "#20232A",
    "border":        "#343B46",
    "border_focus":  "#228BE6",
    "border_accent": "#1a4d8c",
    "accent":        "#22D3EE",
    "accent_dim":    "#164E63",
    "btn_primary":         "#228BE6",
    "btn_primary_hover":   "#339AF0",
    "btn_primary_press":   "#1971C2",
    "btn_success":         "#40C057",
    "btn_success_hover":   "#51CF66",
    "btn_success_press":   "#2F9E44",
    "btn_danger":          "#FA5252",
    "btn_danger_hover":    "#FF6B6B",
    "btn_danger_press":    "#E03131",
    "btn_nuclei":          "#c2185b",
    "btn_nuclei_hover":    "#e91e63",
    "btn_nuclei_press":    "#880e4f",
    "btn_hdf5":            "#7c3aed",
    "btn_hdf5_hover":      "#8b5cf6",
    "btn_hdf5_press":      "#6d28d9",
    "progress_chunk":      "#00d68f",
    "timer_label":         "#F1C40F",
    "exec_time_done":      "#00FF88",
    "exec_time_error":     "#E74C3C",
}

# Backward-compat alias — PALETTE is imported by theme.py and all components
PALETTE = COLORS

# ── Button semantics documentation ───────────────────────────────────────────
BUTTON_SEMANTICS: Dict[str, str] = {
    "primary":     "Creation/navigation. Ex: + Add Image, + Add Slice, Open.",
    "action":      "Heavy computation. Ex: Run Segmentation, Start Pipeline, Export.",
    "success":     "Confirmation/finalization. Ex: Save, Apply Changes.",
    "secondary":   "Secondary actions. Ex: Cancel, Re-run.",
    "ghost":       "Tertiary actions. Ex: links, + Add Layer.",
    "destructive": "Delete, Clear. Filled only in confirmation dialogs.",
}
