# SERAPH Design System

Single source of truth for all UI tokens, component rules, and usage guidelines.
Token definitions live in `app/interface/gui/design_system.py`.

---

## Color Tokens

| Token | Value | Purpose |
|---|---|---|
| `bg_canvas` | `#111111` | Image/canvas area background |
| `bg_surface` | `#1A1B1E` | Base window background |
| `bg_elevated` | `#25262B` | Elevated surfaces (selected cards) |
| `bg_panel` | `#2C2E33` | Sidebars, docks, toolbars |
| `bg_control` | `#373A40` | Inputs, neutral buttons, dropdowns |
| `bg_hover` | `#404652` | Hover overlay for any control |
| `bg_selected` | `rgba(34,139,230,0.12)` | Selection overlay |
| `border_default` | `#373A40` | Default separator / border |
| `border_strong` | `#228BE6` | Focus ring |
| `text_primary` | `#E9ECEF` | Body text |
| `text_secondary` | `#C1C2C5` | Secondary labels |
| `text_muted` | `#909296` | Section headers, hints |
| `text_disabled` | `#5C5F66` | Disabled state |
| `accent_primary` | `#228BE6` | Blue — Add, Open, Select |
| `accent_action` | `#7950F2` | Purple — Run, Execute, Process |
| `accent_success` | `#40C057` | Green — Save, Apply, Done |
| `accent_warning` | `#F59F00` | Yellow — reversible alerts |
| `accent_danger` | `#FA5252` | Red — Delete, Remove, Clear |
| `brand` | `#15AABF` | SERAPH cyan brand color |

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
- [x] No inline `setStyleSheet` on buttons using semantic variants — use objectName  *(main_window.py migrated: add_btn, add_tile_btn, btn_run)*
- [x] Button colors follow semantics table above  *(PrimaryButton=blue, SuccessButton=green)*
- [x] Dynamic swatches (slice color) may use inline `setStyleSheet` — this is the only exception
- [x] All new components import tokens from `design_system.py`, not from `theme.py`  *(slice_previews.py FONT_FAMILY fixed)*
- [x] `theme.py` imports re-exported for backward compat (`PALETTE = COLORS`)
- [x] New widgets live in `app/interface/gui/widgets/` and are exported from `__init__.py`
