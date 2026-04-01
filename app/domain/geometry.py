from typing import List, Tuple

def is_point_in_polygon(x: float, y: float, polygon: List[Tuple[int, int]]) -> bool:
    """
    Ray casting algorithm to determine if a point is inside a polygon.
    
    Args:
        x: The X coordinate of the point.
        y: The Y coordinate of the point.
        polygon: A list of (x, y) coordinates defining the polygon.
        
    Returns:
        True if the point is inside the polygon, False otherwise.
    """
    if not polygon or len(polygon) < 3:
        return False
        
    n = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xints:
                        inside = not inside
        p1x, p1y = p2x, p2y
        
    return inside

def get_polygon_bounding_box(polygon: List[Tuple[int, int]]) -> Tuple[int, int, int, int]:
    """
    Computes the bounding box for a given polygon.
    
    Args:
        polygon: List of (x, y) coordinates.
        
    Returns:
        A tuple of (min_x, min_y, max_x, max_y).
    """
    if not polygon:
        return (0, 0, 0, 0)
    
    min_x = min(pt[0] for pt in polygon)
    min_y = min(pt[1] for pt in polygon)
    max_x = max(pt[0] for pt in polygon)
    max_y = max(pt[1] for pt in polygon)
    return (min_x, min_y, max_x, max_y)

def is_rect_overlapping(rect1: Tuple[int, int, int, int], rect2: Tuple[int, int, int, int]) -> bool:
    """
    Checks if two rectangles are overlapping.
    
    Args:
        rect1: (min_x, min_y, max_x, max_y)
        rect2: (min_x, min_y, max_x, max_y)
        
    Returns:
        True if overlapping, False otherwise.
    """
    r1_x1, r1_y1, r1_x2, r1_y2 = rect1
    r2_x1, r2_y1, r2_x2, r2_y2 = rect2
    
    # If one rectangle is on left side of other
    if r1_x1 >= r2_x2 or r2_x1 >= r1_x2:
        return False
        
    # If one rectangle is above other
    if r1_y1 >= r2_y2 or r2_y1 >= r1_y2:
        return False
        
    return True
