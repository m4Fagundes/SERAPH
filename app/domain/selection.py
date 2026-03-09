"""
Selection math helpers for grid-based image slicing.

Selections are stored as pixel-rect tuples (x1, y1, x2, y2).
This module provides decomposition, connected component analysis,
and merging to support smart add/subtract operations.
"""

from collections import deque
from typing import Any, List, Optional, Set, Tuple


def draw_exclusion_rects(draw: Any, exclusions: List[Tuple[float, float, float, float]], offset_x: float, offset_y: float, scale: float) -> None:
    """Draw exclusion rectangles onto a PIL mask (fill=0).

    Each exclusion is an (x1, y1, x2, y2) tuple in image coordinates.
    """
    for rect in exclusions:
        if not rect or len(rect) != 4:
            continue
        try:
            x1, y1, x2, y2 = float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])
        except (TypeError, ValueError):
            continue  # skip old stroke-format data
        sx1 = (x1 - offset_x) * scale
        sy1 = (y1 - offset_y) * scale
        sx2 = (x2 - offset_x) * scale
        sy2 = (y2 - offset_y) * scale
        draw.rectangle([sx1, sy1, sx2, sy2], fill=0)


def rect_to_cells(rect: Tuple[int, int, int, int], grid_w: int, grid_h: int) -> Set[Tuple[int, int]]:
    """Decompose a pixel rect into a set of (col, row) grid cells."""
    x1, y1, x2, y2 = rect
    col_start = x1 // grid_w
    row_start = y1 // grid_h
    # Use ceil-like logic: a rect ending at x2 covers up to col (x2-1)//grid_w
    col_end = max(col_start, (x2 - 1) // grid_w)
    row_end = max(row_start, (y2 - 1) // grid_h)
    cells = set()
    for c in range(col_start, col_end + 1):
        for r in range(row_start, row_end + 1):
            cells.add((c, r))
    return cells


def cells_to_rects(cells: Set[Tuple[int, int]], grid_w: int, grid_h: int, img_w: int, img_h: int) -> Set[Tuple[int, int, int, int]]:
    """Merge a set of (col, row) grid cells into a minimal set of pixel rects.
    
    Algorithm:
    1. Sort cells by (row, col)
    2. Create horizontal runs of consecutive cells per row
    3. Merge vertically adjacent runs with same column range
    4. Convert merged runs to pixel rects
    """
    if not cells:
        return set()

    # Step 1: horizontal runs per row
    sorted_cells = sorted(cells, key=lambda c: (c[1], c[0]))
    runs = []  # (col_start, col_end, row)
    for col, row in sorted_cells:
        if runs and runs[-1][2] == row and runs[-1][1] + 1 == col:
            runs[-1] = (runs[-1][0], col, row)
        else:
            runs.append((col, col, row))

    # Step 2: merge vertically adjacent runs with same col range
    merged = []  # (col_start, col_end, row_start, row_end)
    for col_s, col_e, row in runs:
        found = False
        for i, (cs, ce, rs, re) in enumerate(merged):
            if cs == col_s and ce == col_e and re + 1 == row:
                merged[i] = (cs, ce, rs, row)
                found = True
                break
        if not found:
            merged.append((col_s, col_e, row, row))

    # Step 3: convert to pixel rects
    result = set()
    for cs, ce, rs, re in merged:
        px1 = cs * grid_w
        py1 = rs * grid_h
        px2 = min((ce + 1) * grid_w, img_w)
        py2 = min((re + 1) * grid_h, img_h)
        result.add((px1, py1, px2, py2))
    return result


def find_connected_components(cells: Set[Tuple[int, int]]) -> List[Set[Tuple[int, int]]]:
    """BFS flood fill with 4-connectivity. Returns list of cell sets."""
    if not cells:
        return []
    remaining = set(cells)
    components = []
    while remaining:
        start = next(iter(remaining))
        component = set()
        queue = deque([start])
        while queue:
            cell = queue.popleft()
            if cell in component:
                continue
            if cell not in remaining:
                continue
            component.add(cell)
            remaining.discard(cell)
            c, r = cell
            for nc, nr in [(c-1, r), (c+1, r), (c, r-1), (c, r+1)]:
                if (nc, nr) in remaining:
                    queue.append((nc, nr))
        components.append(component)
    return components


def _find_overlapping(selections: Set[Tuple[int, int, int, int]], cx1: int, cy1: int, cx2: int, cy2: int) -> Set[Tuple[int, int, int, int]]:
    """Find all pixel rects that overlap a given region."""
    return {s for s in selections if s[0] < cx2 and s[2] > cx1 and s[1] < cy2 and s[3] > cy1}


def _find_adjacent(selections: Set[Tuple[int, int, int, int]], cx1: int, cy1: int, cx2: int, cy2: int) -> Set[Tuple[int, int, int, int]]:
    """Find all pixel rects that touch (share an edge with) a given region."""
    return {s for s in selections if s[0] <= cx2 and s[2] >= cx1 and s[1] <= cy2 and s[3] >= cy1}


def subtract_from_slice(slice_rects: Set[Tuple[int, int, int, int]], col: int, row: int, grid_w: int, grid_h: int, img_w: int, img_h: int) -> List[Set[Tuple[int, int, int, int]]]:
    """Remove a grid cell from a slice, potentially splitting it.
    
    Returns a list of sets: 1 set if still connected, 2+ if disconnected,
    empty list if the entire slice was removed.
    """
    cx1 = col * grid_w
    cy1 = row * grid_h
    cx2 = min(cx1 + grid_w, img_w)
    cy2 = min(cy1 + grid_h, img_h)

    # Check if any rect in this slice overlaps the cell
    overlapping = {r for r in slice_rects if r[0] < cx2 and r[2] > cx1 and r[1] < cy2 and r[3] > cy1}
    if not overlapping:
        return [slice_rects]

    # Decompose ALL rects in the slice to cells
    all_cells = set()
    for rect in slice_rects:
        all_cells |= rect_to_cells(rect, grid_w, grid_h)

    # Remove the target cell
    all_cells.discard((col, row))

    if not all_cells:
        return []

    # Connected components
    components = find_connected_components(all_cells)

    # Each component becomes a new slice
    return [cells_to_rects(comp, grid_w, grid_h, img_w, img_h) for comp in components]
