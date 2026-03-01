# 🔬 Tiles Grid Analyzer

**Tiles Grid Analyzer** is a high-performance desktop tool built with **Python (Tkinter + Pillow + pyvips)** for **visualization, annotation, and slicing of high-resolution images**.

Ideal for **Machine Learning datasets**, **scientific imagery**, **microscopy**, **maps**, or any project that requires splitting large images into precise **tiles** with metadata annotation.

---

## ✨ Features

### 🚀 Performance & Visualization

- **Giant Image Support**  
  On-demand loading for images of any size (200k×200k+) — opens instantly with no pre-build step. Uses `pyvips` for lazy random-access and `OpenSlide` for whole-slide formats (`.ndpi`, `.svs`, `.mrxs`, etc.).

- **3-Tier Zoom Quality**  
  - **< 50% zoom** — Lossy: reads from a lower-resolution pyramid level for speed  
  - **50–94% zoom** — Lossless: crops from original and resizes via Lanczos  
  - **≥ 94% zoom** — Full-res: pixel-perfect original data (nearest-neighbor at > 200%)

- **Viewport-Only Rendering**  
  Only the visible portion of the image is decoded, significantly reducing memory and CPU usage.

- **Welcome Screen**  
  Clean splash screen with quick-access buttons for **New Project** and **Open Project** on launch. Blocks interaction until a project is opened or created.

---

### 🧭 Navigation

- **Pan & Scroll**  
  Left-click and drag to pan the camera. Vertical scroll with mouse wheel, horizontal scroll with `Shift` + mouse wheel.

- **Zoom**  
  Zoom centered on the mouse cursor via `Ctrl` + scroll (Windows) or `⌘/⌥` + scroll (macOS). Toolbar buttons for zoom in (`+`), zoom out (`−`), and fit-to-view (`⟲`).

- **Cross-Platform Controls**  
  Platform-aware keybindings for Windows and macOS, including alternative right-click methods on Mac (`Button-2`, `Ctrl+Click`).

---

### 🛠️ Grid & Tiling

- **Dynamic Grid**  
  Adjust width and height (`W × H`) of the cutting grid in real-time via toolbar inputs. Minimum value of 10px enforced.

- **Customizable Grid Color**  
  Change the grid line color (`🎨` button) for better contrast against any background image.

- **Smart Cell Selection**  
  Right-click to **add** a cell as an independent tile, or right-click on an existing tile to **subtract** a cell. If subtraction disconnects the tile, it is automatically **split into separate groups** using BFS flood-fill with 4-connectivity.

- **Rubber-Band Selection** *(new)*  
  Right-click and drag to draw a selection rectangle. All grid cells inside the rectangle become a single tile — much faster than clicking cell by cell.

- **Distinct Colors per Tile** *(new)*  
  Each tile is automatically assigned a distinct color from a 10-color palette (cyan, coral, green, yellow, purple, orange, blue, pink, teal, lime). Colors are shown on the canvas, in sidebar cards, and persist with the project.

- **Freehand Brush Tool**  
  Switch to **Brush** mode to draw arbitrary polygon regions. Supports transparent export with polygon masks.

- **Clear All Selections**  
  Press `C` to clear all selections at once.

- **Multiple Export Formats**  
  Choose from **PNG**, **JPEG**, **TIFF**, **BMP**, or **WebP** via the toolbar dropdown.

- **Export with Progress Bar** *(new)*  
  Exports run in a background thread with a modal progress dialog showing current/total count and percentage.

- **Auto Re-export**  
  After the first manual export, any selection change automatically re-exports the tiles to the same directory.

---

### 🔬 Scientific Features *(new)*

- **Tile Names**  
  Give each tile a descriptive label (e.g., "Sample A — Region 3") via the inspector. Names appear in the sidebar cards and inspector header.

- **Metadata Export (CSV + JSON)**  
  When exporting tiles, a `_metadata.csv` and `_metadata.json` file are automatically generated with: tile index, name, bounding box, size (px), microns/pixel, physical size (µm/mm), description, and source image.

- **Scale Bar**  
  When `microns/pixel` is set for any tile, a scale bar overlay appears in the bottom-right corner of the canvas. Auto-selects the best unit (µm or mm) and bar length based on current zoom.

---

### ↩️ Undo/Redo *(new)*

- **Stack-Based History**  
  Full undo/redo support for all tile operations (add, delete, clear, rubber-band select). Stores up to 50 snapshots per session with deep-copy isolation.

- **Keyboard Shortcuts**  
  `Ctrl+Z` to undo, `Ctrl+Y` to redo. History is cleared on project open/new.

---

### 🔍 Tile Inspector

Click on any tile thumbnail in the sidebar to open a **full-screen detail view**:

- **Full-Resolution Canvas**  
  Navigate the tile at full-resolution with pan (drag) and zoom (scroll).

- **Tile Name** *(new)*  
  Editable text field at the top of the properties panel.

- **Properties Panel**  
  - **Resolution** — Width × Height in pixels  
  - **Rectangles** — Number of rectangles composing the tile  
  - **Source** — Original image filename  

- **Microns per Pixel (µm/px)**  
  Enter a calibration value to automatically calculate the **physical size** of the tile. Displayed in **µm** or **mm** depending on magnitude.

- **Description**  
  Free-text field to annotate each tile (e.g., sample notes, dataset labels, observations).

- **Persistent Metadata**  
  All inspector data (name, microns/pixel, description) is saved with the project.

---

### 📋 Tile Preview Panel

- **Sidebar Thumbnails**  
  All selected tiles appear as visual thumbnail cards in the sidebar, grouped by source image.

- **Color Dot Indicator** *(new)*  
  Each card shows a colored dot matching its tile color on the canvas.

- **Custom Names** *(new)*  
  Cards display the custom tile name if set, otherwise "Tile N".

- **Collapsible Groups**  
  Click on a session header to collapse/expand its tile list.

- **Scrollable**  
  Full mouse wheel support for scrolling through long tile lists.

---

### 💾 Project Management

- **Multiple Sessions**  
  Work with multiple images simultaneously. Each image is an independent session.

- **Project File Format (`.lab`)**  
  Save and load entire projects as JSON. Persists:
  - Image paths (relative + absolute)
  - Grid dimensions, zoom, camera position
  - Selected regions (as rect groups)
  - Tile metadata (name, description, microns/pixel)
  - Tile colors
  - Polygon data (brush-drawn tiles)
  - Export directory and format

- **Smart Auto-Save**  
  Projects auto-save 2 seconds after the last modification (debounced).

- **Project Sharing**  
  Projects use relative image paths, enabling sharing between machines when images are in the same relative location.

---

## 🎮 Shortcuts & Controls

### General Controls
| Action | Command |
|---|---|
| Pan Camera | Left-click + drag |
| Vertical Scroll | Mouse wheel |
| Horizontal Scroll | `Shift` + Mouse wheel |
| Select Cell / Rubber-band Select | Right-click (click or drag) |
| Clear All Selections | `C` key |
| Undo | `Ctrl+Z` |
| Redo | `Ctrl+Y` |
| Save Project | `Ctrl+S` |
| Open Project | `Ctrl+O` |
| New Project | `Ctrl+N` |
| Delete Selected Tile | `Delete` |

### Zoom Controls
| Platform | Command |
|---|---|
| **Windows** | `Ctrl` + Scroll |
| **macOS** | `⌘ Command` + Scroll or `⌥ Option` + Scroll |

### Toolbar Buttons
| Button | Action |
|---|---|
| `−` | Zoom out |
| `+` | Zoom in |
| `⟲` | Fit image to view |
| `🎨` | Change grid color |
| `✂️ Tile` | Export selected tiles |
| `🔲 All` | Export all grid tiles |

### macOS-Specific
- Right-click alternatives: `Button-2` (middle click) or `Ctrl` + Click

---

## 📦 Installation & Running

### Prerequisites
- Python **3.8** or higher
- **Pillow** — image manipulation
- **pyvips** — on-demand large image reading (recommended)
- **openslide-python** + **openslide-bin** — whole-slide image support (`.ndpi`, `.svs`, etc.)

> **Note:** `pyvips` and `openslide` are optional but strongly recommended. Without them, only PIL-supported formats will work and large images may be slow.

### Setup

Clone the repository:
```bash
git clone https://github.com/your-repo/tiles-grid-analyzer.git
cd tiles-grid-analyzer
```

Install dependencies:

#### Windows
```powershell
pip install Pillow pyvips openslide-bin openslide-python
```

#### macOS
```bash
brew install vips openslide
pip install Pillow pyvips openslide-python
```

> On macOS, `vips` and `openslide` must be installed via Homebrew first because the Python packages are wrappers around the C libraries.

### Run the application

#### Windows
```powershell
python main.py
```

#### macOS
```bash
python3 main.py
```

### Run tests
```bash
python tests/test_selection.py
python tests/test_history.py
python tests/test_services.py
```

---

## ⚙️ Architecture

The project follows a **4-layer architecture** with clear separation between domain logic and presentation:

```
app/
├── domain/          # Pure data models & business logic
│   ├── session.py   # ImageSession: state per image (grid, zoom, selections, metadata, colors)
│   ├── selection.py # Selection math: rect↔cell conversion, BFS splitting, merging
│   ├── history.py   # UndoManager: stack-based undo/redo with deep-copy snapshots
│   └── pyramid.py   # ImagePyramid: on-demand region reader (pyvips + OpenSlide)
├── application/     # Use-case orchestration
│   └── services.py  # ProjectService (load/save) & ExportService (slice/export/metadata)
├── infrastructure/  # I/O operations
│   └── io.py        # File read/write (JSON projects, image tiles)
└── interface/       # Presentation layer
    └── gui/
        ├── main_window.py  # SlicerLabApp: full Tkinter interface
        ├── components.py   # UIComponents: cross-platform button factory + ttk styles
        └── utils.py        # Platform detection (macOS dark mode)
tests/
├── test_selection.py  # Unit tests for selection math
├── test_history.py    # Unit tests for undo/redo
└── test_services.py   # Integration tests for project save/load
```

### Key Design Decisions

| Aspect | Implementation |
|---|---|
| **Image Loading** | On-demand via `pyvips` (random access) or `OpenSlide` (pyramid levels). No pre-build step. |
| **State Management** | `ImageSession` holds all per-image state in RAM, independent of rendering |
| **Selection Model** | Tiles stored as sets of pixel-rect tuples `(x1, y1, x2, y2)` |
| **Undo/Redo** | Stack-based deep-copy snapshots (max 50). Captures cells, polygons, metadata, and colors. |
| **Smart Splitting** | Cell subtraction uses BFS flood-fill to detect disconnected components |
| **Tile Colors** | 10-color auto-cycling palette, persisted in project file |
| **Cross-Platform UI** | `UIComponents` factory creates `ttk.Button` on macOS, `tk.Button` on Windows |
| **Auto-Save** | 2-second debounced timer via `root.after()` |
| **Export** | Threaded with progress callback; metadata exported as CSV + JSON |

### Project File Format (`.lab`)

```json
[
  {
    "path": "relative/path/to/image.png",
    "abs_path": "/absolute/path/to/image.png",
    "grid_w": 1000,
    "grid_h": 1000,
    "selected_regions": [[[0, 0, 1000, 1000]], [[1000, 0, 2000, 1000]]],
    "selected_polygons": [null, [[100, 100], [200, 150], [150, 200]]],
    "slice_metadata": [
      {"name": "Sample A", "description": "Region of interest", "microns_per_pixel": "0.5"},
      {"name": "Sample B", "description": "", "microns_per_pixel": ""}
    ],
    "tile_colors": ["#00FFFF", "#FF6B6B"],
    "grid_color": "#FFFF00",
    "export_dir": "relative/path/to/exports",
    "export_format": ".png",
    "zoom_level": 0.85,
    "camera_x": 120.0,
    "camera_y": 45.0
  }
]
```

---

## 🖥️ Cross-Platform Support

| Feature | Windows | macOS |
|---|---|---|
| Button rendering | `tk.Button` with Segoe UI | `ttk.Button` with native styling |
| Zoom shortcut | `Ctrl` + Scroll | `⌘` / `⌥` + Scroll |
| Right-click | `Button-3` | `Button-2` or `Ctrl+Click` |
| Dark mode | Always dark theme | Detects system dark mode |
| Dependencies | `pip install` only | Requires `brew install vips openslide` first |

---

## 📝 License

MIT License — See [LICENSE](LICENSE) for details.
