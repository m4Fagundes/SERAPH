"""
InputAdapter — Platform Input Port & Adapters
==============================================

Architecture: Hexagonal Architecture (Ports & Adapters) + python-patterns
  - InputPort: Abstract interface (Port) — decouples renderers from platform events
  - MacOSInputAdapter: Concrete implementation for macOS trackpad/Magic Mouse/keyboard
  - WindowsInputAdapter: Concrete implementation for Windows mouse/keyboard

Design Decisions (python-patterns §4 — Separate concerns):
  - Renderers own NO platform-detection logic (no `if sys.platform` scattered around)
  - All event translation is the adapter's responsibility
  - Strongly typed InputCommand prevents implicit coupling (python-patterns §3 — Type hints)

macOS-specific behaviours handled here:
  1. Trackpad two-finger scroll  → pan (pixelDelta)
  2. Trackpad pinch              → zoom (QNativeGestureEvent ZoomNativeGesture)
  3. Magic Mouse scroll          → zoom (angleDelta only, no pixelDelta)
  4. Ctrl+LeftClick              → right-click equivalent (cell select/deselect)
  5. Cmd+Z / Cmd+Shift+Z        → Undo / Redo
  6. +/= / - / 0                 → Zoom in / out / reset
  7. Delete / Backspace          → Clear selection
  8. Escape                      → Close isolated tile / deactivate tool
"""

from __future__ import annotations

import platform
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QWheelEvent, QMouseEvent, QKeyEvent


# ---------------------------------------------------------------------------
# Domain types  (python-patterns §3 — always type public APIs)
# ---------------------------------------------------------------------------

class InputAction(Enum):
    """Canonical actions that a renderer can respond to — platform-agnostic."""
    PAN         = auto()   # Translate camera by (dx, dy) in screen pixels
    ZOOM        = auto()   # Scale around pivot (cx, cy) by 'factor'
    ZOOM_RESET  = auto()   # Restore to fit-to-screen zoom
    RIGHT_CLICK = auto()   # Cell select / deselect (scene coords)
    UNDO        = auto()
    REDO        = auto()
    CLEAR       = auto()   # Clear all selections
    ESCAPE      = auto()   # Exit isolated tile / cancel active action
    PASSTHROUGH = auto()   # Let Qt handle the event as usual


@dataclass
class InputCommand:
    """Result of translating a platform event into a domain action.

    Attributes:
        action:  What the renderer should do.
        dx, dy:  Pan delta in *screen* pixels (for PAN).
        factor:  Zoom scale multiplier (for ZOOM).
        cx, cy:  Zoom pivot in *viewport* pixels (for ZOOM).
        consume: If True the renderer must NOT call super().
    """
    action: InputAction = InputAction.PASSTHROUGH
    dx: float = 0.0
    dy: float = 0.0
    factor: float = 1.0
    cx: float = 0.0
    cy: float = 0.0
    consume: bool = False


# ---------------------------------------------------------------------------
# Port  (abstract interface)
# ---------------------------------------------------------------------------

class InputPort(ABC):
    """Abstract port that translates raw Qt events into InputCommands.

    Renderers call these methods and react to the returned InputCommand.
    They never inspect `platform.system()` or Qt modifiers directly.
    """

    @abstractmethod
    def translate_wheel(self, event: QWheelEvent) -> InputCommand:
        """Translate a QWheelEvent into a pan or zoom command."""

    @abstractmethod
    def translate_mouse_press(self, event: QMouseEvent) -> InputCommand:
        """Translate a QMouseEvent into a right-click or passthrough command."""

    @abstractmethod
    def translate_key(self, event: QKeyEvent) -> InputCommand:
        """Translate a QKeyEvent into undo/redo/zoom/clear/escape."""

    @abstractmethod
    def translate_pinch(self, scale_factor: float, cx: float, cy: float) -> InputCommand:
        """Translate a native pinch gesture into a zoom command."""


# ---------------------------------------------------------------------------
# macOS Adapter
# ---------------------------------------------------------------------------

class MacOSInputAdapter(InputPort):
    """Concrete adapter for Apple hardware.

    Scroll sources on macOS (PyQt6):
      - Trackpad two-finger drag  → pixelDelta is non-zero, angleDelta may also be set
      - Magic Mouse scroll         → angelDelta non-zero, pixelDelta is (0,0)
      - Mouse wheel (USB)          → angleDelta non-zero, pixelDelta is (0,0)

    Strategy:
      - pixelDelta present  → PAN (trackpad scroll is navigation, not zoom)
      - pixelDelta absent   → ZOOM (physical wheel / Magic Mouse)
    """

    # Sensitivities (tuned for 144 dpi Retina)
    _PAN_SENSITIVITY: float = 1.0     # screen-pixel-per-reported-pixel (trackpad)
    _ZOOM_STEP: float = 0.0015        # per angleDelta unit (Magic Mouse / scroll wheel)
    _ZOOM_PINCH_MIN: float = 0.9
    _ZOOM_PINCH_MAX: float = 1.1

    def translate_wheel(self, event: QWheelEvent) -> InputCommand:
        pixel = event.pixelDelta()
        angle = event.angleDelta()

        pos = event.position()
        cx, cy = pos.x(), pos.y()

        # ── Trackpad: pixelDelta reports real pixel displacement ────────────
        if pixel.x() != 0 or pixel.y() != 0:
            return InputCommand(
                action=InputAction.PAN,
                dx=-pixel.x() * self._PAN_SENSITIVITY,
                dy=-pixel.y() * self._PAN_SENSITIVITY,
                consume=True,
            )

        # ── Magic Mouse / physical wheel: use angleDelta for zoom ──────────
        if angle.y() != 0:
            # Each "notch" = 120 units; we accumulate a smooth factor
            raw = angle.y()
            factor = 1.0 + raw * self._ZOOM_STEP
            factor = max(0.5, min(factor, 2.5))   # clamp runaway
            return InputCommand(
                action=InputAction.ZOOM,
                factor=factor,
                cx=cx, cy=cy,
                consume=True,
            )

        # Horizontal-only angle (Magic Mouse lateral swipe) → horizontal pan
        if angle.x() != 0:
            raw = angle.x()
            factor = 1.0 + raw * self._ZOOM_STEP
            factor = max(0.5, min(factor, 2.5))
            return InputCommand(
                action=InputAction.PAN,
                dx=-raw * 0.3,
                dy=0.0,
                consume=True,
            )

        return InputCommand()

    def translate_mouse_press(self, event: QMouseEvent) -> InputCommand:
        """Map Ctrl+LeftButton → RIGHT_CLICK (macOS secondary-click convention)."""
        mods = event.modifiers()
        btn = event.button()
        pos = event.position()

        is_ctrl_click = (
            btn == Qt.MouseButton.LeftButton
            and bool(mods & Qt.KeyboardModifier.ControlModifier)
        )
        if is_ctrl_click:
            return InputCommand(
                action=InputAction.RIGHT_CLICK,
                cx=pos.x(), cy=pos.y(),
                consume=True,
            )
        return InputCommand()

    def translate_key(self, event: QKeyEvent) -> InputCommand:
        key = event.key()
        mods = event.modifiers()
        meta = Qt.KeyboardModifier.MetaModifier   # Cmd key on macOS in Qt

        # Undo — Cmd+Z
        if key == Qt.Key.Key_Z and (mods & meta):
            if mods & Qt.KeyboardModifier.ShiftModifier:
                return InputCommand(action=InputAction.REDO, consume=True)
            return InputCommand(action=InputAction.UNDO, consume=True)

        # Zoom in — Cmd++ or just +/=
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            factor = 1.25
            return InputCommand(action=InputAction.ZOOM, factor=factor, consume=True)

        # Zoom out — Cmd+- or just -
        if key == Qt.Key.Key_Minus:
            return InputCommand(action=InputAction.ZOOM, factor=0.8, consume=True)

        # Zoom reset — Cmd+0 or just 0
        if key == Qt.Key.Key_0:
            return InputCommand(action=InputAction.ZOOM_RESET, consume=True)

        # Clear selection
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            return InputCommand(action=InputAction.CLEAR, consume=True)

        # Escape — exit tool / tile isolation
        if key == Qt.Key.Key_Escape:
            return InputCommand(action=InputAction.ESCAPE, consume=True)

        return InputCommand()

    def translate_pinch(self, scale_factor: float, cx: float, cy: float) -> InputCommand:
        """Convert a QNativeGestureEvent ZoomNativeGesture into a zoom command.

        Qt reports cumulative scale factor per event (e.g. 0.02 for a small spread).
        We clamp and apply it as a multiplicative factor.
        """
        # scale_factor from QNativeGestureEvent.value() is *delta*, e.g. 0.03 per frame
        factor = 1.0 + max(self._ZOOM_PINCH_MIN - 1.0, min(scale_factor, self._ZOOM_PINCH_MAX - 1.0))
        return InputCommand(
            action=InputAction.ZOOM,
            factor=factor,
            cx=cx, cy=cy,
            consume=True,
        )


# ---------------------------------------------------------------------------
# Windows Adapter
# ---------------------------------------------------------------------------

class WindowsInputAdapter(InputPort):
    """Concrete adapter for Windows/Linux mouse + keyboard.

    Scroll:
      - Vertical wheel → zoom (same as original behaviour)
      - Shift + wheel  → horizontal pan
    """

    _ZOOM_FACTOR_UP: float = 1.25
    _ZOOM_FACTOR_DOWN: float = 0.8

    def translate_wheel(self, event: QWheelEvent) -> InputCommand:
        angle = event.angleDelta()
        mods = event.modifiers()
        pos = event.position()
        cx, cy = pos.x(), pos.y()
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        ctrl  = bool(mods & Qt.KeyboardModifier.ControlModifier)

        # Ctrl+scroll → zoom (power-user shortcut)
        if ctrl and angle.y() != 0:
            factor = self._ZOOM_FACTOR_UP if angle.y() > 0 else self._ZOOM_FACTOR_DOWN
            return InputCommand(action=InputAction.ZOOM, factor=factor, cx=cx, cy=cy, consume=True)

        # Shift+scroll → horizontal pan
        if shift and angle.y() != 0:
            # angleDelta unit = 1/8 degree; 120 = one notch
            pixels = (angle.y() / 120) * 40
            return InputCommand(action=InputAction.PAN, dx=pixels, dy=0.0, consume=True)

        # Plain scroll → vertical zoom
        if angle.y() != 0:
            factor = self._ZOOM_FACTOR_UP if angle.y() > 0 else self._ZOOM_FACTOR_DOWN
            return InputCommand(action=InputAction.ZOOM, factor=factor, cx=cx, cy=cy, consume=True)

        return InputCommand()

    def translate_mouse_press(self, event: QMouseEvent) -> InputCommand:
        # Windows right-click is handled natively by Qt as RightButton;
        # no additional translation needed here.
        return InputCommand()

    def translate_key(self, event: QKeyEvent) -> InputCommand:
        key = event.key()
        mods = event.modifiers()
        ctrl = Qt.KeyboardModifier.ControlModifier

        # Undo — Ctrl+Z
        if key == Qt.Key.Key_Z and (mods & ctrl):
            if mods & Qt.KeyboardModifier.ShiftModifier:
                return InputCommand(action=InputAction.REDO, consume=True)
            return InputCommand(action=InputAction.UNDO, consume=True)

        # Zoom in
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            return InputCommand(action=InputAction.ZOOM, factor=1.25, consume=True)

        # Zoom out
        if key == Qt.Key.Key_Minus:
            return InputCommand(action=InputAction.ZOOM, factor=0.8, consume=True)

        # Zoom reset
        if key == Qt.Key.Key_0:
            return InputCommand(action=InputAction.ZOOM_RESET, consume=True)

        # Clear
        if key == Qt.Key.Key_Delete:
            return InputCommand(action=InputAction.CLEAR, consume=True)

        # Escape
        if key == Qt.Key.Key_Escape:
            return InputCommand(action=InputAction.ESCAPE, consume=True)

        return InputCommand()

    def translate_pinch(self, scale_factor: float, cx: float, cy: float) -> InputCommand:
        # Windows laptops rarely send native pinch events; no-op fallback
        return InputCommand()


# ---------------------------------------------------------------------------
# Factory function  (python-patterns §4 — structure by feature, not boilerplate)
# ---------------------------------------------------------------------------

def create_input_adapter() -> InputPort:
    """Return the correct InputPort implementation for the current OS."""
    if platform.system() == "Darwin":
        return MacOSInputAdapter()
    return WindowsInputAdapter()
