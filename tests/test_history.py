"""Tests for the UndoManager."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.domain.history import UndoManager


class FakeSession:
    """Minimal session mock for undo/redo tests."""
    def __init__(self):
        self.selected_cells = []
        self.selected_polygons = []
        self.slice_metadata = []
        self.tile_colors = []

    def sync_metadata(self):
        pass


def test_push_and_undo():
    um = UndoManager()
    s = FakeSession()
    s.selected_cells = [{(0, 0, 100, 100)}]
    s.tile_colors = ["#00FFFF"]

    um.push(s, "add")
    # Modify
    s.selected_cells = [{(0, 0, 100, 100)}, {(200, 200, 300, 300)}]
    s.tile_colors = ["#00FFFF", "#FF6B6B"]

    # Undo should restore previous state
    result = um.undo()
    assert result is s
    assert len(s.selected_cells) == 1
    assert len(s.tile_colors) == 1


def test_redo():
    um = UndoManager()
    s = FakeSession()

    um.push(s, "add")
    s.selected_cells = [{(0, 0, 100, 100)}]

    um.undo()
    assert len(s.selected_cells) == 0

    um.redo()
    assert len(s.selected_cells) == 1


def test_undo_empty():
    um = UndoManager()
    assert um.undo() is None


def test_redo_empty():
    um = UndoManager()
    assert um.redo() is None


def test_push_clears_redo():
    um = UndoManager()
    s = FakeSession()

    um.push(s, "add")
    s.selected_cells = [{(0, 0, 100, 100)}]

    um.undo()
    assert um.can_redo()

    um.push(s, "new_action")
    assert not um.can_redo()


def test_clear():
    um = UndoManager()
    s = FakeSession()
    um.push(s, "add")
    um.clear()
    assert not um.can_undo()
    assert not um.can_redo()


def test_max_history():
    um = UndoManager()
    s = FakeSession()
    for i in range(60):
        um.push(s, f"action_{i}")
    assert len(um._undo_stack) == 50


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS  {name}")
            except AssertionError as e:
                print(f"  FAIL  {name}: {e}")
    print("Done.")
