import json

from app.infrastructure.tile_json import read_json_features


def _child(label, points, annotation_id):
    return {
        "meta": {
            "short_text": label,
            "id": annotation_id,
            "_points": [{"x": x, "y": y} for x, y in points],
        }
    }


def test_unlabeled_json_regions_inside_roi_are_named_by_roi_index(tmp_path):
    data = {
        "children": [
            _child("ROI", [(0, 0), (100, 0), (100, 100), (0, 100)], "roi-1"),
            _child("", [(10, 10), (20, 10), (20, 20), (10, 20)], "inside-1"),
            _child("N", [(30, 30), (40, 30), (40, 40), (30, 40)], "named"),
            _child("", [(150, 150), (160, 150), (160, 160), (150, 160)], "outside"),
        ]
    }
    path = tmp_path / "annotations.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    descriptors = read_json_features(str(path))
    names = [desc["slice"]["name"] for desc in descriptors]

    assert names == ["ROI", "INV_C1", "N", ""]
