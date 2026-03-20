import logging
from typing import Dict, Any, Optional, List
from app.domain.session import ImageSession
from app.domain.tile_analysis import TileAnalyzer

logger = logging.getLogger(__name__)

class TileAnalysisService:
    """
    Application service that orchestrates tile analysis.
    Connects the active session/pyramid with the chosen analyzer.
    """
    def __init__(self) -> None:
        self._analyzers: Dict[str, TileAnalyzer] = {}

    def register_analyzer(self, analyzer: TileAnalyzer) -> None:
        """Registers a new tile analyzer."""
        self._analyzers[analyzer.name] = analyzer
        logger.debug("Registered analyzer: %s", analyzer.name)

    def get_available_analyzers(self) -> List[str]:
        """Returns a list of registered analyzer names."""
        return list(self._analyzers.keys())

    def get_analyzer(self, name: str) -> Optional[TileAnalyzer]:
        """Returns an analyzer by name if registered."""
        return self._analyzers.get(name)

    def analyze_tile(
        self, 
        session: ImageSession, 
        col: int, 
        row: int, 
        zoom: float, 
        tile_size: int, 
        analyzer_name: str,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Fetches a specific tile from the session and runs it through the chosen analyzer.
        """
        analyzer = self.get_analyzer(analyzer_name)
        if not analyzer:
            raise ValueError(f"Analyzer '{analyzer_name}' not found.")

        # Read the tile using the existing pyramid structure
        # get_tile returns a PIL image
        pil_img = session.pyramid.get_tile(col, row, zoom, tile_size)
        
        return analyzer.analyze(pil_img, **kwargs)

    def analyze_region(
        self, 
        session: ImageSession, 
        x: int, 
        y: int, 
        width: int, 
        height: int, 
        analyzer_name: str,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Fetches an arbitrary full-res region from the session and runs it through the analyzer.
        """
        analyzer = self.get_analyzer(analyzer_name)
        if not analyzer:
            raise ValueError(f"Analyzer '{analyzer_name}' not found.")

        # Read the region at full resolution
        pil_img = session.pyramid.get_region_fullres(x, y, width, height)
        
        return analyzer.analyze(pil_img, **kwargs)
