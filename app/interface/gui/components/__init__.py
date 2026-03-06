"""GUI components package for Tiles Grid Analyzer.

Re-exports UIComponents and setup_ttk_styles for backward compatibility,
plus all mixin classes used by SlicerLabApp.
"""

from app.interface.gui.components.ui_components import UIComponents, setup_ttk_styles
from app.interface.gui.components.canvas_renderer import CanvasRendererMixin
from app.interface.gui.components.zoom_pan import ZoomPanMixin
from app.interface.gui.components.selection_tools import SelectionToolsMixin
from app.interface.gui.components.slice_inspector import SliceInspectorMixin
from app.interface.gui.components.slice_previews import SlicePreviewsMixin
from app.interface.gui.components.project_manager import ProjectManagerMixin
from app.interface.gui.components.export_handler import ExportHandlerMixin

__all__ = [
    "UIComponents",
    "setup_ttk_styles",
    "CanvasRendererMixin",
    "ZoomPanMixin",
    "SelectionToolsMixin",
    "SliceInspectorMixin",
    "SlicePreviewsMixin",
    "ProjectManagerMixin",
    "ExportHandlerMixin",
]
