"""Tests for the selection math helpers."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.domain.selection import (
    rect_to_cells,
    cells_to_rects,
    find_connected_components,
    subtract_from_slice,
)


def test_rect_to_cells_single():
    """A rect exactly one grid cell should give one cell."""
    cells = rect_to_cells((0, 0, 100, 100), 100, 100)
    assert cells == {(0, 0)}


def test_rect_to_cells_multiple():
    """A rect spanning 2x2 cells."""
    cells = rect_to_cells((0, 0, 200, 200), 100, 100)
    assert cells == {(0, 0), (1, 0), (0, 1), (1, 1)}


def test_rect_to_cells_partial():
    """A rect that partially covers cells still includes them."""
    cells = rect_to_cells((50, 50, 150, 150), 100, 100)
    assert cells == {(0, 0), (1, 0), (0, 1), (1, 1)}


def test_cells_to_rects_single():
    cells = {(0, 0)}
    rects = cells_to_rects(cells, 100, 100, 1000, 1000)
    assert rects == {(0, 0, 100, 100)}


def test_cells_to_rects_horizontal():
    """Two horizontal cells merge into one rect."""
    cells = {(0, 0), (1, 0)}
    rects = cells_to_rects(cells, 100, 100, 1000, 1000)
    assert rects == {(0, 0, 200, 100)}


def test_cells_to_rects_vertical():
    """Two vertical cells merge into one rect."""
    cells = {(0, 0), (0, 1)}
    rects = cells_to_rects(cells, 100, 100, 1000, 1000)
    assert rects == {(0, 0, 100, 200)}


def test_cells_to_rects_empty():
    assert cells_to_rects(set(), 100, 100, 1000, 1000) == set()


def test_connected_components_single_component():
    cells = {(0, 0), (1, 0), (2, 0)}
    comps = find_connected_components(cells)
    assert len(comps) == 1
    assert comps[0] == cells


def test_connected_components_two():
    cells = {(0, 0), (2, 0)}  # gap at (1,0)
    comps = find_connected_components(cells)
    assert len(comps) == 2


def test_connected_components_empty():
    assert find_connected_components(set()) == []


def test_subtract_removes_single():
    """Removing a single-cell slice returns empty."""
    rects = {(0, 0, 100, 100)}
    result = subtract_from_slice(rects, 0, 0, 100, 100, 1000, 1000)
    assert result == []


def test_subtract_splits():
    """Removing the center of a 3-cell row splits into two."""
    rects = {(0, 0, 100, 100), (100, 0, 200, 100), (200, 0, 300, 100)}
    result = subtract_from_slice(rects, 1, 0, 100, 100, 1000, 1000)
    assert len(result) == 2


def test_subtract_no_overlap():
    """Subtracting a non-overlapping cell returns the slice unchanged."""
    rects = {(0, 0, 100, 100)}
    result = subtract_from_slice(rects, 5, 5, 100, 100, 1000, 1000)
    assert len(result) == 1


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS  {name}")
            except AssertionError as e:
                print(f"  FAIL  {name}: {e}")
    print("Done.")
