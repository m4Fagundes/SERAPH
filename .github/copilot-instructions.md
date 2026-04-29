# Copilot Instructions - Slicer Lab Pro

## Project Overview
Desktop Python app (Tkinter + Pillow) for high-resolution image slicing. Users visualize large images, overlay a configurable grid, select cells, and export selected regions as individual tiles. Used for ML datasets, scientific imagery, and map processing.

## Architecture

### Two-Class Design
- **`SessaoImagem`** (Data Model): Holds per-image state - original image, preview cache, grid dimensions, zoom/camera position, selected cells. Pure data, no UI.
- **`AppScientificSlicer`** (UI Controller): Tkinter interface that reads from active session and renders to canvas. Manages multiple sessions via sidebar tabs.

### Key Data Flow
```
User Input → Update SessaoImagem state → Call redesenhar() → Render visible viewport only
```

### Performance Patterns
- **LOD System**: Images >2048px generate a downscaled preview (`imagem_preview`). Zoom <0.5 uses preview; higher zoom uses original.
- **Viewport Cropping**: Only the visible region is cropped/resized per frame - never the full image.
- **Pillow safety**: `Image.MAX_IMAGE_PIXELS = None` allows loading massive images.

## Code Conventions

### Naming (Portuguese)
- Classes/methods use Portuguese: `SessaoImagem`, `redesenhar()`, `salvar_selecionados()`
- UI labels mix Portuguese/English for UX
- Variables: `sessao_atual`, `caminho_projeto_atual`, `grid_w`, `grid_h`

### State Management
- Grid dimensions stored in session AND synced from Entry widgets on tab switch
- Always call `trigger_modificacao()` after state changes to enable autosave
- Selection stored as `set` of `(col, row)` tuples

### Platform Handling
```python
self.is_mac = platform.system() == "Darwin"
```
- macOS: Right-click via Button-2 OR Ctrl+Button-1; scroll delta multiplied by 10; **Zoom via ⌘+scroll or ⌥+scroll**
- Windows: Right-click via Button-3; scroll delta divided by 120; **Zoom via Ctrl+scroll**

## Project File Format (.lab)
JSON structure with version, platform origin, active index, and array of image sessions. Supports legacy field names (`gw`/`gh` vs `grid_w`/`grid_h`).

## Development Commands
```bash
# Install dependency
pip install Pillow

# Run application
python main.py
```

## When Modifying

### Adding New Features
1. Add state to `SessaoImagem` if it needs persistence
2. Add UI controls in `_setup_ui()` or `_setup_inputs_grid()`
3. Update `_gravar_arquivo()` and `abrir_projeto()` for serialization
4. Call `trigger_modificacao()` to enable autosave

### Canvas Drawing
All rendering happens in `redesenhar()`. Pattern:
1. Calculate viewport bounds from camera position + zoom
2. Crop/resize only visible portion
3. Draw image, then selections, then grid lines

### Event Bindings
Defined in `_setup_binds()`. Use `self.is_mac` for platform-specific bindings.
