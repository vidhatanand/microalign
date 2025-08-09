"""AlignCanvas wrapper around the mixin-based CanvasWidget (compat layer).

Keeps the public API expected by toolbars and the rest of the UI,
without changing any UI or capabilities.
"""

from __future__ import annotations

from PyQt5 import QtCore  # type: ignore

from .canvas_widget import CanvasWidget


class AlignCanvas(CanvasWidget):
    """Public widget API, compatible with existing toolbars."""

    # --- Back-compat for the Top toolbar "Pan" toggle ---
    def set_hand_pan_mode(self, enabled: bool) -> None:
        """Old name kept for the toolbar; maps to mixin pan mode."""
        self.set_pan_mode(bool(enabled))

    # --- Back-compat for view pan QPointF used by the toolbar reset ---
    @property
    def view_pan(self) -> QtCore.QPointF:  # type: ignore[override]
        return QtCore.QPointF(
            float(getattr(self, "view_pan_xp", 0.0)),
            float(getattr(self, "view_pan_yp", 0.0)),
        )

    @view_pan.setter
    def view_pan(self, pt: QtCore.QPointF) -> None:  # type: ignore[override]
        self.view_pan_xp = float(pt.x())
        self.view_pan_yp = float(pt.y())

    # --- Back-compat for toolbar "Reset Image" ---
    def reset_current_image(self) -> None:
        """Old name; calls the mixin reset method."""
        self.reset_current()
