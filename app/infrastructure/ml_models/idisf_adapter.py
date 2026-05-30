import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

from PIL.Image import Image

from app.domain.interfaces.segmentation_model import ISegmentationModel

logger = logging.getLogger(__name__)


class IDISFAdapter(ISegmentationModel):
    """Click-based adapter for the official iDISF implementation."""

    def __init__(
        self,
        repo_dir: str | None = None,
        crop_size: int = 256,
        n0: int = 160,
        iterations: int = 4,
        path_cost_function: int = 4,
        c1: float = 0.7,
        c2: float = 0.8,
    ):
        root = Path(__file__).resolve().parents[3]
        self.repo_dir = Path(repo_dir) if repo_dir else root / "iDISF"
        self.crop_size = crop_size
        self.n0 = n0
        self.iterations = iterations
        self.path_cost_function = path_cost_function
        self.c1 = c1
        self.c2 = c2
        self._binary_checked = False
        self._binary_path: Path | None = None

    @property
    def name(self) -> str:
        return "iDISF"

    def set_parameters(
        self,
        *,
        crop_size: int | None = None,
        n0: int | None = None,
        iterations: int | None = None,
        path_cost_function: int | None = None,
        c1: float | None = None,
        c2: float | None = None,
    ) -> None:
        if crop_size is not None:
            self.crop_size = max(64, int(crop_size))
        if n0 is not None:
            self.n0 = max(1, int(n0))
        if iterations is not None:
            self.iterations = max(1, int(iterations))
        if path_cost_function is not None:
            self.path_cost_function = max(1, min(6, int(path_cost_function)))
        if c1 is not None:
            self.c1 = max(0.1, min(1.0, float(c1)))
        if c2 is not None:
            self.c2 = max(0.1, min(1.0, float(c2)))

    def predict(self, image: Image, click_x: int, click_y: int) -> List[Tuple[int, int]]:
        binary = self._ensure_binary()
        if binary is None:
            logger.warning("iDISF binary is not available. Returning empty segmentation.")
            return []

        import cv2
        import numpy as np

        if image.mode != "RGB":
            image = image.convert("RGB")

        crop, local_x, local_y, offset_x, offset_y = self._crop_around_click(image, click_x, click_y)

        with tempfile.TemporaryDirectory(prefix="seraph_idisf_") as tmp:
            tmp_dir = Path(tmp)
            input_path = tmp_dir / "input.ppm"
            markers_path = tmp_dir / "markers.txt"
            output_prefix = tmp_dir / "idisf"

            crop.save(input_path)
            markers_path.write_text(
                self._marker_file_text(crop.width, crop.height, local_x, local_y),
                encoding="ascii",
            )

            cmd = [
                str(binary),
                "--rem",
                "1",
                "--i",
                str(input_path),
                "--n0",
                str(self.n0),
                "--it",
                str(self.iterations),
                "--f",
                str(self.path_cost_function),
                "--file",
                str(markers_path),
                "--obj_markers",
                "1",
                "--c1",
                str(self.c1),
                "--c2",
                str(self.c2),
                "--o",
                str(output_prefix),
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(self.repo_dir),
                    text=True,
                    capture_output=True,
                    timeout=20,
                )
            except Exception as exc:
                logger.exception("iDISF execution failed: %s", exc)
                return []

            if proc.returncode != 0:
                logger.error("iDISF returned %s\nstdout=%s\nstderr=%s", proc.returncode, proc.stdout, proc.stderr)
                return []

            labels_path = Path(str(output_prefix) + "_labels.pgm")
            if not labels_path.exists():
                logger.error("iDISF did not produce labels output: %s", labels_path)
                return []

            from PIL import Image as PILImage

            labels = np.array(PILImage.open(labels_path))
            mask = self._mask_for_click_label(labels, local_x, local_y)
            if mask is None:
                return []

            contours, _ = cv2.findContours(mask.astype("uint8") * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return []

            contour = max(contours, key=cv2.contourArea)
            if cv2.contourArea(contour) < 8:
                return []

            epsilon = max(1.0, 0.006 * cv2.arcLength(contour, True))
            contour = cv2.approxPolyDP(contour, epsilon, True)

            polygon: List[Tuple[int, int]] = []
            for point in contour:
                px, py = point[0]
                gx = int(px) + offset_x
                gy = int(py) + offset_y
                gx = max(0, min(gx, image.width - 1))
                gy = max(0, min(gy, image.height - 1))
                polygon.append((gx, gy))

            logger.info("iDISF segmented click (%d, %d) with %d polygon points", click_x, click_y, len(polygon))
            return polygon

    def _crop_around_click(self, image: Image, click_x: int, click_y: int) -> tuple[Image, int, int, int, int]:
        crop_size = max(64, int(self.crop_size))
        half = crop_size // 2
        x1 = max(0, click_x - half)
        y1 = max(0, click_y - half)
        x2 = min(image.width, click_x + half)
        y2 = min(image.height, click_y + half)

        if x2 - x1 < crop_size and x1 > 0:
            x1 = max(0, x2 - crop_size)
        if y2 - y1 < crop_size and y1 > 0:
            y1 = max(0, y2 - crop_size)

        crop = image.crop((x1, y1, x2, y2))
        return crop, click_x - x1, click_y - y1, x1, y1

    def _marker_file_text(self, width: int, height: int, click_x: int, click_y: int) -> str:
        bg_points = self._background_points(width, height)
        scribbles = [[(click_x, click_y)], bg_points]
        lines = [str(len(scribbles))]
        for scribble in scribbles:
            lines.append(str(len(scribble)))
            lines.extend(f"{x};{y}" for x, y in scribble)
        return "\n".join(lines)

    def _background_points(self, width: int, height: int) -> list[tuple[int, int]]:
        inset = 2
        step = max(8, min(width, height) // 12)
        points: list[tuple[int, int]] = []

        for x in range(inset, max(inset + 1, width - inset), step):
            points.append((x, inset))
            points.append((x, height - 1 - inset))
        for y in range(inset, max(inset + 1, height - inset), step):
            points.append((inset, y))
            points.append((width - 1 - inset, y))

        return [(max(0, min(x, width - 1)), max(0, min(y, height - 1))) for x, y in points]

    def _mask_for_click_label(self, labels, click_x: int, click_y: int):
        import cv2
        import numpy as np
        from scipy import ndimage as ndi

        click_x = max(0, min(click_x, labels.shape[1] - 1))
        click_y = max(0, min(click_y, labels.shape[0] - 1))
        seed_label = labels[click_y, click_x]
        mask = labels == seed_label

        num_labels, connected = cv2.connectedComponents(mask.astype("uint8"), connectivity=8)
        component_id = connected[click_y, click_x]
        if num_labels <= 1 or component_id == 0:
            return None

        component = connected == component_id
        component = ndi.binary_fill_holes(component)
        kernel = np.ones((3, 3), dtype=np.uint8)
        component = cv2.morphologyEx(component.astype("uint8"), cv2.MORPH_OPEN, kernel).astype(bool)
        component = cv2.morphologyEx(component.astype("uint8"), cv2.MORPH_CLOSE, kernel).astype(bool)
        return component

    def _ensure_binary(self) -> Path | None:
        if self._binary_checked:
            return self._binary_path

        self._binary_checked = True
        exe_name = "iDISF_demo.exe" if os.name == "nt" else "iDISF_demo"
        binary = self.repo_dir / "bin" / exe_name
        if binary.exists():
            self._binary_path = binary
            return binary

        try:
            self._build_binary(binary)
        except Exception as exc:
            logger.error("Failed to build iDISF binary: %s", exc)
            self._binary_path = None
            return None

        self._binary_path = binary if binary.exists() else None
        return self._binary_path

    def _build_binary(self, binary: Path) -> None:
        src_dir = self.repo_dir / "src"
        obj_dir = self.repo_dir / "obj"
        lib_dir = self.repo_dir / "lib"
        bin_dir = self.repo_dir / "bin"
        obj_dir.mkdir(exist_ok=True)
        lib_dir.mkdir(exist_ok=True)
        bin_dir.mkdir(exist_ok=True)

        sources = ["Utils", "IntList", "Color", "PrioQueue", "Image", "Graph", "iDISF"]
        objects = []
        for source in sources:
            obj_path = obj_dir / f"{source}.o"
            objects.append(obj_path)
            subprocess.run(
                [
                    "gcc",
                    "-g",
                    "-Wall",
                    "-fPIC",
                    "-std=gnu11",
                    "-pedantic",
                    "-Wno-unused-result",
                    "-O3",
                    "-fopenmp",
                    "-c",
                    str(src_dir / f"{source}.c"),
                    "-o",
                    str(obj_path),
                    "-I",
                    str(self.repo_dir / "externals"),
                    "-I",
                    str(self.repo_dir / "include"),
                    "-lm",
                ],
                check=True,
            )

        lib_path = lib_dir / "libidisf.a"
        subprocess.run(["ar", "csr", str(lib_path), *[str(obj) for obj in objects]], check=True)

        subprocess.run(
            [
                "gcc",
                "-g",
                "-Wall",
                "-fPIC",
                "-pedantic",
                "-Wno-unused-result",
                "-O3",
                "-fopenmp",
                "-ffast-math",
                "-march=skylake",
                "-mfma",
                str(self.repo_dir / "iDISF_demo.c"),
                "-o",
                str(binary),
                "-I",
                str(self.repo_dir / "externals"),
                "-I",
                str(self.repo_dir / "include"),
                "-L",
                str(lib_dir),
                "-lidisf",
                "-lm",
            ],
            check=True,
        )
