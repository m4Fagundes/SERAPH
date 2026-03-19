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
