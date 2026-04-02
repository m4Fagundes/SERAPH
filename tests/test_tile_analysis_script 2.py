import sys
import os

# Add the project root to sys.path so we can import app modules properly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.domain.session import ImageSession
from app.application.tile_analysis_service import TileAnalysisService
from app.infrastructure.analyzers.dummy_analyzer import BasicStatsAnalyzer

def main() -> None:
    print("Testing Tile Analysis Module...")
    
    # 1. Instantiate the service
    service = TileAnalysisService()
    
    # 2. Register analyzers
    dummy_analyzer = BasicStatsAnalyzer()
    service.register_analyzer(dummy_analyzer)
    
    # 3. List available ones
    print(f"Available analyzers: {service.get_available_analyzers()}")
    
    # Note: We can't fully run it without a real image session initialized
    # so we'll just test the mock logic by instantiating it.
    print("Module Architecture is properly wired.")
    
if __name__ == "__main__":
    main()
