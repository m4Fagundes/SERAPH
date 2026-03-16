from abc import ABC, abstractmethod
from typing import Any, Dict
from PIL import Image

class TileAnalyzer(ABC):
    """
    Abstract base class for all tile analyzers.
    Independent of GUI. Follows Clean Architecture and python pattern guidelines.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the analyzer (e.g., 'BasicStats', 'NucleusSegmentation')"""
        pass

    @abstractmethod
    def analyze(self, image_patch: Image.Image, **kwargs) -> Dict[str, Any]:
        """
        Runs the analysis on a given image patch.
        
        Args:
            image_patch: A PIL Image representing the tile/region to be analyzed.
            **kwargs: Additional parameters specific to the analyzer.
            
        Returns:
            A dictionary containing the analysis results.
        """
        pass
