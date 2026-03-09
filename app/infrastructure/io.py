import json
import logging
import os
from PIL import Image

from app.infrastructure.exceptions import ProjectIOError

logger = logging.getLogger(__name__)


def load_project_file(path):
    """Loads project data from a JSON file.

    Raises:
        ProjectIOError: if the file cannot be opened or is not valid JSON.
    """
    logger.debug("Loading project file: %s", path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Project loaded successfully: %s", path)
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load project '%s': %s", path, exc)
        raise ProjectIOError(f"Cannot read project file '{path}': {exc}") from exc


def save_project_file(path, data):
    """Saves project data to a JSON file.

    Raises:
        ProjectIOError: if the file cannot be written.
    """
    logger.debug("Saving project file: %s", path)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        logger.info("Project saved successfully: %s", path)
    except OSError as exc:
        logger.error("Failed to save project '%s': %s", path, exc)
        raise ProjectIOError(f"Cannot write project file '{path}': {exc}") from exc


def save_image_tile(image, path, format_ext):
    """Saves a PIL Image tile to the specified path."""
    try:
        # Standardize format extension for PIL
        fmt = format_ext.lower().replace(".", "")
        if fmt == "jpg":
            fmt = "jpeg"
        image.save(path, format=fmt, quality=95)
        return True
    except Exception as exc:
        logger.error("Error saving tile '%s': %s", path, exc)
        return False
