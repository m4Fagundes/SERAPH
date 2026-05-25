import logging
import time
import torch
import numpy as np
from cellpose import models

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

print("PyTorch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
print("CUDA device count:", torch.cuda.device_count())

for i in range(torch.cuda.device_count()):
    print(f"Device {i}: {torch.cuda.get_device_name(i)} (Capability: {torch.cuda.get_device_capability(i)})")

# Test Cellpose on cuda:0 (which will be the RTX 2060 if CUDA_VISIBLE_DEVICES="1" is set)
try:
    print("\n--- Initializing CellposeModel on cuda:0 ---")
    device = torch.device("cuda:0")
    model = models.CellposeModel(
        pretrained_model="cpsam",
        gpu=True,
        device=device
    )
    print("Model loaded successfully.")
    
    # Create dummy image
    img = np.random.randint(0, 255, (1000, 1000, 3), dtype=np.uint8)
    
    # Warmup
    print("Running segment warmup...")
    masks, flows, styles = model.eval(img, channels=[3, 0], diameter=30.0)
    print("Warmup success. Detected", masks.max(), "objects.")
    
    # Benchmark
    print("Running segment benchmark...")
    t0 = time.time()
    for _ in range(5):
        masks, flows, styles = model.eval(img, channels=[3, 0], diameter=30.0)
    elapsed = time.time() - t0
    print(f"Benchmark finished: 5 evaluations took {elapsed:.2f} seconds (average {elapsed/5:.2f}s per 1000x1000 tile).")
    
except Exception as e:
    import traceback
    traceback.print_exc()
    print("Error during Cellpose GPU test:", e)
