# SERAPH Design System

Single source of truth for all UI tokens, component rules, and usage guidelines.
Token definitions live in `app/interface/gui/design_system.py`.

---

## Themes

Two palettes ship: **dark** (default) and **light**. `COLORS` is a *live* dict —
`set_theme()` mutates it in place, so `from ... import COLORS` stays valid across a
switch. Users flip themes at **View → Theme**; the choice persists via `QSettings`.

The **image viewport stays dark in both themes** (`canvas_bg`, `tile_bg`). A dark
backdrop maximises perceived contrast on tissue and keeps segmentation overlay
colors reading the same way regardless of the surrounding chrome. Everything else
— docks, menus, toolbars, panels, the welcome page — follows the theme.

### Writing theme-aware widgets

Read colors at style-application time, never at import time. A pre-formatted string
freezes the palette it was built with.

```python
from app.interface.gui.theme_manager import themed

# Right — re-applied automatically on every theme switch
themed(lbl, lambda: f"color: {COLORS['text_muted']}; font-size: 11px;")

# Wrong — frozen at construction, goes stale the moment the theme flips
lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
```

Calling `themed()` again on the same widget replaces its style function, so
state-dependent styles (selected/idle, active/inactive) work unchanged. Widgets are
held weakly — no unregistering needed. For non-QSS visuals (a painted `QPixmap`),
connect to `theme_manager.theme_changed` and re-render.

Bare `setStyleSheet()` is still fine for **color-free** rules (`background: transparent`)
and for the theme-invariant viewport.

---

## Color Tokens

| Token | Dark | Light | Purpose |
|---|---|---|---|
| `bg_canvas` | `#0D0F12` | `#FFFFFF` | Central content area (behind tabs / welcome) |
| `bg_base` | `#181A20` | `#F1F3F5` | Base window background |
| `bg_surface` / `bg_elevated` | `#20232A` | `#FFFFFF` | Raised / elevated surfaces |
| `bg_panel` | `#252932` | `#F8F9FA` | Sidebars, docks, toolbars |
| `bg_control` | `#303640` | `#FFFFFF` | Inputs, neutral buttons, dropdowns |
| `bg_muted` | `#303640` | `#E9ECEF` | Recessed chips: badges, disabled fills |
| `bg_hover` | `#3A424D` | `#E9ECEF` | Hover overlay for any control |
| `bg_selected` | `rgba(34,139,230,0.12)` | same | Selection overlay |
| `overlay_subtle` / `overlay_hover` | white @ 3% / 7% | black @ 2% / 5% | Tint a surface without knowing its background |
| `border_default` | `#343B46` | `#DEE2E6` | Default separator / border |
| `border_strong` | `#228BE6` | same | Focus ring |
| `text_primary` | `#E9ECEF` | `#1A1B1E` | Body text |
| `text_secondary` | `#C1C2C5` | `#495057` | Secondary labels |
| `text_muted` | `#909296` | `#868E96` | Section headers, hints |
| `text_disabled` | `#5C5F66` | `#ADB5BD` | Disabled state |
| `text_on_accent` | `#FFFFFF` | same | Label on a **filled** accent button |
| `text_hover` | `#FFFFFF` | `#1A1B1E` | Label on a **neutral hover** surface |
| `accent_primary` | `#228BE6` | same | Blue — Add, Open, Select |
| `accent_action` | `#7950F2` | same | Purple — Run, Execute, Process |
| `accent_success` | `#40C057` | `#37B24D` | Green — Save, Apply, Done |
| `accent_warning` | `#F59F00` | `#F08C00` | Yellow — reversible alerts |
| `accent_danger` | `#FA5252` | `#F03E3E` | Red — Delete, Remove, Clear |
| `brand` | `#22D3EE` | `#0E7490` | SERAPH cyan (darkened for legibility on white) |
| `canvas_bg` / `tile_bg` | `#0D0F12` / `#111317` | **unchanged** | Image viewport — dark in every theme |

`text_on_accent` and `text_hover` are distinct on purpose. White is correct on a
filled blue button in both themes; white on a light-grey hover surface is invisible.
Never hard-code `#ffffff` for either.

---

## Spacing Scale

Uses `SPACE[n]` — base unit 4px following Mantine spacing.

| Token | Value | Usage example |
|---|---|---|
| `SPACE[0]` | 0px | No gap |
| `SPACE[1]` | 4px | Icon to text gap |
| `SPACE[2]` | 8px | Button padding (horizontal inner) |
| `SPACE[3]` | 12px | Row margins, card inner padding |
| `SPACE[4]` | 16px | Panel / dock content margins |
| `SPACE[5]` | 24px | Section spacing |
| `SPACE[6]` | 32px | Major section spacing |
| `SPACE[7]` | 48px | Page-level vertical spacing |

---

## Size Scale — Component Heights

| Token | Value | Usage |
|---|---|---|
| `SIZE["xs"]` | 24px | Compact rows, tags, badges |
| `SIZE["sm"]` | 32px | Small buttons, secondary controls |
| `SIZE["md"]` | 36px | Default button and input height |
| `SIZE["lg"]` | 44px | Primary CTA buttons |

---

## Border Radius

| Token | Value |
|---|---|
| `RADIUS["sm"]` | 4px |
| `RADIUS["md"]` | 6px |
| `RADIUS["lg"]` | 8px |
| `RADIUS["full"]` | 999px (pill) |

---

## Button Semantics

Buttons are styled via `objectName` in the global QSS — **no inline `setStyleSheet` on buttons**.

| Class | objectName | Color | Use for |
|---|---|---|---|
| `PrimaryButton` | `btn_primary` | Blue `#228BE6` | Add, Open, Select — creation/navigation |
| `ActionButton` | `btn_action` | Purple `#7950F2` | Run, Execute, Start Pipeline — heavy computation |
| `SuccessButton` | `btn_success` | Green `#40C057` | Save, Apply, Done — confirmation |
| `SecondaryButton` | `btn_secondary` | Outline | Cancel, Re-run — secondary actions |
| `GhostButton` | `btn_ghost` | Text-only | Links, + Add Layer — tertiary |
| `DestructiveButton` | `btn_destructive` | Red outline | Delete, Remove, Clear |

### Code examples

```python
from app.interface.gui.widgets.buttons import ActionButton, PrimaryButton, SecondaryButton

# Run computation
btn_run = ActionButton("Run Segmentation", size="lg")

# Add something
btn_add = PrimaryButton("+ Add Slice")

# Cancel
btn_cancel = SecondaryButton("Cancel")
```

---

## Before / After: "Run All Slices x 3"

### Before (problem)
Three identical `QPushButton("Run All Slices")` rendered side by side with no visual
hierarchy. Users had no way to understand which model would run, and the blue color
matched "Add" actions (wrong semantic).

```
[Cellpose (cpsam)]  [Run All Slices]   <- blue button
[NuClick (PyTorch)] [Run All Slices]   <- blue button
[CellViT-SAM]       [Run All Slices]   <- blue button
```

### After (Option B — radio cards + single ActionButton)
Selectable model cards with a single purple ActionButton at the bottom. Clear semantic:
purple = computation. Disabled until a model is selected.

```
[ Cellpose (cpsam)       ]  <- selected: left border accent_action
  cpsam · CUDA

[ NuClick (PyTorch)      ]
  PyTorch

[ CellViT-SAM            ]
  ViT-SAM

[    Run on all slices    ]  <- ActionButton, purple, SIZE["lg"], disabled if none selected
```

---

## Conformance Checklist

- [ ] No magic numbers — use `SPACE[n]`, `SIZE["key"]`, `RADIUS["key"]`, `COLORS["key"]`
- [x] Color-bearing inline styles go through `themed(widget, style_fn)` so they survive a theme switch
- [x] No hard-coded `#ffffff` / `color: white` — use `text_on_accent` or `text_hover`
- [x] No inline `setStyleSheet` on buttons using semantic variants — use objectName  *(main_window.py migrated: add_btn, add_tile_btn, btn_run)*
- [x] Button colors follow semantics table above  *(PrimaryButton=blue, SuccessButton=green)*
- [x] Dynamic swatches (slice color) may use inline `setStyleSheet` — this is the only exception
- [x] All new components import tokens from `design_system.py`, not from `theme.py`  *(slice_previews.py FONT_FAMILY fixed)*
- [x] `theme.py` imports re-exported for backward compat (`PALETTE = COLORS`)
- [x] New widgets live in `app/interface/gui/widgets/` and are exported from `__init__.py`
