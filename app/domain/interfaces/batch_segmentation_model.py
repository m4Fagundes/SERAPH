from abc import ABC, abstractmethod
from typing import List, Tuple

from PIL.Image import Image


class IBatchSegmentationModel(ABC):
    """
    Port (Interface) for batch segmentation models.

    Unlike ISegmentationModel (interactive, click-based), batch models
    process the entire image at once and return ALL detected objects
    as a list of polygon boundaries.

    Architectural Note (python-patterns §3 — Type Hints Strategy):
        All public methods are fully typed for IDE support and mypy.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the display name of the model."""
        pass

    @abstractmethod
    def segment(
        self,
        image: Image,
        diameter: float | None = None,
        flow_threshold: float | None = None,
        cellprob_threshold: float | None = None,
    ) -> List[List[Tuple[int, int]]]:
        """
        Segment ALL objects in the image.

        Args:
            image: PIL Image (RGB).
            diameter: Expected object diameter in pixels (None = auto-detect).
            flow_threshold: Flow error threshold for mask quality (optional).
            cellprob_threshold: Cell probability threshold (optional).

        Returns:
            A list of polygons. Each polygon is a list of (x, y) tuples
            representing the boundary of one detected object, in
            coordinates relative to the provided image region.
        """
        pass

    def probability_map(self):
        """Return the H×W float32 probability map (values 0–1) from the last segment() call.

        Returns None if this model does not expose raw confidence values.
        Subclasses override this to expose model-internal probabilities.
        """
        return None
