"""
Pixel-level editor dialog for extracted slices.

Opens as a floating :class:`QDialog` from the slice sidebar.  Renders the
full-resolution crop of the selected slice inside a zoomable
:class:`QGraphicsView`, then overlays a semi-transparent pixel grid and a
red highlight on every pixel that has been marked for removal.

Usage::

    dialog = SlicePixelEditorDialog(
        main_window=mw,
        slice_idx=0,
        pixel_mask_service=PixelMaskService(),
        undo_manager=mw.undo_manager,
    )
    dialog.exec()
"""

import logging
import math
from typing import Optional, Set, Tuple

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.application.services import PixelMaskService
from app.domain.history import UndoManager
from app.domain.session import ImageSession

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Pixel-level canvas (inner QGraphicsView)
# ─────────────────────────────────────────────────────────────────────────────

class _PixelCanvas(QGraphicsView):
    """Internal zoomable canvas that renders one full-resolution slice crop."""

    # Grid overlay appears only when each real pixel occupies >= this many screen pixels
    _GRID_THRESHOLD = 4.0

    def __init__(
        self,
        pixmap: QPixmap,
        slice_w: int,
        slice_h: int,
        bx1: int,
        by1: int,
        slice_idx: int,
        session: ImageSession,
        pixel_mask_service: PixelMaskService,
        undo_manager: Optional[UndoManager],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._slice_w = slice_w
        self._slice_h = slice_h
        self._bx1 = bx1
        self._by1 = by1
        self._slice_idx = slice_idx
        self._session = session
        self._pms = pixel_mask_service
        self._undo = undo_manager

        # Start zoom so each real pixel ≈ 8 screen pixels, clamped to fit view
        self._zoom: float = 8.0

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._scene.setSceneRect(0, 0, slice_w, slice_h)
        self._pixmap_item = QGraphicsPixmapItem(pixmap)
        self._pixmap_item.setZValue(0)
        self._scene.addItem(self._pixmap_item)

        self._apply_zoom()

    # ── Zoom helpers ─────────────────────────────────────────────────────────

    def _apply_zoom(self) -> None:
        self.resetTransform()
        self.scale(self._zoom, self._zoom)

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(1.0, min(zoom, 64.0))
        self._apply_zoom()
        self.viewport().update()

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.5)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.5)

    def reset_zoom(self) -> None:
        self.set_zoom(8.0)
        self.centerOn(self._slice_w / 2, self._slice_h / 2)

    # ── Overlay ───────────────────────────────────────────────────────────────

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        """Draw the pixel-grid overlay and removed-pixel highlights."""
        zoom = self._zoom

        # ── Red overlay for every removed pixel ──────────────────────────────
        mask: Set[Tuple[int, int]] = self._pms.get_mask(self._session, self._slice_idx)
        if mask:
            removed_color = QColor(220, 30, 30, 160)
            painter.setBrush(QBrush(removed_color))
            painter.setPen(Qt.PenStyle.NoPen)
            for (px, py) in mask:
                lx = px - self._bx1
                ly = py - self._by1
                # Only paint if in valid local coordinates
                if 0 <= lx < self._slice_w and 0 <= ly < self._slice_h:
                    painter.drawRect(QRectF(float(lx), float(ly), 1.0, 1.0))

        # ── Pixel grid (only when zoomed in enough) ─────────────────────────
        if zoom >= self._GRID_THRESHOLD:
            grid_color = QColor(180, 180, 180, 70)
            pen = QPen(grid_color, 1.0 / zoom)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            left = max(0, int(rect.left()))
            top = max(0, int(rect.top()))
            right = min(self._slice_w, int(rect.right()) + 2)
            bottom = min(self._slice_h, int(rect.bottom()) + 2)

            for x in range(left, right + 1):
                painter.drawLine(QPointF(x, top), QPointF(x, bottom))
            for y in range(top, bottom + 1):
                painter.drawLine(QPointF(left, y), QPointF(right, y))

    # ── Mouse / Wheel ─────────────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.set_zoom(self._zoom * factor)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            scene_pt = self.mapToScene(event.pos())

            # Use math.floor() instead of int() to ensure a click always
            # maps to exactly ONE pixel, never split across two adjacent ones.
            # int() truncates toward zero, which misaligns for fractional coords
            # near pixel boundaries (e.g. 2.9999 → 2, but -0.001 → 0 not -1).
            lx = math.floor(scene_pt.x())
            ly = math.floor(scene_pt.y())

            # Convert local slice coords → absolute image-space coords
            px = self._bx1 + lx
            py = self._by1 + ly

            # Validate bounds
            if not (self._bx1 <= px < self._bx1 + self._slice_w and
                    self._by1 <= py < self._by1 + self._slice_h):
                return

            # Snapshot for undo before mutating
            if self._undo is not None:
                self._undo.push(self._session, "pixel_mask_toggle")

            removed = self._pms.toggle_pixel(self._session, self._slice_idx, px, py)
            logger.debug("Pixel (%d, %d) %s", px, py, "removed" if removed else "restored")
            self.viewport().update()
            # Prevent the event being handled as a pan gesture
            return

        super().mousePressEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# Public dialog
# ─────────────────────────────────────────────────────────────────────────────

class SlicePixelEditorDialog(QDialog):
    """Floating pixel editor for a single extracted slice.

    Args:
        main_window: The application main window (used to access the session).
        slice_idx: Index of the slice in ``session.selected_cells``.
        pixel_mask_service: Shared :class:`PixelMaskService` instance.
        undo_manager: Shared :class:`UndoManager` instance (may be ``None``).
    """

    def __init__(
        self,
        main_window,
        slice_idx: int,
        pixel_mask_service: PixelMaskService,
        undo_manager: Optional[UndoManager] = None,
    ) -> None:
        super().__init__(main_window)
        self._mw = main_window
        self._slice_idx = slice_idx
        self._pms = pixel_mask_service
        self._undo = undo_manager

        session: Optional[ImageSession] = main_window.current_session
        if session is None or slice_idx >= len(session.selected_cells):
            self._canvas: Optional[_PixelCanvas] = None
            self._setup_error_ui()
            return

        self._session = session
        slice_rects = session.selected_cells[slice_idx]
        bx1 = min(r[0] for r in slice_rects)
        by1 = min(r[1] for r in slice_rects)
        bx2 = max(r[2] for r in slice_rects)
        by2 = max(r[3] for r in slice_rects)
        w = bx2 - bx1
        h = by2 - by1

        # Fetch full-resolution crop (may be large — runs synchronously here
        # because the dialog only opens on explicit user action)
        try:
            pil_img = session.pyramid.get_region_fullres(bx1, by1, w, h)
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            raw = pil_img.tobytes("raw", "RGB")
            qim = QImage(raw, pil_img.width, pil_img.height, QImage.Format.Format_RGB888).copy()
            pixmap = QPixmap.fromImage(qim)
        except Exception as exc:
            logger.exception("Failed to load slice pixels for pixel editor: %s", exc)
            self._canvas = None
            self._setup_error_ui()
            return

        self._canvas = _PixelCanvas(
            pixmap=pixmap,
            slice_w=w,
            slice_h=h,
            bx1=bx1,
            by1=by1,
            slice_idx=slice_idx,
            session=session,
            pixel_mask_service=pixel_mask_service,
            undo_manager=undo_manager,
            parent=self,
        )

        self._setup_ui(session, slice_idx)

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_error_ui(self) -> None:
        self.setWindowTitle("Pixel Editor — Error")
        self.setMinimumSize(300, 120)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Could not load slice pixels. The slice may be empty or the image unavailable."))
        btn = QPushButton("Close")
        btn.clicked.connect(self.reject)
        layout.addWidget(btn)

    def _setup_ui(self, session: ImageSession, slice_idx: int) -> None:
        meta = session.slice_metadata[slice_idx] if slice_idx < len(session.slice_metadata) else {}
        name = meta.get("name") or f"Slice {slice_idx + 1}"
        self.setWindowTitle(f"Pixel Editor — {name}")
        self.setMinimumSize(720, 540)
        self.resize(900, 680)
        self.setWindowFlag(Qt.WindowType.Window, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()

        # Hint label
        hint = QLabel("Right-click a pixel to remove/restore it  |  Scroll to zoom  |  Drag to pan")
        hint.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        toolbar.addWidget(hint)
        toolbar.addStretch()

        # Zoom controls
        zoom_label = QLabel("Zoom:")
        zoom_label.setStyleSheet("color: #cccccc; font-size: 12px;")
        toolbar.addWidget(zoom_label)

        btn_minus = QPushButton("−")
        btn_minus.setFixedSize(28, 28)
        btn_minus.setToolTip("Zoom out")
        btn_minus.clicked.connect(lambda: self._canvas.zoom_out() if self._canvas else None)
        toolbar.addWidget(btn_minus)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(1, 64)
        self._zoom_slider.setValue(8)
        self._zoom_slider.setFixedWidth(130)
        self._zoom_slider.setToolTip("Pixel size (zoom level)")
        self._zoom_slider.valueChanged.connect(self._on_slider_zoom)
        toolbar.addWidget(self._zoom_slider)

        btn_plus = QPushButton("+")
        btn_plus.setFixedSize(28, 28)
        btn_plus.setToolTip("Zoom in")
        btn_plus.clicked.connect(lambda: self._canvas.zoom_in() if self._canvas else None)
        toolbar.addWidget(btn_plus)

        btn_reset = QPushButton("⌂ Reset")
        btn_reset.setToolTip("Reset zoom to default")
        btn_reset.clicked.connect(self._on_reset_zoom)
        toolbar.addWidget(btn_reset)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        toolbar.addWidget(btn_close)

        root.addLayout(toolbar)

        # ── Canvas ────────────────────────────────────────────────────────────
        root.addWidget(self._canvas)

        # ── Status bar ───────────────────────────────────────────────────────
        self._status_label = QLabel(self._mask_status_text())
        self._status_label.setStyleSheet("color: #888888; font-size: 10px;")
        root.addWidget(self._status_label)

        # Apply dark theme to the dialog
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; }
            QLabel  { color: #cccccc; }
            QPushButton {
                background-color: #3a3a3a;
                color: #eeeeee;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 3px 8px;
            }
            QPushButton:hover  { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #555555; }
            QSlider::groove:horizontal { height: 4px; background: #444; border-radius: 2px; }
            QSlider::handle:horizontal {
                background: #74C0FC; width: 14px; height: 14px;
                margin: -5px 0; border-radius: 7px;
            }
            QGraphicsView { border: 1px solid #444; background-color: #111; }
        """)

    # ── Slot implementations ──────────────────────────────────────────────────

    def _on_slider_zoom(self, value: int) -> None:
        if self._canvas:
            self._canvas.set_zoom(float(value))

    def _on_reset_zoom(self) -> None:
        if self._canvas:
            self._canvas.reset_zoom()
            self._zoom_slider.setValue(8)

    def _mask_status_text(self) -> str:
        if not hasattr(self, "_session"):
            return ""
        count = len(self._pms.get_mask(self._session, self._slice_idx))
        return f"{count} pixel(s) removed in this slice"
