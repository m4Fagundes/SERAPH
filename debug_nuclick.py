import logging
import PIL.Image as Image
import numpy as np

logging.basicConfig(level=logging.DEBUG)

def test_inference():
    from app.infrastructure.ml_models.nuclick_adapter import NuClickAdapter
    
    print("Initializing adapter...")
    adapter = NuClickAdapter(model_path="app/infrastructure/ml_models/nuclick_torch/weights/nuclick.pth")
    if not adapter._model:
        print("Model failed to load.")
        return
        
    print("Model loaded. Running prediction...")
    # Create dummy white image
    img = Image.new("RGB", (256, 256), "white")
    
    # Predict in the center
    try:
        poly = adapter.predict(img, 128, 128)
        print("Prediction successful:", len(poly), "points")
    except Exception as e:
        print("PREDICTION FAILED:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_inference()
