# Cellpose Segmentation Exploration Report
## grid-image-analyzer Codebase

**Date:** May 1, 2026  
**Scope:** Complete mapping of Cellpose integration across production code, tests, and notebooks

---

## Executive Summary

The grid-image-analyzer project implements Cellpose nucleus segmentation through a **Clean Architecture pattern** with clear separation:

- **Infrastructure Layer:** [app/infrastructure/ml_models/cellpose_adapter.py](app/infrastructure/ml_models/cellpose_adapter.py) — CellposeAdapter class
- **Domain Port:** [app/domain/interfaces/batch_segmentation_model.py](app/domain/interfaces/batch_segmentation_model.py) — IBatchSegmentationModel interface
- **Application Service:** [app/application/batch_segmentation_service.py](app/application/batch_segmentation_service.py) — BatchSegmentationService
- **GUI Integration:** [app/interface/gui/main_window.py](app/interface/gui/main_window.py) — Composition root and adapter registration
- **Analysis Notebook:** [main.ipynb](main.ipynb) — Post-processing and visualization of Cellpose output

---

## 1. Cellpose Segmentation Implementation

### 1.1 CellposeAdapter Class

**File:** [app/infrastructure/ml_models/cellpose_adapter.py](app/infrastructure/ml_models/cellpose_adapter.py)  
**Class:** `CellposeAdapter(IBatchSegmentationModel)`

**Purpose:** Encapsulates all Cellpose-specific logic (model loading, inference, mask processing) behind the domain port interface.

#### Constructor Parameters

```python
CellposeAdapter(
    model_type: str = "nuclei",         # "nuclei", "cyto", "cyto2", etc.
    gpu: Optional[bool] = None,         # None = auto-detect from config
    flow_threshold: float = 0.4,        # Flow error threshold
    cellprob_threshold: float = 0.0,    # Cell probability threshold
    min_size: int = 15,                 # Minimum mask area (pixels)
    config_override: Optional[dict] = None  # Override specific settings
)
```

#### Key Configuration Settings

Configuration is loaded from `app/infrastructure/config/performance_config.py`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `batch_size` | 8-16 | Internal Cellpose batch size (256 GPU, 8 CPU) |
| `resample_factor` | 1.0 | Optional pre-segmentation downsampling |
| `timeout_seconds` | 60 | Max inference time (watchdog) |
| `max_tile_size_pixels` | 1024 | Threshold for auto-tiling large images |
| `memory_limit_mb` | 4096 | Memory usage watchdog |
| `use_gpu` | Auto-detected | GPU/CPU decision |
| `gpu_fallback_enabled` | True | Fallback to CPU if GPU fails |

#### Lazy-Loading Pattern

The model is **NOT** loaded at initialization. Instead:

```python
def segment(self, image, diameter=None, ...):
    self._ensure_model_loaded()  # First call triggers import
    # ... inference happens here
```

**Rationale:** Importing cellpose (+ torch, numpy, cv2) at app startup can cause DLL conflicts with PyQt6 on Windows. Deferring to first use prevents this.

---

### 1.2 Complete Segmentation Pipeline

#### Step 1: Input Validation
- Accepts PIL Image (RGB) or NumPy array (uint8)
- Converts all inputs to NumPy format: (H, W, 3) or (H, W)

#### Step 2: H&E Preprocessing
Essential for nucleus detection in stained histology:

```python
# Extract blue channel (hematoxylin absorbs in blue)
blue_channel = img[:, :, 2].astype(np.float32)

# Invert: hematoxylin stain → dark nuclei become bright
inverted = 255.0 - blue_channel

# Normalize to 0-255
img_processed = inverted.astype(np.uint8)
```

#### Step 3: Resample (Optional)
If configured `resample_factor < 1.0`:

```python
# Downscale image before processing (faster, less memory)
new_width = int(width * self._resample_factor)
new_height = int(height * self._resample_factor)
# Use OpenCV INTER_LANCZOS4 for high quality
```

#### Step 4: Large Image Tiling
If image exceeds `max_tile_size` (default 1024px):

```python
tiles = []
for y in range(0, height, max_size):
    for x in range(0, width, max_size):
        tile = image[y:y+max_size, x:x+max_size]
        tiles.append((tile, x, y))  # Store offset for reconstruction
```

#### Step 5: Cellpose Model Inference

**GPU-Optimized Batch Size:**
- GPU: batch_size = 256 (saturate VRAM)
- CPU: batch_size = 8 (conservative)

```python
from cellpose import models as cp_models

model = cp_models.CellposeModel(
    model_type="nuclei",
    gpu=self._gpu  # True or False
)

masks, flows, styles = model.eval(
    img_processed,
    diameter=diameter or None,        # None = auto-estimate
    flow_threshold=0.4,               # Quality filter
    cellprob_threshold=0.0,           # Probability filter
    min_size=15,                      # Filter tiny objects
    channels=[0, 0],                  # Grayscale (already preprocessed)
    batch_size=256 if gpu else 8
)
```

**Returns:**
- `masks`: 2D NumPy array (H, W) — each pixel = label ID (0 = background)
- `flows`: 3D tuple of optical flow fields
- `styles`: Style vector for custom training

#### Step 6: Timeout Protection

Cellpose can hang on problematic images. Protection implemented:

```python
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(self._segment_single_image, image, ...)
    try:
        polygons = future.result(timeout=self._timeout_seconds)
    except concurrent.futures.TimeoutError:
        logger.error("Cellpose timed out after %d seconds", timeout)
        future.cancel()
        return []  # Return empty, don't crash GUI
```

#### Step 7: Mask-to-Polygon Conversion

Optimized contour extraction using OpenCV:

```python
def _masks_to_polygons(masks) -> List[List[Tuple[int, int]]]:
    """Convert 2D label array to list of polygon boundaries."""
    
    polygons = []
    
    # Optimization: get bounding box per label (avoid O(N·W·H))
    slices = scipy.ndimage.find_objects(masks)
    
    for i, slc in enumerate(slices):
        if slc is None:
            continue
        
        label = i + 1
        min_y, min_x = slc[0].start, slc[1].start
        
        # Extract ONLY within bounding box
        crop = masks[slc]
        binary = (crop == label).astype(np.uint8) * 255
        
        # Find contours
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        if not contours:
            continue
        
        # Take largest contour (handles multiple contours per label)
        largest = max(contours, key=cv2.contourArea)
        
        # Convert to (x, y) coordinates
        poly = [
            (int(pt[0][0]) + min_x, int(pt[0][1]) + min_y)
            for pt in largest
        ]
        
        # Filter: exclude nuclei touching tile borders
        touches_border = any(
            x <= 0 or y <= 0 or x >= width - 1 or y >= height - 1
            for x, y in poly
        )
        
        if not touches_border and len(poly) >= 3:
            polygons.append(poly)
    
    return polygons
```

**Output Format:**
```python
[
    [(x1, y1), (x2, y2), (x3, y3), ...],  # Nucleus 1 contour
    [(x1, y1), (x2, y2), (x3, y3), ...],  # Nucleus 2 contour
    ...
]
```

---

### 1.3 GPU Detection and Fallback

**Auto-Detection Logic:**

```python
if gpu is None:  # Auto-detect
    self._gpu = config.cellpose.use_gpu and not config.force_cpu_only
else:  # Manual override
    self._gpu = gpu
```

**Fallback on Load Failure:**

If GPU load fails (e.g., BFloat16 unsupported on Apple MPS):

```python
try:
    self._model = cp_models.CellposeModel(
        model_type=model_type,
        gpu=self._gpu  # True
    )
except Exception as e:
    if self._gpu and ("BFloat16" in str(e) or "MPS" in str(e)):
        logger.warning("GPU failed, retrying on CPU...")
        self._gpu = False
        self._model = cp_models.CellposeModel(
            model_type=model_type,
            gpu=False  # Fallback
        )
    else:
        raise
```

---

## 2. Integration with Application Services

### 2.1 BatchSegmentationService

**File:** [app/application/batch_segmentation_service.py](app/application/batch_segmentation_service.py)

This application-layer service:
- Registers one or more batch models (CellposeAdapter instances)
- Orchestrates segmentation requests
- Converts local coordinates → global coordinates

#### Key Methods

```python
class BatchSegmentationService:
    
    def register_model(self, model: IBatchSegmentationModel) -> None:
        """Register a CellposeAdapter or similar."""
        self._models[model.name] = model
    
    def segment(
        self, model_name: str, image: Image,
        diameter: float = None,
        flow_threshold: float = None,
        cellprob_threshold: float = None
    ) -> List[List[Tuple[int, int]]]:
        """Simple segmentation on a PIL Image."""
        model = self._models.get(model_name)
        return model.segment(image, diameter, flow_threshold, cellprob_threshold)
    
    def segment_tile(
        self, model_name: str, session, slice_idx: int,
        diameter: float = None, **kwargs
    ) -> List[List[Tuple[int, int]]]:
        """Full pipeline: extract → segment → convert coordinates."""
        tile = session.tiles[slice_idx]
        bx1, by1, bx2, by2 = tile.bounding_box
        
        # Get region at full resolution
        pil_img = session.pyramid.get_region_fullres(
            bx1, by1, bx2 - bx1, by2 - by1
        )
        
        # Apply tile exclusion masks
        pil_img = tile.get_ml_ready_image(pil_img)
        
        # Run segmentation (returns local coordinates)
        polygons = self.segment(model_name, pil_img, diameter)
        
        # Convert local → global coordinates
        global_polygons = [
            [(px + bx1, py + by1) for px, py in poly]
            for poly in polygons
        ]
        
        return global_polygons
```

### 2.2 GUI Integration (Composition Root)

**File:** [app/interface/gui/main_window.py](app/interface/gui/main_window.py) — Lines ~60–100

```python
class SlicerLabApp(QMainWindow):
    def __init__(self):
        # ... other setup ...
        
        # Composition Root: wire infrastructure into services
        batch_models = []
        try:
            # Create adapter with auto GPU detection
            cellpose_adapter = CellposeAdapter(
                model_type="nuclei",
                gpu=None  # Auto-detect from config
            )
            batch_models.append(cellpose_adapter)
            
            # Log config used
            from app.infrastructure.config.hardware_detector import get_hardware_detector
            detector = get_hardware_detector()
            logger.info(
                "CellposeAdapter initialized: GPU=%s, profile=%s, "
                "cores=%d, memory=%.1fGB",
                cellpose_adapter._gpu,
                detector.get_performance_profile(),
                detector.cpu_cores,
                detector.memory_gb
            )
        except Exception as e:
            logger.error("Failed to load Cellpose: %s", e)
        
        # Register with service
        self.batch_segmentation_service = BatchSegmentationService(
            models=batch_models
        )
```

---

## 3. Main.ipynb Notebook

**File:** [main.ipynb](main.ipynb)

This Jupyter notebook performs **post-processing and analysis** of Cellpose-generated segmentation masks.

### 3.1 Workflow

**Cell 1-2: Setup and Data Loading**
```python
# Mount Google Drive
from google.colab import drive
drive.mount('/content/drive')

# Load image and Cellpose mask
image_file = "/content/drive/My Drive/image_40x_5.tif"
mask_file = "/content/drive/My Drive/image_40x_5_seg.npy"

import imageio.v2 as imageio
image = imageio.imread(image_file)
mask_dict = np.load(mask_file, allow_pickle=True).item()
mask = mask_dict['masks']  # 2D label array
```

**Cell 3: Visualization**
- Plot original RGB image
- Plot Cellpose mask (colored by label ID)
- Overlay masks on original image
- Show contours

```python
fig, axes = plt.subplots(1, 2, figsize=(12, 6))
axes[0].imshow(image_rgb.astype(np.uint8))
axes[0].set_title("Original Image")

# Overlay masks with transparency
mask_colored = np.ma.masked_where(mask == 0, mask)
axes[0].imshow(mask_colored, cmap='nipy_spectral', alpha=0.5)

# Contour overlay
axes[1].imshow(image_rgb.astype(np.uint8))
axes[1].contour(mask, levels=np.unique(mask)[1:], colors='cyan')
axes[1].set_title("Contour Overlay")
```

**Cell 4-5: Individual Nuclei Extraction**

```python
# Label connected components
labeled_mask = label(mask > 0)
regions = regionprops(labeled_mask)
print(f"Detected {len(regions)} nuclei")

# Extract each nucleus
nuclei_crops = []
for nuc_id in nuc_ids[:36]:  # First 36 nuclei
    ys, xs = np.where(mask == nuc_id)
    minr, maxr = ys.min(), ys.max() + 1
    minc, maxc = xs.min(), xs.max() + 1
    
    # Crop region
    crop = image[minr:maxr, minc:maxc]
    
    # Apply mask to isolate nucleus
    region_mask = (mask[minr:maxr, minc:maxc] == nuc_id).astype(np.uint8)
    crop_masked = crop * region_mask[:, :, np.newaxis]
    
    # Resize to 50x50 with center padding
    h, w = crop_masked.shape[:2]
    if max(h, w) > 50:
        scale = 50 / max(h, w)
        crop_masked = cv2.resize(crop_masked, None, fx=scale, fy=scale)
    
    # Center pad to 50x50
    padded = np.zeros((50, 50, 3), dtype=np.uint8)
    y_offset = (50 - crop_masked.shape[0]) // 2
    x_offset = (50 - crop_masked.shape[1]) // 2
    padded[y_offset:..., x_offset:...] = crop_masked
    
    nuclei_crops.append(padded)
```

### 3.2 Output Formats Used in Notebook

| Item | Type | Purpose |
|------|------|---------|
| `image` | NumPy (H, W, 3) uint8 | Original RGB image |
| `mask` | NumPy (H, W) uint32 | 2D label array from Cellpose |
| `crop` | NumPy (h, w, 3) uint8 | Extracted nucleus region |
| `region_mask` | NumPy (h, w) uint8 | Binary mask for nucleus |
| `nuclei_crops` | List[NumPy] | Standardized 50x50 crops |

---

## 4. Test and Diagnostic Files

### 4.1 test_cellpose_simple.py

**File:** [test_cellpose_simple.py](test_cellpose_simple.py)

Simple test of CellposeAdapter with synthetic images:

```python
# Create test image
test_image = np.random.randint(0, 255, (500, 500, 3), dtype=np.uint8)

# Initialize adapter
adapter = CellposeAdapter(model_type="nuclei", gpu=None)

# Segment
polygons = adapter.segment(
    test_image,
    diameter=30.0,
    flow_threshold=0.4,
    cellprob_threshold=0.0
)

# Output
print(f"Detected {len(polygons)} nuclei")
for i, poly in enumerate(polygons[:3]):
    print(f"  Nucleus {i}: {len(poly)} points")
```

### 4.2 diagnose_gpu.py

**File:** [diagnose_gpu.py](diagnose_gpu.py)

Comprehensive GPU diagnostics:

1. **Hardware Detection**
   - GPU/CUDA available?
   - Memory, CPU cores, architecture

2. **Configuration Check**
   - Cellpose settings loaded?
   - GPU enabled in config?

3. **Cellpose Import Test**
   - Can cellpose be imported?
   - Model type availability?

4. **CellposeAdapter Initialization**
   - Adapter loads without error?
   - GPU correctly detected?

### 4.3 test_hardware_simple.py

Similar to diagnose_gpu.py but simpler for quick verification.

---

## 5. Key Differences: Cellpose Calls in Each Location

| Location | Purpose | Input Type | GPU | Timeout | Output Format |
|----------|---------|-----------|-----|---------|---------------|
| **CellposeAdapter.segment()** | Production batch segmentation | PIL Image or NumPy | Auto-detected | 60s watchdog | List[List[Tuple[int, int]]] (polygons) |
| **CellposeAdapter._segment_single_image()** | Internal: raw Cellpose call | NumPy (uint8) | Same as adapter | N/A (called from segment) | Same (polygons) |
| **model.eval()** (Cellpose library) | Raw model inference | NumPy (uint8) grayscale | Cellpose internal | None | (masks, flows, styles) |
| **main.ipynb mask loading** | Post-processing analysis | NPY dict file | N/A | N/A | `mask_dict['masks']` (2D label array) |
| **diagnose_gpu.py** | Testing/diagnostics | Synthetic NumPy | Same as adapter | Same as adapter | Logs, success/failure |

---

## 6. Input/Output Format Reference

### 6.1 CellposeAdapter.segment() — Inputs

```python
# Input 1: PIL Image (RGB)
from PIL import Image
img = Image.open('nuclei.jpg')  # Shape: (W, H) with RGB mode
adapter.segment(img, diameter=30.0)

# Input 2: NumPy array
import numpy as np
img_array = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
adapter.segment(img_array, diameter=30.0)

# Input 3: Grayscale NumPy
img_gray = np.random.randint(0, 256, (480, 640), dtype=np.uint8)
adapter.segment(img_gray, diameter=30.0)

# Parameters
diameter: float | None = 30.0          # Nucleus size (pixels); None = auto
flow_threshold: float | None = 0.4     # Flow error quality filter
cellprob_threshold: float | None = 0.0 # Cell probability filter
```

### 6.2 CellposeAdapter.segment() — Outputs

```python
# Returns: List[List[Tuple[int, int]]]
polygons = adapter.segment(image, diameter=30.0)

# Example structure:
[
    [(10, 20), (15, 18), (18, 22), (20, 25), ...],  # Nucleus 1 contour
    [(50, 80), (55, 78), (58, 82), (60, 85), ...],  # Nucleus 2 contour
    [(100, 150), (105, 148), ...],                   # Nucleus 3 contour
]

# Access
for i, polygon in enumerate(polygons):
    print(f"Nucleus {i}: {len(polygon)} boundary points")
    for x, y in polygon:
        print(f"  ({x}, {y})")
```

### 6.3 Cellpose Model.eval() — Raw Output

```python
from cellpose import models

model = models.CellposeModel(model_type='nuclei', gpu=True)
masks, flows, styles = model.eval(
    image,
    diameter=30.0,
    channels=[0, 0]
)

# masks: 2D NumPy array (H, W) with dtype=uint32
# Example:
#   - masks[100, 150] = 3      (pixel at y=100, x=150 is nucleus #3)
#   - masks[100, 100] = 0      (background pixel)
#   - masks.max() = 47         (47 nuclei detected)

# flows: Tuple of 3 arrays (dy, dx, uncertainty)
# styles: Feature vector for custom training

# To extract individual nucleus masks:
nucleus_id = 3
nucleus_mask = (masks == nucleus_id).astype(np.uint8) * 255
```

### 6.4 main.ipynb — Saved Format

```python
# Save format (from Cellpose to disk)
np.save('image_seg.npy', {
    'masks': np.array([[0, 0, 1, 1],
                       [0, 2, 2, 1],
                       [3, 2, 1, 1]]),  # 2D label array
    'flows': (dy_flow, dx_flow, uncertainty)
})

# Load format (in main.ipynb)
data = np.load('image_seg.npy', allow_pickle=True).item()
masks = data['masks']  # 2D label array
flows = data['flows']  # Optical flow tuple
```

---

## 7. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    GUI Layer (main_window.py)                   │
│  • User clicks "Segment Tile with Cellpose"                     │
│  • Passes request to BatchSegmentationService                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│         Application Service (batch_segmentation_service.py)      │
│  • Orchestrates: extract image → segment → convert coordinates  │
│  • Calls IBatchSegmentationModel.segment()                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│             Domain Port (batch_segmentation_model.py)            │
│              << IBatchSegmentationModel >>                       │
│    abstract segment(image, diameter, ...) → List[Polygon]       │
└──────────────────────────▬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│         Infrastructure Adapter (cellpose_adapter.py)             │
│           << CellposeAdapter(IBatchSegmentationModel) >>         │
│  1. Validate input (PIL Image → NumPy array)                    │
│  2. H&E preprocessing (extract + invert blue channel)           │
│  3. Optionally resample                                          │
│  4. Tile large images if necessary                              │
│  5. Call Cellpose model.eval() with timeout protection          │
│  6. Convert masks → polygons (OpenCV contours)                  │
│  7. Filter edge nuclei                                          │
│  8. Return List[List[Tuple[int, int]]] (polygons)               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│              Cellpose Library (cellpose.models)                  │
│  • CellposeModel.eval() → (masks, flows, styles)                │
│  • Runs on GPU or CPU based on configuration                    │
│  • Returns 2D label array where each pixel = nucleus ID          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 8. Configuration Reference

**Location:** [app/infrastructure/config/performance_config.py](app/infrastructure/config/performance_config.py)

### Accessing Configuration

```python
from app.infrastructure.config.performance_config import get_performance_config

config = get_performance_config()

# Cellpose settings
use_gpu = config.cellpose.use_gpu
batch_size = config.cellpose.batch_size
timeout = config.cellpose.timeout_seconds
max_tile = config.cellpose.max_tile_size_pixels
memory_limit = config.cellpose.memory_limit_mb
resample = config.cellpose.resample_factor

# Global settings
force_cpu = config.force_cpu_only
```

### Profile-Based Defaults

Configuration adapts based on **hardware profile** (detected at startup):

- **High-End GPU** (RTX 4080, A100): batch_size=256, timeout=120s
- **Mid-Range GPU** (RTX 3060): batch_size=128, timeout=90s
- **Laptop GPU** (RTX 2060, M1): batch_size=64, timeout=60s
- **CPU Only**: batch_size=8, timeout=30s

---

## 9. Common Use Cases

### 9.1 Segment a Single Image in Production

```python
from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
from PIL import Image

# Initialize (triggers lazy-load on first call)
adapter = CellposeAdapter(model_type="nuclei", gpu=None)

# Load image
img = Image.open("nuclei.jpg").convert("RGB")

# Segment
polygons = adapter.segment(img, diameter=30.0)

# Process results
for nucleus_id, polygon in enumerate(polygons):
    print(f"Nucleus {nucleus_id}: {len(polygon)} boundary points")
    # polygon = [(x1, y1), (x2, y2), ...]
```

### 9.2 Segment a Region from the Image Pyramid

```python
from app.application.batch_segmentation_service import BatchSegmentationService

# Already configured in GUI
service = self.batch_segmentation_service

# Segment tile (auto-extracts from pyramid, converts coordinates)
global_polygons = service.segment_tile(
    model_name="Cellpose (nuclei)",
    session=current_session,
    slice_idx=tile_index,
    diameter=30.0
)

# Output: polygons in global image coordinates
```

### 9.3 Analyze Pre-Segmented Data (Jupyter Notebook)

```python
import numpy as np
import matplotlib.pyplot as plt

# Load Cellpose output
mask_dict = np.load("image_seg.npy", allow_pickle=True).item()
masks = mask_dict['masks']

# Visualize
fig, ax = plt.subplots(figsize=(10, 10))
ax.imshow(masks, cmap='nipy_spectral')
ax.set_title(f"{masks.max()} nuclei detected")
plt.show()

# Extract individual nucleus
nucleus_id = 5
nucleus_mask = (masks == nucleus_id).astype(np.uint8) * 255
ys, xs = np.where(nucleus_mask)
crop = image[ys.min():ys.max()+1, xs.min():xs.max()+1]
```

### 9.4 Test GPU Configuration

```bash
cd /path/to/grid-image-analyzer

# Full diagnostics
python diagnose_gpu.py

# Simple test
python test_hardware_simple.py

# Cellpose-specific test
python test_cellpose_simple.py
```

---

## 10. Troubleshooting

### Issue: "Cellpose model not loaded" / Empty polygon list

**Causes:**
1. Model file missing from `~/.cellpose/models/`
2. GPU memory exhausted
3. Image preprocessing failed
4. Timeout exceeded

**Solutions:**
```python
# Check config
from app.infrastructure.config.performance_config import get_performance_config
config = get_performance_config()
print(f"GPU enabled: {config.cellpose.use_gpu}")
print(f"Timeout: {config.cellpose.timeout_seconds}s")

# Force CPU if GPU is causing issues
adapter = CellposeAdapter(model_type="nuclei", gpu=False)

# Reduce image size (triggers resampling)
adapter._resample_factor = 0.5
polygons = adapter.segment(large_image)
```

### Issue: "BFloat16 not supported" (Apple MPS)

**Cause:** GPU loaded a model version incompatible with Apple Silicon

**Solution:** Automatic fallback enabled in adapter:
```python
# This is handled automatically:
try:
    model = CellposeModel(gpu=True)  # MPS fails
except Exception:
    model = CellposeModel(gpu=False)  # Retried on CPU
```

### Issue: Segmentation too slow

**Solutions:**
```python
# Reduce batch size (use less VRAM)
config.cellpose.batch_size = 32

# Enable resampling
adapter._resample_factor = 0.8  # 80% of original size

# Reduce max tile size (more tiles, smaller per tile)
config.cellpose.max_tile_size_pixels = 512

# Lower timeout (kill slow processes)
config.cellpose.timeout_seconds = 30
```

---

## 11. Key Files Summary Table

| File | Class | Purpose | Lines |
|------|-------|---------|-------|
| [cellpose_adapter.py](app/infrastructure/ml_models/cellpose_adapter.py) | `CellposeAdapter` | Core Cellpose wrapper | ~600 |
| [batch_segmentation_service.py](app/application/batch_segmentation_service.py) | `BatchSegmentationService` | Service orchestration | ~150 |
| [batch_segmentation_model.py](app/domain/interfaces/batch_segmentation_model.py) | `IBatchSegmentationModel` | Domain port (interface) | ~50 |
| [main_window.py](app/interface/gui/main_window.py) | `SlicerLabApp` | GUI + composition root | ~250 |
| [main.ipynb](main.ipynb) | — | Jupyter notebook (analysis) | ~500 |
| [test_cellpose_simple.py](test_cellpose_simple.py) | — | Simple test script | ~80 |
| [diagnose_gpu.py](diagnose_gpu.py) | — | GPU diagnostics | ~200 |

---

## Conclusion

The grid-image-analyzer implements a **production-grade, enterprise-architecture** Cellpose integration:

✅ **Clean Architecture** — Infrastructure isolated behind domain port  
✅ **Lazy Loading** — Defers heavy imports to avoid DLL conflicts  
✅ **GPU Optimization** — Auto-detection + fallback + batch size tuning  
✅ **Robustness** — Timeout watchdog + memory checks + edge filtering  
✅ **Scalability** — Automatic tiling for large images  
✅ **Testing** — Comprehensive test and diagnostic tools  
✅ **Analysis** — Jupyter notebook for post-processing exploration  

This design allows Cellpose segmentation to be seamlessly integrated into the GUI while maintaining flexibility for research, debugging, and optimization.
