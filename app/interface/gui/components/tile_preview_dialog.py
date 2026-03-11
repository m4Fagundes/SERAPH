"""
tile_preview_dialog.py
======================
Dedicated viewer that renders a slice/tile at its **true 1:1 pixel resolution**,
reading directly from ``ImagePyramid.get_region_fullres()`` in a background thread.

Design decisions (python-patterns skill):
- I/O-bound image read → ``QRunnable`` in Qt's thread pool (non-blocking UI)
- Type hints on every public method / parameter
- Single responsibility: this module only handles display, not data mutation
- Error handling isolated in the worker → clean error message to dialog
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import (
    Qt, QRunnable, QObject, QThreadPool, pyqtSignal, QSize
)
from PyQt6.QtGui import QImage, QPixmap, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QSizePolicy, QApplication,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker: reads the full-res region in a background thread
# ---------------------------------------------------------------------------

class _LoadSignals(QObject):
    finished = pyqtSignal(object)   # emits PIL Image on success
    error    = pyqtSignal(str)       # emits error message string on failure


class _RegionLoader(QRunnable):
    """Background worker that reads a bounding-box region at full resolution.

    Args:
        pyramid: ``ImagePyramid`` instance from the active session.
        x1, y1, x2, y2: bounding-box in full-resolution image coordinates.
    """

    def __init__(self, pyramid, x1: int, y1: int, x2: int, y2: int) -> None:
        super().__init__()
        self._pyramid = pyramid
        self._x1, self._y1 = x1, y1
        self._x2, self._y2 = x2, y2
        self.signals = _LoadSignals()

    def run(self) -> None:  # executed in thread-pool thread
        try:
            w = self._x2 - self._x1
            h = self._y2 - self._y1
            pil_img = self._pyramid.get_region_fullres(self._x1, self._y1, w, h)
            if pil_img.mode not in ("RGB", "RGBA"):
                pil_img = pil_img.convert("RGB")
            self.signals.finished.emit(pil_img)
        except Exception as exc:
            logger.exception("RegionLoader failed: %s", exc)
            self.signals.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class TilePreviewDialog(QDialog):
    """Modal dialog that shows the selected slice at true 1:1 resolution.

    Opens a scroll area so the user can pan large tile images. Image is loaded
    asynchronously so the dialog appears instantly with a loading indicator.

    Args:
        session:    The active ``ImageSession``.
        slice_idx:  Which slice to display.
        parent:     Optional Qt parent widget.
    """

    _STYLE_DIALOG = """
        QDialog {
            background-color: #1e1e1e;
            color: #cccccc;
        }
    """
    _STYLE_LABEL = "color: #cccccc; font-size: 12px; padding: 4px;"
    _STYLE_META  = "color: #888888; font-size: 11px; padding: 2px 4px;"
    _STYLE_BTN   = (
        "QPushButton { background-color: #007acc; color: white; padding: 6px 16px; "
        "font-weight: bold; border-radius: 4px; }"
        "QPushButton:hover { background-color: #005f9e; }"
    )
    _STYLE_COPY_BTN = (
        "QPushButton { background-color: #3d3d3d; color: #cccccc; padding: 6px 16px; "
        "font-weight: bold; border-radius: 4px; }"
        "QPushButton:hover { background-color: #505050; }"
    )

    def __init__(
        self,
        session,
        slice_idx: int,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._session   = session
        self._slice_idx = slice_idx
        self._pixmap: Optional[QPixmap] = None

        self._compute_bounds()
        self._setup_ui()
        self._start_load()

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _compute_bounds(self) -> None:
        """Derive the bounding box from all rects in the target slice."""
        rects = self._session.selected_cells[self._slice_idx]
        self._x1 = min(r[0] for r in rects)
        self._y1 = min(r[1] for r in rects)
        self._x2 = max(r[2] for r in rects)
        self._y2 = max(r[3] for r in rects)
        self._w  = self._x2 - self._x1
        self._h  = self._y2 - self._y1

    def _setup_ui(self) -> None:
        meta = (self._session.slice_metadata[self._slice_idx]
                if self._slice_idx < len(self._session.slice_metadata) else {})
        name = meta.get("name") or f"Slice {self._slice_idx + 1}"
        mpp  = meta.get("microns_per_pixel", "")

        self.setWindowTitle(f"🖼️ {name} — Resolução Real 1:1")
        self.setMinimumSize(480, 360)
        self.setStyleSheet(self._STYLE_DIALOG)

        # Main layout
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        # ── Header info bar ──────────────────────────────────────────────
        info_row = QHBoxLayout()
        self._lbl_info = QLabel(
            f"<b>{name}</b>  "
            f"<span style='color:#666;'>Origem: ({self._x1}, {self._y1}) | "
            f"Tamanho: {self._w}×{self._h} px"
            + (f" | {mpp} µm/px" if mpp else "")
            + "</span>"
        )
        self._lbl_info.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_info.setStyleSheet(self._STYLE_LABEL)
        info_row.addWidget(self._lbl_info)
        info_row.addStretch()
        root.addLayout(info_row)

        # ── Scroll area (image goes here) ────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setStyleSheet(
            "QScrollArea { background: #111; border: 1px solid #333; }"
        )

        # Loading placeholder
        self._img_label = QLabel("⏳  Carregando imagem em resolução real…")
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setStyleSheet(
            "color: #888; font-size: 14px; background: #111; padding: 40px;"
        )
        self._img_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._scroll.setWidget(self._img_label)

        root.addWidget(self._scroll, stretch=1)

        # ── Status bar ───────────────────────────────────────────────────
        self._lbl_status = QLabel("Lendo pixels da imagem original…")
        self._lbl_status.setStyleSheet(self._STYLE_META)
        root.addWidget(self._lbl_status)

        # ── Button row ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_close = QPushButton("✕  Fechar")
        btn_close.setStyleSheet(self._STYLE_BTN)
        btn_close.clicked.connect(self.close)
        btn_close.setShortcut("Escape")
        btn_row.addWidget(btn_close)

        root.addLayout(btn_row)

        # ── Resize dialog to a comfortable size (max 80% of screen) ─────
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            max_w = int(sg.width()  * 0.80)
            max_h = int(sg.height() * 0.80)
            dlg_w = min(self._w  + 40, max_w)
            dlg_h = min(self._h  + 130, max_h)
            self.resize(max(480, dlg_w), max(360, dlg_h))

    # ------------------------------------------------------------------
    # Async image loading
    # ------------------------------------------------------------------

    def _start_load(self) -> None:
        """Dispatch the background region read."""
        loader = _RegionLoader(
            self._session.pyramid,
            self._x1, self._y1, self._x2, self._y2,
        )
        loader.signals.finished.connect(self._on_image_ready)
        loader.signals.error.connect(self._on_load_error)
        QThreadPool.globalInstance().start(loader)

    def _on_image_ready(self, pil_img) -> None:
        """Slot called from the main thread after the region is loaded."""
        mode = pil_img.mode            # "RGB" or "RGBA"
        channels = len(pil_img.getbands())
        data  = pil_img.tobytes("raw", mode)

        fmt = (QImage.Format.Format_RGBA8888
               if mode == "RGBA"
               else QImage.Format.Format_RGB888)
        stride = pil_img.width * channels

        qimg = QImage(data, pil_img.width, pil_img.height, stride, fmt).copy()
        self._pixmap = QPixmap.fromImage(qimg)

        self._img_label.setPixmap(self._pixmap)
        self._img_label.setFixedSize(self._pixmap.size())
        self._img_label.setStyleSheet("")   # remove loading style

        size_kb = (pil_img.width * pil_img.height * channels) / 1024
        self._lbl_status.setText(
            f"✅  Imagem carregada  |  {pil_img.width}×{pil_img.height} px  |  "
            f"~{size_kb:.0f} KB  |  Scroll para navegar"
        )

    def _on_load_error(self, message: str) -> None:
        """Slot called if the region read fails."""
        self._img_label.setText(f"❌  Erro ao carregar imagem:\n{message}")
        self._img_label.setStyleSheet(
            "color: #ff5555; font-size: 13px; background: #1e1e1e; padding: 20px;"
        )
        self._lbl_status.setText("Falha ao ler os pixels da imagem original.")
        logger.error("TilePreviewDialog load error: %s", message)
