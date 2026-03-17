from abc import ABC, abstractmethod
from typing import List, Tuple
from PIL.Image import Image


class ISegmentationModel(ABC):
    """
    Port (Interface) for interactive segmentation models.
    Defines the contract that any segmentation model must implement.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the display name of the model."""
        pass

    @abstractmethod
    def predict(self, image: Image, click_x: int, click_y: int) -> List[Tuple[int, int]]:
        """
        Run interactive segmentation based on a click coordinate.

        Args:
            image: The full resolution PIL Image region.
            click_x: The X coordinate of the user click (relative to the image region).
            click_y: The Y coordinate of the user click (relative to the image region).

        Returns:
            A list of (x, y) tuples representing the polygon boundary of the segmented object,
            in coordinates relative to the provided image region.
        """
        pass
