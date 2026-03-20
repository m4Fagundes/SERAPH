import logging
import os
from typing import Set, Tuple
from app.domain.session import ImageSession

logger = logging.getLogger(__name__)

class PixelMaskService:
    """Application-layer service for toggling individual pixel removal masks.

    Masks are stored as a :class:`set` of ``(px, py)`` image-space coordinate
    pairs on ``session.pixel_masks[slice_idx]``.  This service has no side-effects
    beyond mutating that set — callers are responsible for pushing an undo snapshot
    via :class:`~app.domain.history.UndoManager` before calling :meth:`toggle_pixel`.
    """

    def toggle_pixel(
        self, session: ImageSession, slice_idx: int, px: int, py: int
    ) -> bool:
        """Toggle the removal state of a single pixel.

        Args:
            session: The active :class:`ImageSession`.
            slice_idx: Index into ``session.tiles``.
            px, py: Image-space pixel coordinates (0-based, full-resolution).

        Returns:
            ``True`` if the pixel is now *removed*; ``False`` if it was restored.
        """
        mask: Set[Tuple[int, int]] = session.tiles[slice_idx].pixel_mask
        coord = (px, py)
        if coord in mask:
            mask.discard(coord)
            return False
        else:
            mask.add(coord)
            return True

    def get_mask(
        self, session: ImageSession, slice_idx: int
    ) -> Set[Tuple[int, int]]:
        """Return the current pixel mask set for a slice (never ``None``)."""
        return session.tiles[slice_idx].pixel_mask
