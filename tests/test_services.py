"""Tests for ProjectService save/load roundtrip."""

import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.application.services import ProjectService


class FakeSession:
    """Minimal session mock for save/load tests."""
    def __init__(self, path="test_image.png"):
        self.path = path
        self.name = os.path.basename(path)
        self.grid_w = 500
        self.grid_h = 500
        self.zoom_level = 2.0
        self.camera_x = 100
        self.camera_y = 200
        self.selected_cells = [{(0, 0, 500, 500)}, {(500, 0, 1000, 500)}]
        self.selected_polygons = [None, None]
        self.slice_metadata = [
            {"name": "Tile A", "description": "First", "microns_per_pixel": "0.5"},
            {"name": "Tile B", "description": "Second", "microns_per_pixel": "1.0"},
        ]
        self.tile_colors = ["#00FFFF", "#FF6B6B"]
        self.grid_color = "#FFFF00"
        self.export_dir = None
        self.export_format = None


def test_save_roundtrip():
    """Save project and verify JSON structure contains expected keys."""
    ps = ProjectService()
    s = FakeSession()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".lab", delete=False) as f:
        path = f.name

    try:
        ps.save_project(path, [s])
        with open(path, "r") as f:
            data = json.load(f)

        assert len(data) == 1
        item = data[0]
        assert "path" in item
        assert "abs_path" in item
        assert "grid_w" in item
        assert item["grid_w"] == 500
        assert item["tile_colors"] == ["#00FFFF", "#FF6B6B"]
        assert len(item["slice_metadata"]) == 2
        assert item["slice_metadata"][0]["name"] == "Tile A"
    finally:
        os.unlink(path)


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS  {name}")
            except AssertionError as e:
                print(f"  FAIL  {name}: {e}")
    print("Done.")
