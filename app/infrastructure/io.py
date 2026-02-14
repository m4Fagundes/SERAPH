import json
import os
from PIL import Image

def load_project_file(path):
    """Loads project data from a JSON file."""
    with open(path, "r") as f:
        return json.load(f)

def save_project_file(path, data):
    """Saves project data to a JSON file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

def save_image_tile(image, path, format_ext):
    """Saves a PIL Image tile to the specified path."""
    try:
        # Standardize format extension for PIL
        fmt = format_ext.lower().replace(".", "")
        if fmt == "jpg": fmt = "jpeg"
        image.save(path, format=fmt, quality=95)
        return True
    except Exception as e:
        print(f"Error saving tile {path}: {e}")
        return False
