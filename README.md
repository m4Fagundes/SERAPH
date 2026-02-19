# 🔬 Slicer Lab Pro

**Slicer Lab Pro** is a high-performance desktop tool built with **Python (Tkinter + Pillow)** for **visualization, annotation, and slicing of high-resolution images**.

Ideal for **Machine Learning datasets**, **scientific imagery**, **microscopy**, **maps**, or any project that requires splitting large images into precise **tiles** with metadata annotation.

---

## ✨ Features

### 🚀 Performance & Visualization

- **Giant Image Support**  
  Optimized loading for high-resolution images (satellite, microscopy, etc.) without freezing the interface. Uses `Image.MAX_IMAGE_PIXELS = None` to bypass decompression limits.

- **LOD System (Level of Detail)**  
  Automatically generates a preview cache (max 2048px) used during zoom-out (<50%) to keep navigation smooth. Full-resolution rendering is used only when zoomed in.

- **Viewport-Only Rendering**  
  Only the visible portion of the image is cropped and resized for display, significantly reducing memory and CPU usage.

- **Welcome Screen**  
  Clean splash screen with quick-access buttons for **New Project** and **Open Project** on launch.

---

### 🧭 Navigation

- **Pan & Scroll**  
  Left-click and drag to pan the camera. Vertical scroll with mouse wheel, horizontal scroll with `Shift` + mouse wheel.

- **Zoom**  
  Zoom centered on the mouse cursor via `Ctrl` + scroll (Windows) or `⌘/⌥` + scroll (macOS). Toolbar buttons for zoom in (`+`), zoom out (`−`), and fit-to-view (`⟲`).

- **Cross-Platform Controls**  
  Platform-aware keybindings for Windows and macOS, including alternative right-click methods on Mac (`Button-2`, `Ctrl+Click`).

---

### 🛠️ Grid & Slicing

- **Dynamic Grid**  
  Adjust width and height (`W × H`) of the cutting grid in real-time via toolbar inputs. Minimum value of 10px enforced.

- **Customizable Grid Color**  
  Change the grid line color (`🎨` button) for better contrast against any background image. Grid lines are rendered as dashed lines.

- **Smart Cell Selection**  
  Right-click to **add** a cell as an independent slice, or right-click on an existing slice to **subtract** a cell. If subtraction disconnects the slice, it is automatically **split into separate groups** using BFS flood-fill with 4-connectivity.

- **Clear All Selections**  
  Press `C` to clear all selections at once.

- **Multiple Export Formats**  
  Choose from **PNG**, **JPEG**, **TIFF**, **BMP**, or **WebP** via the toolbar dropdown. PNG and WebP exports use transparent backgrounds for non-rectangular slices.

- **Export Selected Slices**  
  Export only selected slice groups as individual files, one per slice.

- **Slice All**  
  Export the entire image divided into grid tiles with a single click. Shows a confirmation dialog with tile count, grid size, and format.

- **Auto Re-export**  
  After the first manual export, any selection change automatically re-exports the slices to the same directory in the same format.

---

### 🔍 Slice Inspector

Click on any slice thumbnail in the sidebar to open a **full-screen detail view**:

- **Full-Resolution Canvas**  
  Navigate the slice at full-resolution with pan (drag) and zoom (scroll). Uses LANCZOS interpolation at normal zoom and nearest-neighbor at high zoom (>200%) for pixel-level inspection.

- **Properties Panel**  
  Displays read-only metadata:
  - **Resolution** — Width × Height in pixels
  - **Rectangles** — Number of rectangles composing the slice
  - **Source** — Original image filename

- **Microns per Pixel (µm/px)**  
  Enter a calibration value to automatically calculate the **physical size** of the slice. Displayed in **µm** or **mm** depending on magnitude.

- **Description**  
  Free-text field to annotate each slice (e.g., sample notes, dataset labels, observations).

- **Persistent Metadata**  
  All inspector data (microns/pixel, description) is saved with the project and stays synchronized with the slice list.

---

### 📋 Slice Preview Panel

- **Sidebar Thumbnails**  
  All selected slices appear as visual thumbnail cards in the sidebar, grouped by source image.

- **Collapsible Groups**  
  Click on a session header to collapse/expand its slice list. Arrow indicators (`▶`/`▼`) show state.

- **Scrollable**  
  Full mouse wheel support for scrolling through long slice lists.

- **Slice Counter**  
  Header displays total slice count across all sessions.

---

### 💾 Project Management

- **Multiple Sessions**  
  Work with multiple images simultaneously. Each image is an independent session with its own grid settings, zoom, camera position, and selections.

- **Project File Format (`.lab`)**  
  Save and load entire projects as JSON. The system persists:
  - Image paths
  - Grid dimensions (`grid_w`, `grid_h`)
  - Zoom level and camera position
  - Selected regions (as rect groups)
  - Slice metadata (descriptions, microns/pixel)
  - Last export directory and format

- **Smart Auto-Save**  
  Projects auto-save 2 seconds after the last modification (debounced). Status bar shows save state (`Modified...` → `Auto-saved`).

- **Project Menu**  
  Dropdown menu with **New Project**, **Open Project**, and **Save As** operations.

- **Backward Compatibility**  
  Supports both legacy field names (`selected_cells`) and current format (`selected_regions`) when loading projects.

---

## 🎮 Shortcuts & Controls

### General Controls
| Action | Command |
|---|---|
| Pan Camera | Left-click + drag |
| Vertical Scroll | Mouse wheel |
| Horizontal Scroll | `Shift` + Mouse wheel |
| Select / Deselect Cell | Right-click |
| Clear All Selections | `C` key |

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
| `✂️ Slice` | Export selected slices |
| `🔲 All` | Export all grid tiles |

### macOS-Specific
- Right-click alternatives: `Button-2` (middle click) or `Ctrl` + Click

---

## 📦 Installation & Running

### Prerequisites
- Python **3.8** or higher
- **Pillow** library

### Setup

Clone the repository:
```bash
git clone https://github.com/your-repo/slicer-lab-pro.git
cd slicer-lab-pro
```

Install dependencies:
```bash
pip install Pillow
```

Run the application:
```bash
python main.py
```

---

## ⚙️ Architecture

The project follows a **4-layer architecture** with clear separation between domain logic and presentation:

```
app/
├── domain/          # Pure data models & business logic
│   ├── session.py   # ImageSession: state per image (grid, zoom, selections, metadata)
│   └── selection.py # Selection math: rect↔cell conversion, BFS splitting, merging
├── application/     # Use-case orchestration
│   └── services.py  # ProjectService (load/save) & ExportService (slice/export)
├── infrastructure/  # I/O operations
│   └── io.py        # File read/write (JSON projects, image tiles)
└── interface/       # Presentation layer
    └── gui/
        ├── main_window.py  # SlicerLabApp: full Tkinter interface
        ├── components.py   # UIComponents: cross-platform button factory + ttk styles
        └── utils.py        # Platform detection (macOS dark mode)
```

### Key Design Decisions

| Aspect | Implementation |
|---|---|
| **State Management** | `ImageSession` holds all per-image state in RAM, independent of rendering |
| **LOD Cache** | Preview images generated at load time (max 2048px, LANCZOS resample) |
| **Selection Model** | Slices stored as sets of pixel-rect tuples `(x1, y1, x2, y2)` |
| **Smart Splitting** | Cell subtraction uses BFS flood-fill to detect disconnected components |
| **Cross-Platform UI** | `UIComponents` factory creates `ttk.Button` on macOS, `tk.Button` on Windows |
| **Auto-Save** | 2-second debounced timer via `root.after()` |

### Project File Format (`.lab`)

```json
[
  {
    "path": "/path/to/image.png",
    "grid_w": 1000,
    "grid_h": 1000,
    "selected_regions": [[[0, 0, 1000, 1000]], [[1000, 0, 2000, 1000]]],
    "slice_metadata": [
      {"description": "Sample A", "microns_per_pixel": "0.5"},
      {"description": "Sample B", "microns_per_pixel": ""}
    ],
    "export_dir": "/path/to/exports",
    "export_format": ".png",
    "zoom_level": 0.85,
    "camera_x": 120.0,
    "camera_y": 45.0
  }
]
```

---

## 🖥️ UI Layout

### Main Grid View
```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ [📁 Project ▾] │ W:[____] H:[____] [🎨] │ [− 100% + ⟲] │ [PNG▾] │ [✂️ Slice] [🔲 All] │
├──────────┬──────────────────────────────────────────────────────────────────────────────┤
│ PROJECT  │                                                                              │
│ /IMAGES  │                                                                              │
│          │                                                                              │
│ ☐ img1   │                    Main Canvas                                               │
│ ☑ img2   │                   (Viewport)                                                 │
│          │                                                                              │
│[+Add Img]│                                                                              │
│──────────│                                                                              │
│ SLICES(2)│                                                                              │
│          │                                                                              │
│ ▼ img2(2)│                                                                              │
│ ┌──────┐ │                                                                              │
│ │thumb1│ │                                                                              │
│ │512x512│ │                                                                              │
│ ┌──────┐ │                                                                              │
│ │thumb2│ │                                                                              │
│ │1024x5│ │                                                                              │
├──────────┴──────────────────────────────────────────────────────────────────────────────┤
│ Status: Image: example.png | Size: 4096×4096px                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Slice Inspector View
```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ [← Back to Grid]    Slice 1 — image.png                         512×512 px   100%       │
├──────────────────────────────────────────────────────────────────┬────────────────────────┤
│                                                                  │ PROPERTIES             │
│                                                                  │                        │
│                                                                  │ Resolution             │
│                     Full-Res Canvas                              │ 512 × 512 px           │
│                    (Pan + Zoom)                                  │                        │
│                                                                  │ Rectangles             │
│                                                                  │ 1 rect(s)              │
│                                                                  │                        │
│                                                                  │ Source                  │
│                                                                  │ image.png              │
│                                                                  │────────────────────────│
│                                                                  │ Microns / pixel        │
│                                                                  │ [0.5_________]         │
│                                                                  │ 256.0 × 256.0 µm      │
│                                                                  │────────────────────────│
│                                                                  │ DESCRIPTION            │
│                                                                  │ [___________________]  │
│                                                                  │ [___________________]  │
├──────────────────────────────────────────────────────────────────┴────────────────────────┤
│ Status: Image: example.png | Size: 4096×4096px                                           │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🖥️ Cross-Platform Support

| Feature | Windows | macOS |
|---|---|---|
| Button rendering | `tk.Button` with Segoe UI | `ttk.Button` with native styling |
| Zoom shortcut | `Ctrl` + Scroll | `⌘` / `⌥` + Scroll |
| Right-click | `Button-3` | `Button-2` or `Ctrl+Click` |
| Dark mode | Always dark theme | Detects system dark mode |
| Window size | 1400×900 default | 1400×900 default |

---

## 📝 License

MIT License — See [LICENSE](LICENSE) for details.
