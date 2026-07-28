import logging
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue
from threading import Lock
from typing import List, Optional, Tuple
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QDialog,
    QDialogButtonBox, QScrollArea, QSizePolicy, QComboBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QBrush, QColor, QCursor

from app.domain.geometry import get_polygon_centroid
from app.domain.tile import LAYER_COLORS
from app.interface.gui.design_system import COLORS, SPACE, SIZE, RADIUS
from app.interface.gui.theme_manager import themed


def _style_hint() -> str:
    return f"color: {COLORS['text_muted']}; font-size: 12px;"


def _style_count() -> str:
    return f"color: {COLORS['text_primary']}; font-size: 12px; font-weight: 600;"


def _style_card_title() -> str:
    return (
        f"font-size: 13px; font-weight: 600;"
        f" color: {COLORS['text_primary']}; background: transparent; border: none;"
    )


def _style_card_desc() -> str:
    return (
        f"font-size: 11px; color: {COLORS['text_muted']};"
        f" background: transparent; border: none;"
    )


def _style_field_label() -> str:
    return f"color: {COLORS['text_muted']}; font-size: 11px; background: transparent;"


def _style_field_label_strong() -> str:
    return (
        f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: 600;"
        " background: transparent;"
    )


def _style_inline_row() -> str:
    return (
        f"background: {COLORS['bg_panel']}; border-radius: {RADIUS['sm']}px;"
        f" border: 1px solid {COLORS['border_default']};"
    )


def _style_ref_unset() -> str:
    return (
        f"color: {COLORS['text_muted']}; font-size: 11px;"
        f" background: transparent; border: none;"
    )


def _style_ref_ready() -> str:
    return (
        f"color: {COLORS['accent_success']};"
        f" font-size: 11px; font-weight: 600; background: transparent; border: none;"
    )
from app.interface.gui.widgets.buttons import ActionButton, SecondaryButton

logger = logging.getLogger(__name__)

# ── Model registry ────────────────────────────────────────────────────────────

_KNOWN_MODELS = [
    ("Cellpose (cpsam)",   LAYER_COLORS[0]),
    ("NucleAI",            LAYER_COLORS[1]),
    ("CellViT-SAM",        LAYER_COLORS[3]),
    ("PathoSAM (ViT-L)",   LAYER_COLORS[2]),
    ("DINOSim (small)",    LAYER_COLORS[1]),
    ("InstanSeg",          LAYER_COLORS[4]),
]

def _layer_name(model_name: str) -> str:
    short = model_name.split(" ")[0]
    return f"Macro {short}"


# ── DINOSim reference-point dialog ───────────────────────────────────────────

def _pil_to_pixmap(pil_img) -> QPixmap:
    """Convert a PIL Image (RGB) to a QPixmap without external dependencies."""
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    data = pil_img.tobytes("raw", "RGB")
    qimg = QImage(data, pil_img.width, pil_img.height,
                  pil_img.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


class _ClickableImageLabel(QLabel):
    """QLabel that emits (x, y) in display coords on left-click."""
    clicked = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(int(event.position().x()), int(event.position().y()))
        super().mousePressEvent(event)


class DINOSimReferenceDialog(QDialog):
    """
    Dialog for picking reference nuclei on the current tile.

    The user clicks on representative nuclei; each click is recorded as a
    reference point. Accepts and returns the selected coordinates in original
    tile pixel space.

    Usage:
        dlg = DINOSimReferenceDialog(tile_pil_image, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            coords = dlg.reference_coords   # List[Tuple[int, int]] in tile pixels
    """

    # Max display dimension (longest side) — keeps the dialog manageable
    _MAX_DISPLAY_PX = 640

    def __init__(self, tile_image, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DINOSim — Set Reference Points")
        self.setModal(True)
        self.setMinimumWidth(500)

        self._tile_image = tile_image
        self._display_scale: float = 1.0
        self._base_pixmap: Optional[QPixmap] = None
        self._coords: List[Tuple[int, int]] = []  # in original tile space

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACE[3])

        # ── Instruction text ──────────────────────────────────────────────────
        instr = QLabel(
            "Click on representative nuclei below.\n"
            "DINOSim will find visually similar cells across all tiles."
        )
        instr.setWordWrap(True)
        themed(instr, _style_hint)
        layout.addWidget(instr)

        # ── Point counter ─────────────────────────────────────────────────────
        self._lbl_count = QLabel("0 points selected")
        themed(self._lbl_count, _style_count)
        layout.addWidget(self._lbl_count)

        # ── Tile image ────────────────────────────────────────────────────────
        self._img_label = _ClickableImageLabel()
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.clicked.connect(self._on_image_click)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setWidget(self._img_label)
        scroll.setMinimumHeight(300)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(scroll, stretch=1)

        self._load_tile_image()

        # ── Clear button ──────────────────────────────────────────────────────
        btn_clear = SecondaryButton("Clear All Points")
        btn_clear.clicked.connect(self._clear_points)
        layout.addWidget(btn_clear)

        # ── OK / Cancel ───────────────────────────────────────────────────────
        self._btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._btn_box.accepted.connect(self.accept)
        self._btn_box.rejected.connect(self.reject)
        self._btn_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout.addWidget(self._btn_box)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def reference_coords(self) -> List[Tuple[int, int]]:
        """Selected (x, y) coordinates in original tile pixel space."""
        return list(self._coords)

    # ── Image loading ─────────────────────────────────────────────────────────

    def _load_tile_image(self) -> None:
        try:
            w, h = self._tile_image.size
            scale = min(self._MAX_DISPLAY_PX / w, self._MAX_DISPLAY_PX / h, 1.0)
            self._display_scale = scale
            disp_w, disp_h = int(w * scale), int(h * scale)

            resized = self._tile_image.resize((disp_w, disp_h))
            self._base_pixmap = _pil_to_pixmap(resized)
            self._img_label.setFixedSize(disp_w, disp_h)
            self._img_label.setPixmap(self._base_pixmap.copy())
        except Exception as exc:
            logger.error("DINOSimReferenceDialog: failed to load tile image: %s", exc)
            self._img_label.setText("(failed to load tile image)")

    # ── Point management ─────────────────────────────────────────────────────

    def _on_image_click(self, disp_x: int, disp_y: int) -> None:
        orig_x = int(disp_x / self._display_scale)
        orig_y = int(disp_y / self._display_scale)
        self._coords.append((orig_x, orig_y))
        self._redraw_points()
        self._update_count()

    def _clear_points(self) -> None:
        self._coords.clear()
        if self._base_pixmap:
            self._img_label.setPixmap(self._base_pixmap.copy())
        self._update_count()

    def _update_count(self) -> None:
        n = len(self._coords)
        self._lbl_count.setText(f"{n} point{'s' if n != 1 else ''} selected")
        ok_btn = self._btn_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setEnabled(n > 0)

    def _redraw_points(self) -> None:
        if self._base_pixmap is None:
            return
        pixmap = self._base_pixmap.copy()
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dot_r = max(5, int(8 * self._display_scale))
        for i, (ox, oy) in enumerate(self._coords):
            dx = int(ox * self._display_scale)
            dy = int(oy * self._display_scale)
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.setBrush(QBrush(QColor(255, 220, 0, 200)))
            painter.drawEllipse(QPoint(dx, dy), dot_r, dot_r)
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(QPoint(dx + dot_r + 2, dy + 4), str(i + 1))
        painter.end()
        self._img_label.setPixmap(pixmap)


# ── Workers ───────────────────────────────────────────────────────────────────

class MacroPipelineWorker(QThread):
    progress = pyqtSignal(int, int, str)   # current, total, status_text
    time_update = pyqtSignal(str, float)   # phase, elapsed_time
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, session, batch_service, interactive_service,
                 cellpose_model, nuclick_model, cellpose_params, run_nuclick=True,
                 slice_indices: Optional[list[int]] = None,
                 gpu_ids: Optional[list[int]] = None):
        super().__init__()
        self.session = session
        self.batch_service = batch_service
        self.interactive_service = interactive_service
        self.cellpose_model = cellpose_model
        self.nuclick_model = nuclick_model
        self.cellpose_params = cellpose_params
        self.run_nuclick = run_nuclick
        self.slice_indices = list(slice_indices) if slice_indices is not None else list(range(len(session.tiles)))
        self.gpu_ids = list(gpu_ids) if gpu_ids else []
        self.pipeline_run_id = f"macro-{time.monotonic_ns()}"

        self.is_paused = False
        self.is_cancelled = False

        self.current_phase = 1
        self.current_slice_pos = 0

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            total_slices = len(self.slice_indices)
            if total_slices == 0:
                self.finished.emit()
                return

            # PHASE 1: Cellpose
            if self.current_phase == 1:
                start_time = time.monotonic()
                if self.gpu_ids and self.current_slice_pos == 0:
                    self._run_cellpose_multigpu(total_slices)
                else:
                    self._run_cellpose_serial(total_slices)

                elapsed = time.monotonic() - start_time
                self.time_update.emit("Cellpose", elapsed)
                self.current_slice_pos = 0

                if self.run_nuclick:
                    self.current_phase = 2
                else:
                    self.finished.emit()
                    return

            # PHASE 2: NuClick — seeds from Cellpose centroids
            if self.current_phase == 2 and self.run_nuclick:
                start_time = time.monotonic()
                if self.gpu_ids and self.current_slice_pos == 0:
                    self._run_nuclick_multigpu(total_slices)
                else:
                    self._run_nuclick_serial(total_slices)

                elapsed = time.monotonic() - start_time
                self.time_update.emit("NuClick", elapsed)

            self.finished.emit()

        except Exception as e:
            logger.exception("Error in MacroPipelineWorker: %s", e)
            self.error.emit(str(e))

    def _cellpose_centroids_for_slice(self, slice_idx: int) -> list[tuple[int, int]]:
        tile = self.session.tiles[slice_idx]
        centroids = []
        for layer in tile.segmentation_layers:
            if (
                layer.get("name") == "Macro Cellpose"
                and layer.get("pipeline_run_id") == self.pipeline_run_id
            ):
                for poly in layer.get("polygons", []):
                    centroids.append(get_polygon_centroid(poly))
        return centroids

    def _run_nuclick_serial(self, total_slices: int) -> None:
        for pos in range(self.current_slice_pos, total_slices):
            while self.is_paused and not self.is_cancelled:
                time.sleep(0.1)
            if self.is_cancelled:
                return

            i = self.slice_indices[pos]
            self.progress.emit(pos, total_slices, f"NuClick: Slice {i+1} ({pos+1}/{total_slices})…")
            slice_start = time.monotonic()
            vram_start = self._current_vram_snapshot()

            tile = self.session.tiles[i]
            centroids = self._cellpose_centroids_for_slice(i)

            if centroids:
                nuclick_polys = self.interactive_service.segment_at_points(
                    self.nuclick_model, self.session, i, centroids
                )
                if nuclick_polys:
                    self._add_nuclick_layer(tile, nuclick_polys, time.monotonic() - slice_start, vram_start)

                    self.current_slice_pos = pos + 1
                    self.progress.emit(pos + 1, total_slices, f"NuClick: Slice {i+1} done ({pos+1}/{total_slices})")

    def _run_nuclick_multigpu(self, total_slices: int) -> None:
        from app.infrastructure.ml_models.nuclick_adapter import NuClickAdapter
        from app.infrastructure.ml_models.gpu_memory import cleanup_cuda_memory, cuda_memory_snapshot

        prepared_items = []
        for pos, i in enumerate(self.slice_indices):
            while self.is_paused and not self.is_cancelled:
                time.sleep(0.1)
            if self.is_cancelled:
                return

            centroids = self._cellpose_centroids_for_slice(i)
            if not centroids:
                continue
            prepared = self.batch_service.prepare_tile_image(self.session, i)
            if prepared is None:
                continue
            pil_img, origin = prepared
            bx1, by1 = origin
            local_points = [(gx - bx1, gy - by1) for gx, gy in centroids]
            prepared_items.append((pos, i, pil_img, origin, local_points))

        if not prepared_items:
            return

        work_queue = Queue()
        result_queue = Queue()
        for item in prepared_items:
            work_queue.put(item)

        completed = 0
        completed_lock = Lock()

        def run_on_device(device_id: int):
            nonlocal completed
            adapter = NuClickAdapter(device_id=device_id)
            try:
                while not self.is_cancelled:
                    try:
                        pos, i, pil_img, origin, local_points = work_queue.get_nowait()
                    except Empty:
                        break
                    if self.is_cancelled:
                        break
                    slice_start = time.monotonic()
                    vram_start = cuda_memory_snapshot(device_id)
                    local_polys = adapter.predict_batch(pil_img, local_points)
                    global_polys = self._offset_polygons(local_polys, origin)
                    result_queue.put((pos, i, global_polys, time.monotonic() - slice_start, device_id, vram_start))
                    with completed_lock:
                        completed += 1
                        self.progress.emit(
                            completed,
                            total_slices,
                            f"NuClick GPU {device_id}: {completed}/{total_slices} slices done",
                        )
                    work_queue.task_done()
            finally:
                cleanup_cuda_memory(f"after NuClick GPU {device_id}")

        with ThreadPoolExecutor(max_workers=len(self.gpu_ids), thread_name_prefix="nuclick-gpu") as pool:
            futures = [pool.submit(run_on_device, device_id) for device_id in self.gpu_ids]
            processed = 0
            while processed < len(prepared_items):
                if self.is_cancelled:
                    return
                try:
                    _, i, polygons, elapsed, device_id, vram_start = result_queue.get(timeout=0.2)
                except Empty:
                    if all(f.done() for f in futures):
                        break
                    continue
                if polygons:
                    self._add_nuclick_layer(self.session.tiles[i], polygons, elapsed, vram_start)
                    logger.info(
                        "Macro NuClick multi-GPU: slice %d completed on CUDA device %d with %d polygons",
                        i + 1, device_id, len(polygons),
                    )
                processed += 1
                self.current_slice_pos = processed
            for future in futures:
                future.result()

    def _run_cellpose_serial(self, total_slices: int) -> None:
        for pos in range(self.current_slice_pos, total_slices):
            while self.is_paused and not self.is_cancelled:
                time.sleep(0.1)
            if self.is_cancelled:
                return

            i = self.slice_indices[pos]
            self.progress.emit(pos, total_slices, f"Cellpose: Slice {i+1} ({pos+1}/{total_slices})…")
            slice_start = time.monotonic()

            polys = self.batch_service.segment_tile(
                self.cellpose_model, self.session, i,
                **self.cellpose_params
            )

            if polys:
                self._add_cellpose_layer(
                    i,
                    polys,
                    time.monotonic() - slice_start,
                    self.batch_service.probability_map(),
                    self.batch_service.vram_snapshot_start()
                    if hasattr(self.batch_service, "vram_snapshot_start")
                    else None,
                    self.batch_service.instance_map()
                    if hasattr(self.batch_service, "instance_map")
                    else None,
                )

            self.current_slice_pos = pos + 1
            self.progress.emit(pos + 1, total_slices, f"Cellpose: Slice {i+1} done ({pos+1}/{total_slices})")

    def _run_cellpose_multigpu(self, total_slices: int) -> None:
        from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
        from app.infrastructure.ml_models.gpu_memory import cleanup_cuda_memory, cuda_memory_snapshot

        prepared_items = []
        for pos, i in enumerate(self.slice_indices):
            while self.is_paused and not self.is_cancelled:
                time.sleep(0.1)
            if self.is_cancelled:
                return
            progress_total = max(total_slices * 2, 1)
            self.progress.emit(pos + 1, progress_total, f"Preparing slice {i+1} ({pos+1}/{total_slices})…")
            prepared = self.batch_service.prepare_tile_image(self.session, i)
            if prepared is not None:
                prepared_items.append((pos, i, prepared[0], prepared[1]))

        if not prepared_items:
            return

        work_queue = Queue()
        result_queue = Queue()
        for item in prepared_items:
            work_queue.put(item)

        completed = 0
        completed_lock = Lock()

        def run_on_device(device_id: int):
            nonlocal completed
            adapter = CellposeAdapter(model_type="cpsam", gpu=True, device_id=device_id)
            try:
                while not self.is_cancelled:
                    try:
                        pos, i, pil_img, origin = work_queue.get_nowait()
                    except Empty:
                        break
                    if self.is_cancelled:
                        break
                    slice_start = time.monotonic()
                    self.progress.emit(
                        total_slices + completed,
                        progress_total,
                        f"Cellpose GPU {device_id}: Slice {i+1}…",
                    )
                    vram_start = cuda_memory_snapshot(device_id)
                    local_polys = adapter.segment(pil_img, **self.cellpose_params)
                    global_polys = self._offset_polygons(local_polys, origin)
                    prob = adapter.probability_map()
                    instance_map = getattr(adapter, "instance_map", lambda: None)()
                    result_queue.put((pos, i, global_polys, prob, instance_map, time.monotonic() - slice_start, device_id, vram_start))
                    with completed_lock:
                        completed += 1
                        self.progress.emit(
                            total_slices + completed,
                            progress_total,
                            f"Cellpose multi-GPU: {completed}/{total_slices} slices done",
                        )
                    work_queue.task_done()
            finally:
                cleanup_cuda_memory(f"after Cellpose GPU {device_id}")

        with ThreadPoolExecutor(max_workers=len(self.gpu_ids), thread_name_prefix="cellpose-gpu") as pool:
            futures = [pool.submit(run_on_device, device_id) for device_id in self.gpu_ids]
            processed = 0
            while processed < len(prepared_items):
                if self.is_cancelled:
                    return
                try:
                    _, i, polys, prob, instance_map, elapsed, device_id, vram_start = result_queue.get(timeout=0.2)
                except Empty:
                    if all(f.done() for f in futures):
                        break
                    continue
                if polys:
                    self._add_cellpose_layer(i, polys, elapsed, prob, vram_start, instance_map)
                    logger.info(
                        "Macro Cellpose multi-GPU: slice %d completed on CUDA device %d with %d polygons",
                        i + 1, device_id, len(polys),
                    )
                processed += 1
                self.current_slice_pos = processed
            for future in futures:
                future.result()

    @staticmethod
    def _offset_polygons(polygons, origin):
        if not polygons:
            return []
        bx1, by1 = origin
        return [[(px + bx1, py + by1) for px, py in poly] for poly in polygons]

    def _add_cellpose_layer(self, slice_idx: int, polygons, elapsed: float, probability_map, vram_start=None, instance_map=None) -> None:
        layer_idx = self.session.tiles[slice_idx].add_layer(
            "Macro Cellpose", self.cellpose_model, polygons, LAYER_COLORS[0]
        )
        layer = self.session.tiles[slice_idx].segmentation_layers[layer_idx]
        layer["execution_time_s"] = elapsed
        layer["pipeline_run_id"] = self.pipeline_run_id
        self._apply_vram_metadata(layer, vram_start)
        if probability_map is not None:
            layer["probability_map"] = probability_map
        if instance_map is not None:
            layer["instance_map"] = instance_map
            layer["instance_map_source"] = "raw_model_output"

    def _add_nuclick_layer(self, tile, polygons, elapsed: float, vram_start=None) -> None:
        layer_idx = tile.add_layer("Macro NuClick", self.nuclick_model, polygons, LAYER_COLORS[1])
        layer = tile.segmentation_layers[layer_idx]
        layer["execution_time_s"] = elapsed
        layer["pipeline_run_id"] = self.pipeline_run_id
        layer["source_layer_name"] = "Macro Cellpose"
        self._apply_vram_metadata(layer, vram_start)

    @staticmethod
    def _apply_vram_metadata(layer: dict, snapshot) -> None:
        if not snapshot:
            return
        layer["vram_free_gb_start"] = snapshot.get("free_gb")
        layer["vram_device_name"] = snapshot.get("device_name")
        layer["vram_device_id"] = snapshot.get("device_id")

    @staticmethod
    def _current_vram_snapshot():
        try:
            from app.infrastructure.ml_models.gpu_memory import cuda_memory_snapshot
            return cuda_memory_snapshot()
        except Exception:
            return None


class SingleModelWorker(QThread):
    """Runs a single batch model across selected tiles."""
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(float)           # elapsed seconds
    error = pyqtSignal(str)

    def __init__(self, session, batch_service, model_name: str, params: dict,
                 layer_name: str, layer_color: str, slice_indices: Optional[list[int]] = None,
                 gpu_ids: Optional[list[int]] = None):
        super().__init__()
        self.session = session
        self.batch_service = batch_service
        self.model_name = model_name
        self.params = params
        self.layer_name = layer_name
        self.layer_color = layer_color
        self.slice_indices = list(slice_indices) if slice_indices is not None else list(range(len(session.tiles)))
        self.gpu_ids = list(gpu_ids) if gpu_ids else []
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            total_slices = len(self.slice_indices)
            if total_slices == 0:
                self.finished.emit(0.0)
                return

            start_time = time.monotonic()
            can_prefetch = hasattr(self.batch_service, "prepare_tile_image") and hasattr(
                self.batch_service, "segment_prepared_tile"
            )
            if self.model_name == "Cellpose (cpsam)" and self.gpu_ids:
                self._run_cellpose_with_devices(total_slices)
            elif self.model_name == "CellViT-SAM" and self.gpu_ids:
                self._run_cellvit_with_devices(total_slices)
            elif can_prefetch:
                self._run_with_prefetch(total_slices)
            else:
                self._run_serial(total_slices)

            elapsed = time.monotonic() - start_time
            self.finished.emit(elapsed)

        except Exception as e:
            logger.exception("Error in SingleModelWorker (%s): %s", self.model_name, e)
            self.error.emit(str(e))

    def _run_serial(self, total_slices: int) -> None:
        for pos, i in enumerate(self.slice_indices):
            if self.is_cancelled:
                return

            self.progress.emit(
                pos, total_slices,
                f"{self.model_name}: Slice {i+1} ({pos+1}/{total_slices})…"
            )

            slice_start = time.monotonic()
            polys = self.batch_service.segment_tile(
                self.model_name, self.session, i, **self.params
            )
            slice_elapsed = time.monotonic() - slice_start

            if polys:
                layer_idx = self.session.tiles[i].add_layer(
                    self.layer_name, self.model_name, polys, self.layer_color
                )
                self.session.tiles[i].segmentation_layers[layer_idx]["execution_time_s"] = slice_elapsed
                if hasattr(self.batch_service, "vram_snapshot_start"):
                    MacroPipelineWorker._apply_vram_metadata(
                        self.session.tiles[i].segmentation_layers[layer_idx],
                        self.batch_service.vram_snapshot_start(),
                    )
                prob = self.batch_service.probability_map()
                if prob is not None:
                    self.session.tiles[i].segmentation_layers[layer_idx]["probability_map"] = prob
                instance_map = getattr(self.batch_service, "instance_map", lambda: None)()
                if instance_map is not None:
                    self.session.tiles[i].segmentation_layers[layer_idx]["instance_map"] = instance_map
                    self.session.tiles[i].segmentation_layers[layer_idx]["instance_map_source"] = "raw_model_output"
            self.progress.emit(
                pos + 1,
                total_slices,
                f"{self.model_name}: Slice {i+1} done ({pos+1}/{total_slices})",
            )

    def _run_cellpose_with_devices(self, total_slices: int) -> None:
        from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
        from app.infrastructure.ml_models.gpu_memory import cleanup_cuda_memory, cuda_memory_snapshot

        prepared_items = []
        progress_total = max(total_slices * 2, 1)
        for pos, i in enumerate(self.slice_indices):
            if self.is_cancelled:
                return
            self.progress.emit(
                pos + 1, progress_total,
                f"Preparing slice {i+1} ({pos+1}/{total_slices})…"
            )
            prepared = self.batch_service.prepare_tile_image(self.session, i)
            if prepared is not None:
                prepared_items.append((pos, i, prepared[0], prepared[1]))

        work_queue = Queue()
        result_queue = Queue()
        for item in prepared_items:
            work_queue.put(item)

        completed = 0
        completed_lock = Lock()

        def run_on_device(device_id: int):
            nonlocal completed
            adapter = CellposeAdapter(model_type="cpsam", gpu=True, device_id=device_id)
            try:
                while not self.is_cancelled:
                    try:
                        pos, i, pil_img, origin = work_queue.get_nowait()
                    except Empty:
                        break
                    if self.is_cancelled:
                        break
                    slice_start = time.monotonic()
                    vram_start = cuda_memory_snapshot(device_id)
                    local_polys = adapter.segment(pil_img, **self.params)
                    cleanup_hook = getattr(adapter, "cleanup_after_segment", None)
                    if callable(cleanup_hook):
                        cleanup_hook()
                    actual_device_id = getattr(adapter, "current_cuda_device_id", lambda: device_id)()
                    actual_device_label = getattr(adapter, "current_device_label", lambda: f"cuda:{device_id}")()
                    bx1, by1 = origin
                    global_polys = [
                        [(px + bx1, py + by1) for px, py in poly]
                        for poly in local_polys
                    ]
                    result_queue.put(
                        (
                            pos,
                            i,
                            global_polys,
                            adapter.probability_map(),
                            getattr(adapter, "instance_map", lambda: None)(),
                            time.monotonic() - slice_start,
                            actual_device_id if actual_device_id is not None else device_id,
                            vram_start,
                            actual_device_label,
                        )
                    )
                    with completed_lock:
                        completed += 1
                        self.progress.emit(
                            total_slices + completed,
                            progress_total,
                            f"{self.model_name} GPU {device_id}: {completed}/{total_slices} slices done",
                        )
                    work_queue.task_done()
            finally:
                cleanup_cuda_memory(f"after {self.model_name} GPU {device_id}")

        with ThreadPoolExecutor(max_workers=len(self.gpu_ids), thread_name_prefix="single-cellpose-gpu") as pool:
            futures = [pool.submit(run_on_device, device_id) for device_id in self.gpu_ids]
            self._drain_batch_results(result_queue, futures, len(prepared_items))

    def _run_cellvit_with_devices(self, total_slices: int) -> None:
        from app.infrastructure.ml_models.cellvit_adapter import CellViTAdapter
        from app.infrastructure.ml_models.gpu_memory import cleanup_cuda_memory, cuda_memory_snapshot

        prepared_items = []
        progress_total = max(total_slices * 2, 1)
        for pos, i in enumerate(self.slice_indices):
            if self.is_cancelled:
                return
            self.progress.emit(
                pos + 1, progress_total,
                f"Preparing slice {i+1} ({pos+1}/{total_slices})…"
            )
            prepared = self.batch_service.prepare_tile_image(self.session, i)
            if prepared is not None:
                prepared_items.append((pos, i, prepared[0], prepared[1]))

        work_queue = Queue()
        result_queue = Queue()
        for item in prepared_items:
            work_queue.put(item)

        completed = 0
        completed_lock = Lock()

        def run_on_device(device_id: int):
            nonlocal completed
            adapter = CellViTAdapter(gpu=True, device_id=device_id)
            try:
                while not self.is_cancelled:
                    try:
                        pos, i, pil_img, origin = work_queue.get_nowait()
                    except Empty:
                        break
                    if self.is_cancelled:
                        break
                    slice_start = time.monotonic()
                    vram_start = cuda_memory_snapshot(device_id)
                    local_polys = adapter.segment(pil_img, **self.params)
                    cleanup_hook = getattr(adapter, "cleanup_after_segment", None)
                    if callable(cleanup_hook):
                        cleanup_hook()
                    actual_device_id = getattr(adapter, "current_cuda_device_id", lambda: device_id)()
                    actual_device_label = getattr(adapter, "current_device_label", lambda: f"cuda:{device_id}")()
                    bx1, by1 = origin
                    global_polys = [
                        [(px + bx1, py + by1) for px, py in poly]
                        for poly in local_polys
                    ]
                    result_queue.put(
                        (
                            pos,
                            i,
                            global_polys,
                            adapter.probability_map(),
                            getattr(adapter, "instance_map", lambda: None)(),
                            time.monotonic() - slice_start,
                            actual_device_id if actual_device_id is not None else device_id,
                            vram_start,
                            actual_device_label,
                        )
                    )
                    with completed_lock:
                        completed += 1
                        self.progress.emit(
                            total_slices + completed,
                            progress_total,
                            f"{self.model_name} GPU {device_id}: {completed}/{total_slices} slices done",
                        )
                    work_queue.task_done()
            finally:
                cleanup_hook = getattr(adapter, "cleanup_after_segment", None)
                if callable(cleanup_hook):
                    cleanup_hook()
                cleanup_cuda_memory(f"after {self.model_name} GPU {device_id}")

        with ThreadPoolExecutor(max_workers=len(self.gpu_ids), thread_name_prefix="single-cellvit-gpu") as pool:
            futures = [pool.submit(run_on_device, device_id) for device_id in self.gpu_ids]
            self._drain_batch_results(result_queue, futures, len(prepared_items))

    def _drain_batch_results(self, result_queue: Queue, futures, expected_count: int) -> None:
        processed = 0
        while processed < expected_count:
            if self.is_cancelled:
                return
            try:
                item = result_queue.get(timeout=0.2)
            except Empty:
                if all(f.done() for f in futures):
                    break
                continue
            if len(item) == 9:
                _, i, polys, prob, instance_map, elapsed, device_id, vram_start, device_label = item
            else:
                _, i, polys, prob, instance_map, elapsed, device_id, vram_start = item
                device_label = f"cuda:{device_id}"

            if polys:
                layer_idx = self.session.tiles[i].add_layer(
                    self.layer_name, self.model_name, polys, self.layer_color
                )
                layer = self.session.tiles[i].segmentation_layers[layer_idx]
                layer["execution_time_s"] = elapsed
                layer["execution_device"] = device_label
                MacroPipelineWorker._apply_vram_metadata(layer, vram_start)
                if prob is not None:
                    layer["probability_map"] = prob
                if instance_map is not None:
                    layer["instance_map"] = instance_map
                    layer["instance_map_source"] = "raw_model_output"
                logger.info(
                    "%s: slice %d completed on %s with %d polygons",
                    self.model_name, i + 1, device_label, len(polys),
                )
            processed += 1

        for future in futures:
            future.result()

    def _run_with_prefetch(self, total_slices: int) -> None:
        def prepare(idx: int):
            return self.batch_service.prepare_tile_image(self.session, idx)

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="slice-prefetch") as pool:
            next_future = pool.submit(prepare, self.slice_indices[0])

            for pos, i in enumerate(self.slice_indices):
                if self.is_cancelled:
                    return

                self.progress.emit(
                    pos, total_slices,
                    f"{self.model_name}: Slice {i+1} ({pos+1}/{total_slices})…"
                )

                prepared = next_future.result()
                if pos + 1 < total_slices:
                    next_future = pool.submit(prepare, self.slice_indices[pos + 1])

                if prepared is None:
                    self.progress.emit(
                        pos + 1,
                        total_slices,
                        f"{self.model_name}: Slice {i+1} skipped ({pos+1}/{total_slices})",
                    )
                    continue

                slice_start = time.monotonic()
                polys = self.batch_service.segment_prepared_tile(
                    self.model_name, prepared[0], prepared[1], **self.params
                )
                slice_elapsed = time.monotonic() - slice_start

                if polys:
                    layer_idx = self.session.tiles[i].add_layer(
                        self.layer_name, self.model_name, polys, self.layer_color
                    )
                    self.session.tiles[i].segmentation_layers[layer_idx]["execution_time_s"] = slice_elapsed
                    if hasattr(self.batch_service, "vram_snapshot_start"):
                        MacroPipelineWorker._apply_vram_metadata(
                            self.session.tiles[i].segmentation_layers[layer_idx],
                            self.batch_service.vram_snapshot_start(),
                        )
                    prob = self.batch_service.probability_map()
                    if prob is not None:
                        self.session.tiles[i].segmentation_layers[layer_idx]["probability_map"] = prob
                    instance_map = getattr(self.batch_service, "instance_map", lambda: None)()
                    if instance_map is not None:
                        self.session.tiles[i].segmentation_layers[layer_idx]["instance_map"] = instance_map
                        self.session.tiles[i].segmentation_layers[layer_idx]["instance_map_source"] = "raw_model_output"
                self.progress.emit(
                    pos + 1,
                    total_slices,
                    f"{self.model_name}: Slice {i+1} done ({pos+1}/{total_slices})",
                )


class NucleAIWorker(QThread):
    """Runs a click-based model on centroids from a user-selected layer."""
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(float)
    error = pyqtSignal(str)

    def __init__(self, session, interactive_service, source_layer_name: str,
                 click_model_name: str = "NuClick (PyTorch)",
                 slice_indices: Optional[list[int]] = None):
        super().__init__()
        self.session = session
        self.interactive_service = interactive_service
        self.source_layer_name = source_layer_name
        self.click_model_name = click_model_name
        self.slice_indices = list(slice_indices) if slice_indices is not None else list(range(len(session.tiles)))
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            total_slices = len(self.slice_indices)
            if total_slices == 0:
                self.finished.emit(0.0)
                return

            start_time = time.monotonic()
            for pos, i in enumerate(self.slice_indices):
                if self.is_cancelled:
                    return

                self.progress.emit(
                    pos,
                    total_slices,
                    f"NucleAI: Slice {i + 1} ({pos + 1}/{total_slices})...",
                )

                tile = self.session.tiles[i]
                source_layer = self._find_source_layer(tile)
                if source_layer is None:
                    logger.info(
                        "NucleAI: source layer '%s' not found on slice %d",
                        self.source_layer_name,
                        i + 1,
                    )
                    self.progress.emit(
                        pos + 1,
                        total_slices,
                        f"NucleAI: Slice {i + 1} skipped ({pos + 1}/{total_slices})",
                    )
                    continue

                centroids = [
                    get_polygon_centroid(poly)
                    for poly in source_layer.get("polygons", [])
                    if poly
                ]
                if not centroids:
                    self.progress.emit(
                        pos + 1,
                        total_slices,
                        f"NucleAI: Slice {i + 1} skipped ({pos + 1}/{total_slices})",
                    )
                    continue

                slice_start = time.monotonic()
                vram_start = MacroPipelineWorker._current_vram_snapshot()
                click_polys = self.interactive_service.segment_at_points(
                    self.click_model_name, self.session, i, centroids
                )
                if click_polys:
                    layer_idx = tile.add_layer(
                        f"NucleAI {self._short_click_name()} · {self.source_layer_name}",
                        self.click_model_name,
                        click_polys,
                        LAYER_COLORS[1],
                    )
                    layer = tile.segmentation_layers[layer_idx]
                    layer["execution_time_s"] = time.monotonic() - slice_start
                    layer["source_layer_name"] = self.source_layer_name
                    MacroPipelineWorker._apply_vram_metadata(layer, vram_start)
                self.progress.emit(
                    pos + 1,
                    total_slices,
                    f"NucleAI: Slice {i + 1} done ({pos + 1}/{total_slices})",
                )

            self.finished.emit(time.monotonic() - start_time)

        except Exception as exc:
            logger.exception("Error in NucleAIWorker: %s", exc)
            self.error.emit(str(exc))

    def _find_source_layer(self, tile):
        for layer in tile.segmentation_layers:
            name = layer.get("name") or layer.get("model") or "Segmentation"
            if name == self.source_layer_name:
                return layer
        return None

    def _short_click_name(self) -> str:
        if self.click_model_name == "NuClick (PyTorch)":
            return "NuClick"
        return self.click_model_name


class DINOSimCellposeReferenceWorker(QThread):
    """Build DINOSim reference points from Cellpose centroids on one tile."""
    reference_ready = pyqtSignal(int, int, float)  # point_count, cellpose_polygon_count, elapsed seconds
    error = pyqtSignal(str)
    MAX_REFERENCE_POINTS = 48

    def __init__(self, batch_service, dinosim_model: str, cellpose_model: str,
                 tile_image, params: dict):
        super().__init__()
        self.batch_service = batch_service
        self.dinosim_model = dinosim_model
        self.cellpose_model = cellpose_model
        self.tile_image = tile_image
        self.params = params

    def run(self):
        try:
            start_time = time.monotonic()
            cellpose_polys = self.batch_service.segment(
                self.cellpose_model,
                self.tile_image,
                **self.params,
            )
            selected_polys = self._select_reference_polygons(cellpose_polys)
            coords = [get_polygon_centroid(poly) for poly in selected_polys]
            if not coords:
                self.error.emit("Cellpose did not detect nuclei to use as DINOSim reference points.")
                return

            adapter = self.batch_service.get_model(self.dinosim_model)
            if adapter is None:
                self.error.emit("DINOSim adapter not registered.")
                return

            adapter.set_reference_points(coords, reference_image=self.tile_image)
            elapsed = time.monotonic() - start_time
            self.reference_ready.emit(len(coords), len(cellpose_polys), elapsed)
        except Exception as exc:
            logger.exception("DINOSim Cellpose reference failed: %s", exc)
            self.error.emit(str(exc))

    def _select_reference_polygons(self, polygons):
        """Keep representative Cellpose nuclei and drop tiny/huge artifacts."""
        from app.domain.geometry import polygon_area

        candidates = []
        for poly in polygons:
            if not poly or len(poly) < 3:
                continue
            area = float(polygon_area(poly))
            if area <= 0:
                continue
            candidates.append((area, poly))

        if not candidates:
            return []

        areas = sorted(area for area, _ in candidates)
        lo = areas[max(0, int(len(areas) * 0.10) - 1)]
        hi = areas[min(len(areas) - 1, int(len(areas) * 0.90))]
        filtered = [(area, poly) for area, poly in candidates if lo <= area <= hi]
        if not filtered:
            filtered = candidates

        median_area = areas[len(areas) // 2]
        filtered.sort(key=lambda item: abs(item[0] - median_area))
        return [poly for _, poly in filtered[: self.MAX_REFERENCE_POINTS]]


# ── Model card widget ──────────────────────────────────────────────────────────

class _ModelCard(QWidget):
    """
    Selectable radio card for a segmentation model.

    Visual state:
      - Unselected: bg_panel background, default border
      - Selected: bg_elevated background, 2px accent_action left border
    """

    def __init__(self, model_name: str, description: str, parent=None):
        super().__init__(parent)
        self.model_name = model_name
        self._selected = False
        self.setObjectName("ModelCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(SIZE["lg"])  # 44px

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE[3], 0, SPACE[3], 0)
        layout.setSpacing(SPACE[2])

        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)

        self._name_lbl = QLabel(model_name)
        themed(self._name_lbl, _style_card_title)

        self._desc_lbl = QLabel(description)
        themed(self._desc_lbl, _style_card_desc)

        col.addStretch()
        col.addWidget(self._name_lbl)
        col.addWidget(self._desc_lbl)
        col.addStretch()
        layout.addLayout(col, stretch=1)

        self._refresh_style()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._refresh_style()

    def is_selected(self) -> bool:
        return self._selected

    def mousePressEvent(self, event) -> None:
        self.set_selected(True)
        super().mousePressEvent(event)

    def _refresh_style(self) -> None:
        themed(self, self._card_selected_style if self._selected else self._card_idle_style)

    @staticmethod
    def _card_selected_style() -> str:
        return (
            f"QWidget#ModelCard {{"
            f" background: {COLORS['bg_elevated']};"
            f" border-radius: {RADIUS['md']}px;"
            f" border: 1.5px solid {COLORS['accent_action']};"
            f"}}"
        )

    @staticmethod
    def _card_idle_style() -> str:
        return (
            f"QWidget#ModelCard {{"
            f" background: {COLORS['bg_panel']};"
            f" border-radius: {RADIUS['md']}px;"
            f" border: 1px solid {COLORS['border_default']};"
            f"}}"
        )


# ── Panel ─────────────────────────────────────────────────────────────────────

class MacroPipelinePanel(QDockWidget):
    """
    Unified segmentation dock.

    Model cards let the user pick which model to run.
    NucleAI runs a click-based model from centroids of a user-selected segmentation layer.
    When DINOSim is selected, a reference-point section appears — the user must
    pick reference nuclei before running.
    All other models run as single independent passes.
    """

    _MODEL_DESCRIPTIONS = {
        "Cellpose (cpsam)":  "cpsam · CUDA",
        "NucleAI":           "Click model from selected layer",
        "CellViT-SAM":       "ViT-SAM",
        "PathoSAM (ViT-L)":  "SAM · histopathology",
        "DINOSim (small)":   "DINOv2 · zero-shot similarity",
    }

    _DINOSIM_NAME = "DINOSim (small)"
    _NUCLEAI_NAME = "NucleAI"

    def __init__(self, parent=None):
        super().__init__("Segmentation", parent)
        self.main_window = parent
        self.setFeatures(
            QDockWidget.DockWidgetFeature.NoDockWidgetFeatures |
            QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.worker: Optional[QThread] = None
        self._reference_worker: Optional[QThread] = None
        self._running = False

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(SPACE[3], SPACE[3], SPACE[3], SPACE[3])
        layout.setSpacing(SPACE[2])

        # ── Model cards ───────────────────────────────────────────────────────
        self._model_cards: list[_ModelCard] = []
        for model_name, color in _KNOWN_MODELS:
            desc = self._MODEL_DESCRIPTIONS.get(model_name, "")
            card = _ModelCard(model_name, desc)
            card.mousePressEvent = self._make_card_click(card)
            self._model_cards.append(card)
            layout.addWidget(card)

        layout.addSpacing(SPACE[1])

        # ── GPU selector — shown for models with explicit CUDA device support ──
        self._gpu_row = QWidget()
        gpu_layout = QHBoxLayout(self._gpu_row)
        gpu_layout.setContentsMargins(0, 0, 0, 0)
        gpu_layout.setSpacing(SPACE[2])
        self._lbl_gpu = QLabel("GPU")
        themed(self._lbl_gpu, _style_field_label)
        gpu_layout.addWidget(self._lbl_gpu)
        self._cmb_gpu = QComboBox()
        self._cmb_gpu.setToolTip("Choose which visible CUDA device the selected model should use.")
        self._cmb_gpu.setMinimumHeight(SIZE["md"])
        gpu_layout.addWidget(self._cmb_gpu, stretch=1)
        self._gpu_row.setVisible(False)
        layout.addWidget(self._gpu_row)
        self._refresh_gpu_choices()

        # ── NucleAI source layer — only shown when NucleAI is selected ────────
        self._nucleai_row = QWidget()
        themed(self._nucleai_row, _style_inline_row)
        nucleai_layout = QVBoxLayout(self._nucleai_row)
        nucleai_layout.setContentsMargins(SPACE[3], SPACE[2], SPACE[3], SPACE[2])
        nucleai_layout.setSpacing(SPACE[2])

        self._lbl_nucleai_source = QLabel("Source layer")
        themed(self._lbl_nucleai_source, _style_field_label_strong)
        nucleai_layout.addWidget(self._lbl_nucleai_source)

        self._cmb_nucleai_source = QComboBox()
        self._cmb_nucleai_source.setToolTip(
            "Choose which existing membrane/mask layer provides centroids for NucleAI."
        )
        self._cmb_nucleai_source.setMinimumHeight(SIZE["md"])
        self._cmb_nucleai_source.currentIndexChanged.connect(self.refresh_selection_state)
        nucleai_layout.addWidget(self._cmb_nucleai_source)

        self._lbl_nucleai_click_model = QLabel("Click model")
        themed(self._lbl_nucleai_click_model, _style_field_label_strong)
        nucleai_layout.addWidget(self._lbl_nucleai_click_model)

        self._cmb_nucleai_click_model = QComboBox()
        self._cmb_nucleai_click_model.setToolTip(
            "Choose which click-based model will refine each source-layer centroid."
        )
        self._cmb_nucleai_click_model.setMinimumHeight(SIZE["md"])
        self._cmb_nucleai_click_model.currentIndexChanged.connect(self._on_nucleai_click_model_changed)
        nucleai_layout.addWidget(self._cmb_nucleai_click_model)
        self._refresh_nucleai_click_models()

        self._nucleai_row.setVisible(False)
        layout.addWidget(self._nucleai_row)

        # ── DINOSim reference row — only shown when DINOSim is selected ───────
        self._dinosim_row = QWidget()
        themed(self._dinosim_row, _style_inline_row)
        dinosim_layout = QHBoxLayout(self._dinosim_row)
        dinosim_layout.setContentsMargins(SPACE[2], SPACE[2], SPACE[2], SPACE[2])
        dinosim_layout.setSpacing(SPACE[2])

        self._lbl_dinosim_ref = QLabel("○  No reference set")
        themed(self._lbl_dinosim_ref, _style_ref_unset)
        dinosim_layout.addWidget(self._lbl_dinosim_ref, stretch=1)

        self._btn_pick_ref = SecondaryButton("Pick Points")
        self._btn_pick_ref.setToolTip(
            "Click on representative nuclei in the current tile to define the reference."
        )
        self._btn_pick_ref.clicked.connect(self._pick_dinosim_reference)
        dinosim_layout.addWidget(self._btn_pick_ref)

        self._btn_cellpose_ref = SecondaryButton("Cellpose Points")
        self._btn_cellpose_ref.setToolTip(
            "Run Cellpose on the current tile and use one centroid per detected nucleus as DINOSim reference points."
        )
        self._btn_cellpose_ref.clicked.connect(self._pick_dinosim_reference_from_cellpose)
        dinosim_layout.addWidget(self._btn_cellpose_ref)

        self._dinosim_row.setVisible(False)
        layout.addWidget(self._dinosim_row)

        layout.addSpacing(SPACE[1])

        # ── Progress ──────────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Select slices and a model to run.")
        self.lbl_status.setWordWrap(True)
        themed(self.lbl_status, _style_field_label)
        layout.addWidget(self.lbl_status)

        layout.addSpacing(SPACE[1])

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(SPACE[2])

        self.btn_run = ActionButton("Run selected", size="lg")
        self.btn_run.setEnabled(False)
        self.btn_run.setToolTip("Run selected model on checked slices")
        self.btn_run.clicked.connect(self._on_run_clicked)

        self.btn_cancel = SecondaryButton("Cancel")
        self.btn_cancel.setToolTip("Stop after current slice finishes")
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_cancel.setEnabled(False)

        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        layout.addStretch()
        self.setWidget(container)

    # ── Card interaction ──────────────────────────────────────────────────────

    def _make_card_click(self, clicked_card: "_ModelCard"):
        def handler(event):
            for card in self._model_cards:
                card.set_selected(card is clicked_card)

            is_cellpose = clicked_card.model_name == "Cellpose (cpsam)"
            supports_gpu_choice = clicked_card.model_name in {"Cellpose (cpsam)", "CellViT-SAM"}
            is_dinosim  = clicked_card.model_name == self._DINOSIM_NAME
            is_nucleai = clicked_card.model_name == self._NUCLEAI_NAME

            self._gpu_row.setVisible(supports_gpu_choice)
            self._nucleai_row.setVisible(is_nucleai)
            self._dinosim_row.setVisible(is_dinosim)
            self._set_properties_params_visible(
                cellpose_visible=is_cellpose,
                idisf_visible=is_nucleai and self._selected_nucleai_click_model() == "iDISF",
            )

            if is_dinosim:
                self._refresh_dinosim_ref_status()
            if is_nucleai:
                self._refresh_nucleai_sources()
                self._refresh_nucleai_click_models()
                if self._selected_nucleai_click_model() == "iDISF":
                    panel = getattr(self.main_window, "properties_dock", None)
                    if panel is not None:
                        panel.setVisible(True)
            self.refresh_selection_state()

            _ModelCard.mousePressEvent(clicked_card, event)
        return handler

    def _selected_model(self):
        """Return (model_name, color) of the selected card, or (None, None)."""
        for card, (name, color) in zip(self._model_cards, _KNOWN_MODELS):
            if card.is_selected():
                return name, color
        return None, None

    def _selected_slice_indices(self) -> list[int]:
        slice_previews = getattr(self.main_window, "slice_previews", None)
        if slice_previews is None or not hasattr(slice_previews, "selected_batch_indices"):
            return []
        return slice_previews.selected_batch_indices()

    def _refresh_nucleai_sources(self) -> None:
        current = self._cmb_nucleai_source.currentData()
        self._cmb_nucleai_source.blockSignals(True)
        self._cmb_nucleai_source.clear()

        sources = self._available_nucleai_sources()
        if sources:
            for source in sources:
                self._cmb_nucleai_source.addItem(source, source)
        else:
            self._cmb_nucleai_source.addItem("No membrane/layer available", None)

        if current in sources:
            self._cmb_nucleai_source.setCurrentIndex(sources.index(current))

        self._cmb_nucleai_source.blockSignals(False)

    def _refresh_nucleai_click_models(self) -> None:
        current = self._cmb_nucleai_click_model.currentData()
        self._cmb_nucleai_click_model.blockSignals(True)
        self._cmb_nucleai_click_model.clear()

        service = getattr(self.main_window, "segmentation_service", None)
        available = service.get_available_models() if service is not None else []
        preferred = ["NuClick (PyTorch)", "iDISF"]
        models = [name for name in preferred if name in available]
        models.extend(name for name in available if name not in models)

        for model_name in models:
            label = "NuClick" if model_name == "NuClick (PyTorch)" else model_name
            self._cmb_nucleai_click_model.addItem(label, model_name)

        if current is not None:
            idx = self._cmb_nucleai_click_model.findData(current)
            if idx >= 0:
                self._cmb_nucleai_click_model.setCurrentIndex(idx)

        self._cmb_nucleai_click_model.blockSignals(False)

    def _selected_nucleai_click_model(self) -> Optional[str]:
        return self._cmb_nucleai_click_model.currentData()

    def _on_nucleai_click_model_changed(self, _index: int) -> None:
        model_name, _ = self._selected_model()
        is_nucleai = model_name == self._NUCLEAI_NAME
        show_idisf = is_nucleai and self._selected_nucleai_click_model() == "iDISF"
        self._set_properties_params_visible(
            cellpose_visible=False,
            idisf_visible=show_idisf,
        )
        if show_idisf:
            panel = getattr(self.main_window, "properties_dock", None)
            if panel is not None:
                panel.setVisible(True)
        self.refresh_selection_state()

    def _available_nucleai_sources(self) -> list[str]:
        s = getattr(self.main_window, "current_session", None)
        if s is None:
            return []

        indices = self._selected_slice_indices()
        if not indices:
            indices = list(range(len(s.tiles)))

        names: list[str] = []
        seen: set[str] = set()
        for idx in indices:
            if idx < 0 or idx >= len(s.tiles):
                continue
            for layer in s.tiles[idx].segmentation_layers:
                if not layer.get("polygons"):
                    continue
                name = layer.get("name") or layer.get("model") or "Segmentation"
                model = layer.get("model_name") or layer.get("model")
                if name.startswith("NucleAI") or model == "NuClick (PyTorch)":
                    continue
                if name not in seen:
                    seen.add(name)
                    names.append(name)
        return names

    def _selected_nucleai_source(self) -> Optional[str]:
        return self._cmb_nucleai_source.currentData()

    def _refresh_gpu_choices(self) -> None:
        self._cmb_gpu.clear()
        self._cmb_gpu.addItem("Auto", None)
        try:
            from app.infrastructure.config.gpu_selector import list_compatible_cuda_devices
            devices = list_compatible_cuda_devices()
        except Exception as exc:
            logger.debug("Could not list CUDA devices for macro panel: %s", exc)
            devices = []

        for device in devices:
            device_id = int(device["id"])
            total_gb = float(device.get("total_memory", 0)) / (1024 ** 3)
            label = f"GPU {device_id} · {device['name']}"
            if total_gb > 0:
                label = f"{label} · {total_gb:.1f} GB"
            self._cmb_gpu.addItem(label, [device_id])

        if len(devices) > 1:
            ids = [int(device["id"]) for device in devices]
            self._cmb_gpu.addItem("All visible GPUs", ids)
            self._cmb_gpu.setCurrentIndex(self._cmb_gpu.count() - 1)

    def _selected_gpu_ids(self) -> Optional[list[int]]:
        data = self._cmb_gpu.currentData()
        if not data:
            return None
        return list(data)

    def _set_properties_params_visible(self, cellpose_visible: bool = False, idisf_visible: bool = False) -> None:
        panel = getattr(self.main_window, "properties_dock", None)
        if panel is None:
            return
        if hasattr(panel, "show_cellpose_params"):
            panel.show_cellpose_params(cellpose_visible)
        if hasattr(panel, "show_idisf_params"):
            panel.show_idisf_params(idisf_visible)

    def refresh_selection_state(self) -> None:
        if self._running:
            return

        model_name, _ = self._selected_model()
        selected_count = len(self._selected_slice_indices())
        has_model = model_name is not None
        can_run = has_model and selected_count > 0

        if model_name == self._DINOSIM_NAME:
            can_run = can_run and self._dinosim_has_reference()
        if model_name == self._NUCLEAI_NAME:
            self._refresh_nucleai_sources()
            self._refresh_nucleai_click_models()
            can_run = (
                can_run
                and self._selected_nucleai_source() is not None
                and self._selected_nucleai_click_model() is not None
            )

        self.btn_run.setEnabled(can_run)

        if selected_count == 0:
            self.lbl_status.setText("Check one or more slices to run batch segmentation.")
        elif not has_model:
            self.lbl_status.setText(f"{selected_count} slice{'s' if selected_count != 1 else ''} selected. Choose a model.")
        elif model_name == self._DINOSIM_NAME and not self._dinosim_has_reference():
            self.lbl_status.setText("Pick DINOSim reference points before running selected slices.")
        elif model_name == self._NUCLEAI_NAME and self._selected_nucleai_source() is None:
            self.lbl_status.setText("Choose a source membrane/layer before running NucleAI.")
        elif model_name == self._NUCLEAI_NAME and self._selected_nucleai_click_model() is None:
            self.lbl_status.setText("Choose NuClick or iDISF before running NucleAI.")
        elif model_name == self._NUCLEAI_NAME:
            click_model = self._selected_nucleai_click_model()
            click_label = "NuClick" if click_model == "NuClick (PyTorch)" else click_model
            self.lbl_status.setText(
                f"Ready to run <b>NucleAI {click_label}</b> from <b>{self._selected_nucleai_source()}</b> "
                f"on {selected_count} selected slice{'s' if selected_count != 1 else ''}."
            )
        else:
            self.lbl_status.setText(
                f"Ready to run <b>{model_name}</b> on {selected_count} selected slice"
                f"{'s' if selected_count != 1 else ''}."
            )

    # ── DINOSim reference management ─────────────────────────────────────────

    def _dinosim_has_reference(self) -> bool:
        """True if the DINOSimAdapter already has reference vectors loaded."""
        svc = getattr(self.main_window, "batch_segmentation_service", None)
        if svc is None:
            return False
        adapter = svc.get_model(self._DINOSIM_NAME)
        return adapter is not None and getattr(adapter, "has_reference", False)

    def _refresh_dinosim_ref_status(self) -> None:
        if self._dinosim_has_reference():
            self._lbl_dinosim_ref.setText("●  Reference ready")
            themed(self._lbl_dinosim_ref, _style_ref_ready)
            self._btn_pick_ref.setText("Change Points")
            self._btn_cellpose_ref.setText("Cellpose Points")
        else:
            self._lbl_dinosim_ref.setText("○  No reference set")
            themed(self._lbl_dinosim_ref, _style_ref_unset)
            self._btn_pick_ref.setText("Pick Points")
            self._btn_cellpose_ref.setText("Cellpose Points")

    def _reference_tile_index(self) -> int:
        mw = self.main_window
        s = getattr(mw, "current_session", None)
        if s is None or not s.tiles:
            return 0

        idx = getattr(mw.canvas_renderer, "isolated_slice_idx", None)
        if idx is not None and 0 <= idx < len(s.tiles):
            return idx

        selected = self._selected_slice_indices()
        if selected:
            return selected[0]

        return 0

    def _load_reference_tile_image(self):
        mw = self.main_window
        s = getattr(mw, "current_session", None)
        if s is None or not s.tiles:
            raise RuntimeError("Open an image with slices first.")

        idx = self._reference_tile_index()
        tile = s.tiles[idx]
        bx1, by1, bx2, by2 = tile.bounding_box
        tile_pil = s.pyramid.get_region_fullres(bx1, by1, bx2 - bx1, by2 - by1)
        tile_pil = tile.get_ml_ready_image(tile_pil)
        return idx, tile_pil

    def _pick_dinosim_reference(self) -> None:
        """Open the reference-point dialog, then apply coords to the DINOSimAdapter."""
        mw = self.main_window
        s = getattr(mw, "current_session", None)
        if s is None or not s.tiles:
            self.lbl_status.setText("Open an image with slices first.")
            return

        try:
            idx, tile_pil = self._load_reference_tile_image()
        except Exception as exc:
            self.lbl_status.setText(f"Could not load tile image: {exc}")
            logger.error("DINOSim pick: failed to get tile image: %s", exc)
            return

        dlg = DINOSimReferenceDialog(tile_pil, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        coords = dlg.reference_coords
        if not coords:
            return

        svc = getattr(mw, "batch_segmentation_service", None)
        if svc is None:
            return
        adapter = svc.get_model(self._DINOSIM_NAME)
        if adapter is None:
            self.lbl_status.setText("DINOSim adapter not registered.")
            return

        self.lbl_status.setText("Computing DINOSim reference embeddings…")
        try:
            adapter.set_reference_points(coords, reference_image=tile_pil)
        except Exception as exc:
            self.lbl_status.setText(f"Reference failed: {exc}")
            logger.error("DINOSim set_reference_points error: %s", exc)
            return

        self._refresh_dinosim_ref_status()
        self.refresh_selection_state()
        n = len(coords)
        self.lbl_status.setText(
            f"DINOSim reference set from {n} point{'s' if n != 1 else ''} on tile {idx + 1}."
        )

    def _pick_dinosim_reference_from_cellpose(self) -> None:
        """Run Cellpose on the reference tile and use centroids as DINOSim prompts."""
        if self._reference_worker is not None:
            return

        mw = self.main_window
        svc = getattr(mw, "batch_segmentation_service", None)
        if svc is None:
            self.lbl_status.setText("Batch segmentation service unavailable.")
            return

        if svc.get_model(self._DINOSIM_NAME) is None:
            self.lbl_status.setText("DINOSim adapter not registered.")
            return
        if svc.get_model("Cellpose (cpsam)") is None:
            self.lbl_status.setText("Cellpose adapter not registered.")
            return

        try:
            idx, tile_pil = self._load_reference_tile_image()
        except Exception as exc:
            self.lbl_status.setText(f"Could not load tile image: {exc}")
            logger.error("DINOSim Cellpose reference: failed to get tile image: %s", exc)
            return

        self._reference_worker = DINOSimCellposeReferenceWorker(
            svc,
            self._DINOSIM_NAME,
            "Cellpose (cpsam)",
            tile_pil,
            self._build_params(),
        )
        self._reference_worker.reference_ready.connect(
            lambda point_count, poly_count, elapsed, tile_idx=idx:
                self._on_dinosim_cellpose_reference_ready(point_count, poly_count, elapsed, tile_idx)
        )
        self._reference_worker.error.connect(self._on_dinosim_cellpose_reference_error)
        self._reference_worker.finished.connect(self._on_dinosim_reference_thread_finished)

        self._btn_pick_ref.setEnabled(False)
        self._btn_cellpose_ref.setEnabled(False)
        self.lbl_status.setText(
            f"Running Cellpose to create DINOSim reference points on tile {idx + 1}…"
        )
        self._reference_worker.start()

    def _on_dinosim_cellpose_reference_ready(
        self,
        point_count: int,
        poly_count: int,
        elapsed: float,
        tile_idx: int,
    ) -> None:
        self._btn_pick_ref.setEnabled(True)
        self._btn_cellpose_ref.setEnabled(True)
        self._refresh_dinosim_ref_status()
        self.refresh_selection_state()
        self.lbl_status.setText(
            f"DINOSim reference set from {point_count} Cellpose centroid"
            f"{'s' if point_count != 1 else ''} on tile {tile_idx + 1} ({elapsed:.2f}s)."
        )

    def _on_dinosim_cellpose_reference_error(self, err_msg: str) -> None:
        self._btn_pick_ref.setEnabled(True)
        self._btn_cellpose_ref.setEnabled(True)
        self._refresh_dinosim_ref_status()
        self.refresh_selection_state()
        self.lbl_status.setText(f"Cellpose reference failed: {err_msg}")

    def _on_dinosim_reference_thread_finished(self) -> None:
        self._reference_worker = None

    # ── Run / Pause / Resume ──────────────────────────────────────────────────

    def _on_run_clicked(self) -> None:
        # Pause/Resume toggle for an active pipeline
        if self._running and isinstance(self.worker, MacroPipelineWorker):
            if self.worker.is_paused:
                self.worker.resume()
                self.btn_run.setText("Pause")
            else:
                self.worker.pause()
                self.btn_run.setText("Resume")
            return

        model_name, color = self._selected_model()
        if not model_name or self.worker is not None:
            return

        s = self.main_window.current_session
        if not s or not s.tiles:
            self.lbl_status.setText("No slices found in the project.")
            return

        selected_indices = self._selected_slice_indices()
        if not selected_indices:
            self.lbl_status.setText("Check one or more slices before running.")
            return

        # DINOSim guard — reference must be set before running
        if model_name == self._DINOSIM_NAME and not self._dinosim_has_reference():
            self.lbl_status.setText("Pick reference points first (use the button above).")
            return

        if model_name == self._NUCLEAI_NAME:
            self._run_nucleai(s, selected_indices)
        else:
            self._run_single_model(model_name, color, s, selected_indices)

    def _run_nucleai(self, s, slice_indices: list[int]) -> None:
        source_layer = self._selected_nucleai_source()
        if not source_layer:
            self.lbl_status.setText("Choose a source membrane/layer before running NucleAI.")
            return
        click_model = self._selected_nucleai_click_model()
        if not click_model:
            self.lbl_status.setText("Choose NuClick or iDISF before running NucleAI.")
            return
        if click_model == "iDISF" and hasattr(self.main_window, "_sync_idisf_params"):
            self.main_window._sync_idisf_params()

        self.worker = NucleAIWorker(
            s,
            self.main_window.segmentation_service,
            source_layer,
            click_model_name=click_model,
            slice_indices=slice_indices,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_single_finished)
        self.worker.error.connect(self._on_error)

        self.progress_bar.setValue(0)
        click_label = "NuClick" if click_model == "NuClick (PyTorch)" else click_model
        self.lbl_status.setText(
            f"Running <b>NucleAI {click_label}</b> from <b>{source_layer}</b> on {len(slice_indices)} selected slices..."
        )
        self._set_running(True, pipeline=False)
        self.worker.start()

    def _run_single_model(self, model_name: str, color: str, s, slice_indices: list[int]) -> None:
        params = self._build_params()
        self.worker = SingleModelWorker(
            s, self.main_window.batch_segmentation_service,
            model_name, params, _layer_name(model_name), color,
            slice_indices=slice_indices,
            gpu_ids=self._selected_gpu_ids() if model_name in {"Cellpose (cpsam)", "CellViT-SAM"} else None,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_single_finished)
        self.worker.error.connect(self._on_error)

        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"Running <b>{model_name}</b> on {len(slice_indices)} selected slices…")
        self._set_running(True, pipeline=False)
        self.worker.start()

    def _start_pipeline(self, s, slice_indices: list[int]) -> None:
        params = self._build_params()
        self.worker = MacroPipelineWorker(
            s,
            self.main_window.batch_segmentation_service,
            self.main_window.segmentation_service,
            "Cellpose (cpsam)",
            "NuClick (PyTorch)",
            params,
            run_nuclick=True,
            slice_indices=slice_indices,
            gpu_ids=self._selected_gpu_ids(),
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_pipeline_finished)
        self.worker.error.connect(self._on_error)

        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"Starting pipeline on {len(slice_indices)} selected slices…")
        self._set_running(True, pipeline=True)
        self.worker.start()

    # ── State management ──────────────────────────────────────────────────────

    def _set_running(self, running: bool, pipeline: bool = False) -> None:
        self._running = running
        if running:
            self.btn_run.setText("Pause" if pipeline else "Running…")
            self.btn_run.setEnabled(pipeline)  # only pipeline supports pause/resume
            self.btn_cancel.setEnabled(True)
            for card in self._model_cards:
                card.setEnabled(False)
            self._btn_pick_ref.setEnabled(False)
            self._btn_cellpose_ref.setEnabled(False)
            self._cmb_gpu.setEnabled(False)
            self._cmb_nucleai_source.setEnabled(False)
            self._cmb_nucleai_click_model.setEnabled(False)
        else:
            self.btn_run.setText("Run selected")
            self.btn_cancel.setEnabled(False)
            for card in self._model_cards:
                card.setEnabled(True)
            self._btn_pick_ref.setEnabled(True)
            self._btn_cellpose_ref.setEnabled(True)
            self._cmb_gpu.setEnabled(True)
            self._cmb_nucleai_source.setEnabled(True)
            self._cmb_nucleai_click_model.setEnabled(True)
            self.refresh_selection_state()

    def _cancel(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.worker.wait()
            self.worker = None
        self._set_running(False)
        self.lbl_status.setText("Cancelled.")
        self.progress_bar.setValue(0)

    # ── Worker callbacks ──────────────────────────────────────────────────────

    def _release_worker(self) -> None:
        """Tear down the worker thread safely after it signals completion.

        The workers emit their custom ``finished``/``error`` signal from *inside*
        ``run()``, so the QThread is still running when these slots fire. Simply
        dropping the only reference (``self.worker = None``) lets Python GC the
        QThread while it is still running, which makes Qt abort the process with
        "QThread: Destroyed while thread is still running". Wait for ``run()`` to
        return first (mirrors ``_cancel``), then release.
        """
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.wait()
            worker.deleteLater()

    def _on_progress(self, current: int, total: int, text: str) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.lbl_status.setText(text)

    def _on_single_finished(self, elapsed: float) -> None:
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.lbl_status.setText(f"Done in {elapsed:.2f}s")
        self._release_worker()
        self._set_running(False)
        self._refresh_views()

    def _on_pipeline_finished(self) -> None:
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.lbl_status.setText("Pipeline completed.")
        self._release_worker()
        self._set_running(False)
        self._refresh_views()

    def _on_error(self, err_msg: str) -> None:
        self.lbl_status.setText(f"Error: {err_msg}")
        self._release_worker()
        self._set_running(False)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_params(self) -> dict:
        mw = self.main_window
        diameter = mw.spin_diameter.value()
        return {
            "diameter": None if diameter == 0.0 else diameter,
            "flow_threshold": mw.spin_flow.value(),
            "cellprob_threshold": mw.spin_cellprob.value(),
        }

    def _refresh_views(self) -> None:
        if hasattr(self.main_window, "layer_dropdown"):
            self.main_window.layer_dropdown.refresh()
        panel = getattr(self.main_window, "properties_dock", None)
        if panel is not None and hasattr(panel, "refresh_segmentation_summary"):
            panel.refresh_segmentation_summary()
        if hasattr(self.main_window, "canvas_renderer"):
            self.main_window.canvas_renderer.redraw()
        if hasattr(self.main_window, "tile_renderer"):
            self.main_window.tile_renderer.viewport().update()
