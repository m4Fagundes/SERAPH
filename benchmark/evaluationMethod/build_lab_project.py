"""Build a SERAPH .lab project from exported instance masks (severe + healthy).

Reconstructs one session per class: each ROI becomes a tile (laid out exactly like
"Import Slice Images Folder"), with Cellpose / CellViT / PathoSAM model masks — and
the GT where available — added as polygon segmentation layers. Polygons are placed
in absolute canvas coordinates so they line up with each tile.

Run:  python -m benchmark.evaluationMethod.build_lab_project
Output: benchmark/data/exports/benchmark_severe_healthy.lab (+ lab_images/ folders)
"""
from __future__ import annotations
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from app.domain.session import ImageSession
from app.domain.tile import Tile
from app.application.project_service import ProjectService

ROOT = Path("benchmark/data/oral_epithelium_activation_pack/oral_epithelium_activation_pack")
GTDIR = ROOT / "oral_epithelium_db" / "annotations" / "instance"
RGBDIR = ROOT / "cellpose_per_roi"
EXPORTS = Path("benchmark/data/exports")
LAB_IMG = EXPORTS / "lab_images"
LAB_PATH = EXPORTS / "benchmark_severe_healthy.lab"

CLASSES = {
    "severe": EXPORTS / "run1" / "severe_instance_masks_manifest.csv",
    "healthy": EXPORTS / "run_healthy" / "healthy_instance_masks_manifest.csv",
}
LAYER_COLORS = {
    "Macro Cellpose": "#00E5FF",
    "Macro CellViT-SAM": "#7CFFB2",
    "Macro PathoSAM": "#FFD166",
    "gt-pathology": "#FF5C8A",
}


def mask_to_polygons(label: np.ndarray, epsilon: float = 1.0) -> list[list[tuple[int, int]]]:
    """One simplified polygon per instance. approxPolyDP(epsilon) removes the
    pixel-staircase points (keeps shape within ~epsilon px) so the .lab stays light."""
    import cv2
    polys = []
    for uid in np.unique(label[label > 0]):
        m = (label == uid).astype(np.uint8)
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        c = max(cnts, key=cv2.contourArea)
        if epsilon > 0:
            c = cv2.approxPolyDP(c, epsilon, True)
        if len(c) < 3:
            continue
        polys.append([(int(p[0][0]), int(p[0][1])) for p in c])
    return polys


def build_session(cls: str, manifest_path: Path) -> ImageSession | None:
    if not manifest_path.exists():
        print(f"  [{cls}] manifest not found: {manifest_path}")
        return None
    df = pd.read_csv(manifest_path)
    export_dir = manifest_path.parent
    rois = list(df["slice_name"].dropna().unique())

    # 1. flat image folder of roi_rgb.png named by ROI (pyramid lays these out)
    img_dir = LAB_IMG / cls
    if img_dir.exists():
        shutil.rmtree(img_dir)
    img_dir.mkdir(parents=True, exist_ok=True)
    kept = []
    for roi in rois:
        src = RGBDIR / cls / roi / "roi_rgb.png"
        if src.exists():
            shutil.copyfile(src, img_dir / f"{roi}.png")
            kept.append(roi)
    if not kept:
        print(f"  [{cls}] no roi_rgb images found — skipping")
        return None

    # 2. session + pyramid layout
    s = ImageSession(str(img_dir))
    s.name = f"benchmark_{cls}"
    s.tiles = []
    item_by_name = {it["name"]: it for it in s.pyramid.items}

    # 3. one tile per ROI with model + GT layers (absolute coords)
    for roi in kept:
        it = item_by_name.get(roi)
        if it is None:
            continue
        ox, oy, w, h = it["x"], it["y"], it["width"], it["height"]
        tile = Tile(rects=[(ox, oy, ox + w, oy + h)])
        tile.metadata["name"] = roi

        for _, r in df[df["slice_name"] == roi].iterrows():
            layer = r["layer"]
            mask = np.load(export_dir / r["npy"]).astype(np.int32)
            polys = [[(px + ox, py + oy) for px, py in poly] for poly in mask_to_polygons(mask)]
            if polys:
                tile.add_layer(layer, layer, polys, LAYER_COLORS.get(layer, "#00E5FF"))

        gtp = GTDIR / cls / f"{roi}.png"
        if gtp.exists():
            gt = np.array(Image.open(gtp)).astype(np.int32)
            polys = [[(px + ox, py + oy) for px, py in poly] for poly in mask_to_polygons(gt)]
            if polys:
                tile.add_layer("gt-pathology", "gt-pathology", polys, LAYER_COLORS["gt-pathology"])

        s.tiles.append(tile)

    print(f"  [{cls}] {len(s.tiles)} tiles, canvas {s.pyramid.image_width}x{s.pyramid.image_height}")
    return s


def main():
    sessions = []
    for cls, manifest in CLASSES.items():
        print(f"Building session: {cls}")
        sess = build_session(cls, manifest)
        if sess is not None:
            sessions.append(sess)
    if not sessions:
        print("No sessions built — aborting.")
        return
    ProjectService().save_project(str(LAB_PATH), sessions)
    print(f"\nSaved .lab -> {LAB_PATH}  ({len(sessions)} session(s))")


if __name__ == "__main__":
    main()
