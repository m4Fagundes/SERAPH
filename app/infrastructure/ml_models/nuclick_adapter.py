import logging
import math
from typing import List, Tuple
from pathlib import Path
from PIL.Image import Image

from app.domain.interfaces.segmentation_model import ISegmentationModel
from app.infrastructure.ml_models.model_downloader import ModelDownloader

logger = logging.getLogger(__name__)


class NuClickAdapter(ISegmentationModel):
    """
    Adapter for the NuClick interactive segmentation model.
    Transforms the domain concepts (Image, x, y) into the expected
    format for the NuClick neural network, and translates the output
    mask back to a list of polygon coordinates.
    
    The model is downloaded on-demand from the internet on first use.
    """

    PATCH_SIZE = 128   # NuClick operates on 128×128 patches
    PAD = PATCH_SIZE // 2  # Padding to guarantee safe patch extraction at edges

    def __init__(self, model_path: str = None):
        """
        Initialize NuClick adapter.
        
        Args:
            model_path: Optional override path to model. If None, will auto-download
                       from configured URL to ~/.grid-analyzer/models/nuclick.pth
        """
        self.model_path = model_path
        self._model = None
        self._load_attempted = False

    def _ensure_model_loaded(self):
        """Lazy-load the PyTorch model on first use.

        Importing torch at app startup can fail when PyQt6's OpenGL widget
        has already loaded conflicting DLLs.  By deferring the import to
        the first prediction request, we sidestep the DLL-load-order issue
        and keep the adapter name available for the UI ComboBox immediately.
        """
        if self._load_attempted:
            return
        self._load_attempted = True
        self._load_model()

    def _get_model_path(self) -> Path:
        """Get path to model, downloading if necessary."""
        if self.model_path:
            # User provided explicit path
            return Path(self.model_path)
        
        # Auto-download from configured URL
        logger.info("Downloading NuClick model on-demand...")
        try:
            model_path = ModelDownloader.get_model_path('nuclick.pth')
            logger.info(f"NuClick model ready at {model_path}")
            return model_path
        except Exception as e:
            logger.error(f"Failed to download NuClick model: {e}")
            raise

    def _load_model(self):
        """Loads the NuClick PyTorch model."""
        import torch
        from app.infrastructure.ml_models.nuclick_torch.architecture import NuClick_NN
        from app.infrastructure.config.gpu_selector import get_best_cuda_device

        try:
            # Ensure model file exists (download if needed)
            model_path = self._get_model_path()
            
            best_gpu = get_best_cuda_device()
            if torch.cuda.is_available() and best_gpu is not None:
                device = torch.device(f'cuda:{best_gpu}')
            else:
                device = torch.device('cpu')
                
            self._model = NuClick_NN(n_channels=5, n_classes=1)
            self._model.to(device=device)
            
            # Load state dictionary
            self._model.load_state_dict(torch.load(str(model_path), map_location=device, weights_only=True))
            self._model.eval()
            
            logger.info("NuClick model loaded successfully from %s on %s", model_path, device)
        except Exception as e:
            logger.error("Failed to load NuClick model: %s", e)
            self._model = None

    @property
    def name(self) -> str:
        return "NuClick (PyTorch)"

    def predict(self, image: Image, click_x: int, click_y: int) -> List[Tuple[int, int]]:
        """
        Runs the NuClick neural network to segment the nucleus at the clicked coordinate.

        Args:
            image: The PIL Image (RGB).
            click_x: Click X coordinate.
            click_y: Click Y coordinate.

        Returns:
            List of (x, y) coordinates forming the segmented polygon.
        """
        self._ensure_model_loaded()

        if self._model is None:
            logger.warning("NuClick model is not loaded. Returning empty segmentation.")
            return []

        import torch
        import numpy as np
        import cv2

        from app.infrastructure.ml_models.nuclick_torch.guiding_signals import get_patches_and_signals
        from app.infrastructure.ml_models.nuclick_torch.process import post_processing
        from PIL import ImageOps

        logger.info(f"Running NuClick segmentation for point ({click_x}, {click_y})")

        # 1. Pad image by PAD pixels on all sides to prevent edge-crop issues
        # This guarantees ANY click point can safely yield a PATCH_SIZE boundary.
        pad = self.PAD
        padded_image = ImageOps.expand(image, border=pad, fill=0)
        padded_width, padded_height = padded_image.size

        new_click_x = click_x + pad
        new_click_y = click_y + pad

        # 2. Transform PIL Image to Numpy RGB
        image_np = np.asarray(padded_image)[:, :, :3]
        image_np = np.moveaxis(image_np, 2, 0) # Format (3, H, W)

        # 3. Setup standard arrays required by get_patches_and_signals
        cx = [new_click_x]
        cy = [new_click_y]
        
        clickMap = np.zeros((padded_height, padded_width), dtype=np.uint8)
        clickMap[new_click_y, new_click_x] = 1

        # Bounding box is exactly PATCH_SIZE centered on new click
        half = self.PAD
        bb = [
            new_click_x - half,
            new_click_y - half,
            new_click_x + half - 1,
            new_click_y + half - 1
        ]
        boundingBoxes = [bb]

        # 4. Generate the 5-channel patch
        # get_patches_and_signals takes:
        # image (3, H, W), clickMap, boundingBoxes, cx, cy, imgHeight, imgWidth
        patchs, nucPoints, otherPoints = get_patches_and_signals(
            image_np, clickMap, boundingBoxes, cx, cy, padded_height, padded_width
        )
        
        # Normalize patches
        patchs = patchs / 255.0

        # Concatenate RGB + Nucleus Point + Other Points
        input_data = np.concatenate((patchs, nucPoints, otherPoints), axis=1, dtype=np.float32)
        
        from app.infrastructure.config.gpu_selector import get_best_cuda_device
        best_gpu = get_best_cuda_device()
        if torch.cuda.is_available() and best_gpu is not None:
            device = torch.device(f'cuda:{best_gpu}')
        else:
            device = torch.device('cpu')
            
        input_tensor = torch.from_numpy(input_data).to(device=device, dtype=torch.float32)

        # 4. Predict
        with torch.no_grad():
            output = self._model(input_tensor) # (1, 1, 128, 128)
            output = torch.sigmoid(output)
            output = torch.squeeze(output, 1)  # (1, 128, 128)
            preds = output.cpu().numpy()

        # 5. Post Processing
        logger.info("Raw max prediction probability: %f", float(preds.max()))
        logger.info("Raw min prediction probability: %f", float(preds.min()))
        
        # OpenCV's RETR_EXTERNAL ignores holes and we pick the largest contour,
        # skipping expensive CPU morphology.
        masks = preds > 0.5
        patch_mask = masks[0]
        
        # cv2.findContours requires uint8 array
        patch_mask = patch_mask.astype(np.uint8) * 255
        
        logger.info("Generated mask unique values: %s", str(np.unique(patch_mask)))
        
        # Find contours inside the patch
        contours, _ = cv2.findContours(patch_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []

        # Assuming largest contour is the cell we want
        largest_contour = max(contours, key=cv2.contourArea)
        
        # Output coordinates (polygon patch-relative -> absolute)
        # Bounding box dictates where the patch is located
        bx_min, by_min, bx_max, by_max = boundingBoxes[0]
        
        polygon = []
        for pt in largest_contour:
            px, py = pt[0]
            # Coordinates inside patch are offset by bounding box start.
            # Subtract 'pad' to return coordinates to the original unpadded image plane.
            abs_x = px + bx_min - pad
            abs_y = py + by_min - pad
            polygon.append((int(abs_x), int(abs_y)))

        return polygon

    def predict_batch(self, image: Image, clicks: List[Tuple[int, int]]) -> List[List[Tuple[int, int]]]:
        """
        Runs the NuClick neural network to segment multiple nuclei in a single batch pass.

        Args:
            image: The PIL Image (RGB).
            clicks: List of (click_x, click_y) coordinates.

        Returns:
            List of polygons, where each polygon is a list of (x, y) coordinates.
        """
        self._ensure_model_loaded()

        if self._model is None:
            logger.warning("NuClick model is not loaded. Returning empty segmentations.")
            return []

        if not clicks:
            return []

        import torch
        import numpy as np
        import cv2

        from app.infrastructure.ml_models.nuclick_torch.guiding_signals import get_patches_and_signals
        from app.infrastructure.ml_models.nuclick_torch.process import post_processing
        from PIL import ImageOps

        logger.info(f"Running NuClick batch segmentation for {len(clicks)} points")

        pad = self.PAD
        padded_image = ImageOps.expand(image, border=pad, fill=0)
        padded_width, padded_height = padded_image.size

        image_np = np.asarray(padded_image)[:, :, :3]
        image_np = np.moveaxis(image_np, 2, 0) # Format (3, H, W)

        cx = []
        cy = []
        boundingBoxes = []
        clickMap = np.zeros((padded_height, padded_width), dtype=np.uint8)

        for (click_x, click_y) in clicks:
            new_click_x = click_x + pad
            new_click_y = click_y + pad
            cx.append(new_click_x)
            cy.append(new_click_y)
            clickMap[new_click_y, new_click_x] = 1
            half = self.PAD
            bb = [
                new_click_x - half,
                new_click_y - half,
                new_click_x + half - 1,
                new_click_y + half - 1
            ]
            boundingBoxes.append(bb)

        # Send patches in chunks to prevent CUDA OOM.
        # A chunk size of 64 is safe for a 6GB GPU (RTX 2060) when Cellpose is also loaded.
        CHUNK_SIZE = 64
        all_polygons = []
        from app.infrastructure.config.gpu_selector import get_best_cuda_device
        best_gpu = get_best_cuda_device()
        if torch.cuda.is_available() and best_gpu is not None:
            device = torch.device(f'cuda:{best_gpu}')
        else:
            device = torch.device('cpu')

        for i in range(0, len(cx), CHUNK_SIZE):
            cx_chunk = cx[i:i+CHUNK_SIZE]
            cy_chunk = cy[i:i+CHUNK_SIZE]
            bb_chunk = boundingBoxes[i:i+CHUNK_SIZE]

            patchs, nucPoints, otherPoints = get_patches_and_signals(
                image_np, clickMap, bb_chunk, cx_chunk, cy_chunk, padded_height, padded_width
            )

            patchs = patchs / 255.0
            input_data = np.concatenate((patchs, nucPoints, otherPoints), axis=1, dtype=np.float32)
            input_tensor = torch.from_numpy(input_data).to(device=device, dtype=torch.float32)

            with torch.no_grad():
                output = self._model(input_tensor) # (N, 1, 128, 128)
                output = torch.sigmoid(output)
                output = torch.squeeze(output, 1)  # (N, 128, 128)
                preds = output.cpu().numpy()

            # OpenCV's RETR_EXTERNAL already ignores holes and we pick the largest contour,
            # so expensive CPU morphology (remove_small_objects, holes, reconstruction) is 100% redundant.
            masks = preds > 0.5

            for j in range(len(masks)):
                patch_mask = masks[j]
                patch_mask = patch_mask.astype(np.uint8) * 255
                
                contours, _ = cv2.findContours(patch_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if not contours:
                    all_polygons.append([])
                    continue

                largest_contour = max(contours, key=cv2.contourArea)
                bx_min, by_min, bx_max, by_max = bb_chunk[j]
                
                polygon = []
                for pt in largest_contour:
                    px, py = pt[0]
                    abs_x = px + bx_min - pad
                    abs_y = py + by_min - pad
                    polygon.append((int(abs_x), int(abs_y)))
                    
                all_polygons.append(polygon)

        return all_polygons
