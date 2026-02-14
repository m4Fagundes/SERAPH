# 🔬 Slicer Lab Pro

**Slicer Lab Pro** is a high-performance desktop tool built with **Python (Tkinter + Pillow)** for **visualization, annotation, and slicing of high-resolution images**.

Ideal for **Machine Learning datasets**, **scientific imagery**, **maps**, or any project that requires splitting large images into specific **tiles**.

---

## ✨ Main Features

### 🚀 Performance & Visualization
- **Giant Image Support**  
  Optimized loading for high-resolution images (satellite, microscopy, etc.) without freezing the interface.

- **LOD System (Level of Detail)**  
  Visual cache implementation that renders low-resolution previews during zoom-out to keep navigation smooth.

- **Intuitive Navigation**  
  Zoom and Pan similar to CAD software or maps (e.g., Google Maps).

- **Cross-Platform**  
  Full support for **macOS** (including Apple Silicon M1/M2/M3) and **Windows** with platform-specific optimizations.

---

### 🛠️ Editing & Slicing
- **Dynamic Grid**  
  Adjust width and height (W × H) of the cutting grid in real-time.

- **Cell Selection**  
  Right-click to select/deselect specific areas for export. Selected cells display with a semi-transparent cyan overlay.

- **Customizable Colors**  
  Change grid color for better contrast with the background image.

- **Multiple Export Formats**  
  Choose your preferred format: **PNG**, **JPEG**, **TIFF**, **BMP**, or **WebP**.

- **Slice All**  
  Export the entire image divided into grid tiles with a single click.

---

### 🔍 Slice Inspector
- **Interactive Thumbnails**  
  Click on any grid cell to open a detailed inspection view without exporting.

- **High-Res Preview**  
  Examine full-resolution details of specific tiles instantly.

- **Physical Measurements**  
  Define **Microns per Pixel (µm/px)** to automatically calculate real-world dimensions for each slice.

- **Metadata Annotation**  
  Add custom descriptions to specific tiles/slices, useful for dataset labeling or scientific notes.

- **Data Persistence**  
  All inspector data (descriptions, resolution settings) is saved directly within the `.lab` project file.

---

### 💾 Project Management
- **Multiple Sessions**  
  Work with multiple images simultaneously via sidebar tabs.

- **Data Persistence (JSON)**  
  Save and load entire projects (`.lab` files).  
  The system preserves:
  - Grid settings  
  - Zoom level  
  - Camera position  
  - Selections for each image  
  - Export format preference

- **Smart Auto-Save**  
  Project automatically saves after changes, preventing data loss.

- **Project Menu**  
  Quick access dropdown menu for New Project, Open, and Save operations.

- **Batch Export**  
  Export only selected cells or all grid tiles as individual image files.

---

## 🎮 Shortcuts & Controls

### General Controls
| Action | Command |
|--------|---------|
| Pan Camera | Left-click and drag |
| Vertical Scroll | Mouse wheel |
| Horizontal Scroll | `Shift` + Mouse wheel |
| Select Cell | Right-click |
| Clear Selection | `C` key |

### Zoom Controls
| Platform | Command |
|----------|---------|
| **macOS** | `⌘ Command` + Scroll or `⌥ Option` + Scroll |
| **Windows** | `Ctrl` + Scroll |

> **Tip:** Use the visual zoom buttons (−/+/⟲) in the toolbar if scroll zoom doesn't work on your system.

### macOS-Specific
- Right-click alternatives: `Button-2` (middle click) or `Ctrl` + Click

---

## 📦 Installation & Running

### Prerequisites
- Python **3.8** or higher  
- **Pillow** library

### Step by Step

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

## ⚙️ Technical Details

### Architecture

The project follows a clear separation between **Data Logic** and **Graphical Interface**, avoiding state bugs:

#### Backend (`ImageSession`)
Class responsible for maintaining the "pure" state of each image:
- Real dimensions (`real_width`, `real_height`)
- File paths
- Grid settings (`grid_w`, `grid_h`, `grid_color`)
- Selected cells list
- Zoom level and camera position

Data remains in RAM, independent of rendering.

#### Frontend (`SlicerLabApp`)
Tkinter interface that reads data from the active session and draws on the Canvas.

### Image Optimization

To handle `DecompressionBombError` with large images:
```python
Image.MAX_IMAGE_PIXELS = None
```

### Dynamic Crop & Resize
- Only the visible portion of the image (Viewport) is processed
- Significant reduction in memory and CPU usage
- LOD system uses preview images for zoom levels < 50%

### Project File Format (`.lab`)
JSON structure with:
```json
{
  "version": "2.2",
  "platform": "Darwin",
  "active_index": 0,
  "export_format": ".png",
  "images": [...]
}
```
Backward compatible with legacy field names.

---

## 🖥️ UI Layout

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ [📁 Project ▾] │ W:[____] H:[____] [🎨] │ [− 100% + ⟲] │ [PNG▾] │ [✂️ Slice] [🔲 All] │
├──────────┬─────────────────────────────────────────────────────────────────────────────┤
│ PROJECT  │                                                                             │
│ /IMAGES  │                                                                             │
│          │                    Canvas                                                   │
│ ☐ img1   │                  (Viewport)                                                 │
│ ☑ img2   │                                                                             │
│          │                                                                             │
│[+Add Img]│                                                                             │
├──────────┴─────────────────────────────────────────────────────────────────────────────┤
│ Status: Image: example.png | Size: 4096×4096px                                         │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---
