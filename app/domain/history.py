"""
Undo/Redo history manager for tile operations.

Stores snapshots of tile state to allow undo/redo of add, delete,
and clear actions. Each action captures the minimal data needed
to restore the previous state.
"""

import copy
from typing import Any, Dict, List, Optional


# Maximum number of undo steps per session
MAX_HISTORY = 50


class UndoManager:
    """Stack-based undo/redo manager for tile operations."""

    def __init__(self) -> None:
        self._undo_stack: List[Dict[str, Any]] = []  # list of Action dicts
        self._redo_stack: List[Dict[str, Any]] = []  # list of Action dicts

    def push(self, session: Any, action_type: str = "modify") -> None:
        """Snapshot the current tile state before a modification.

        Call this BEFORE modifying selected_cells / selected_polygons /
        slice_metadata on the session.

        Args:
            session: ImageSession whose state is being changed.
            action_type: human-readable label, e.g. "add_tile", "delete_tile".
        """
        snapshot = {
            "type": action_type,
            "session_id": id(session),
            "session": session,
            "selected_cells": copy.deepcopy(
                [list(rects) for rects in session.selected_cells]
            ),
            "selected_polygons": copy.deepcopy(session.selected_polygons),
            "slice_metadata": copy.deepcopy(session.slice_metadata),
            "tile_colors": copy.deepcopy(session.tile_colors),
        }
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > MAX_HISTORY:
            self._undo_stack.pop(0)
        # Any new action invalidates the redo stack
        self._redo_stack.clear()

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def undo(self) -> Optional[Any]:
        """Undo the last tile action. Returns the affected session or None."""
        if not self._undo_stack:
            return None

        snapshot = self._undo_stack.pop()
        session = snapshot["session"]

        # Save current state to redo stack before restoring
        redo_snapshot = {
            "type": snapshot["type"],
            "session_id": snapshot["session_id"],
            "session": session,
            "selected_cells": copy.deepcopy(
                [list(rects) for rects in session.selected_cells]
            ),
            "selected_polygons": copy.deepcopy(session.selected_polygons),
            "slice_metadata": copy.deepcopy(session.slice_metadata),
            "tile_colors": copy.deepcopy(session.tile_colors),
        }
        self._redo_stack.append(redo_snapshot)

        # Restore from snapshot
        self._restore(session, snapshot)
        return session

    def redo(self) -> Optional[Any]:
        """Redo the last undone action. Returns the affected session or None."""
        if not self._redo_stack:
            return None

        snapshot = self._redo_stack.pop()
        session = snapshot["session"]

        # Save current state to undo stack before re-applying
        undo_snapshot = {
            "type": snapshot["type"],
            "session_id": snapshot["session_id"],
            "session": session,
            "selected_cells": copy.deepcopy(
                [list(rects) for rects in session.selected_cells]
            ),
            "selected_polygons": copy.deepcopy(session.selected_polygons),
            "slice_metadata": copy.deepcopy(session.slice_metadata),
            "tile_colors": copy.deepcopy(session.tile_colors),
        }
        self._undo_stack.append(undo_snapshot)

        # Restore from snapshot
        self._restore(session, snapshot)
        return session

    def clear(self) -> None:
        """Clear all history (e.g. on project close)."""
        self._undo_stack.clear()
        self._redo_stack.clear()

    @staticmethod
    def _restore(session: Any, snapshot: Dict[str, Any]) -> None:
        """Apply a snapshot back to a session."""
        session.selected_cells = [
            set(tuple(r) for r in rects) for rects in snapshot["selected_cells"]
        ]
        session.selected_polygons = copy.deepcopy(snapshot["selected_polygons"])
        session.slice_metadata = copy.deepcopy(snapshot["slice_metadata"])
        session.tile_colors = copy.deepcopy(snapshot.get("tile_colors", []))
        session.sync_metadata()
