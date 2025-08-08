"""AlignCanvas widget that exposes signals and delegates to CanvasCore.

Adds Qt signals and glue on top of CanvasCore so external UI can react.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5 import QtCore, QtWidgets  # pylint: disable=no-name-in-module

from .canvas_core import CanvasCore


class AlignCanvas(CanvasCore):
    """Public widget API with signals."""

    # Emits Path or None whenever current file changes
    currentPathChanged = QtCore.pyqtSignal(object)  # type: ignore[attr-defined]
    # Emits (done, total) during crop
    cropProgress = QtCore.pyqtSignal(int, int)  # type: ignore[attr-defined]
    # Emits when perspective mode toggles
    modeChanged = QtCore.pyqtSignal(bool)  # type: ignore[attr-defined]
    # Emits when active corner changes (0..3)
    activeCornerChanged = QtCore.pyqtSignal(int)  # type: ignore[attr-defined]

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)

    # ----- signal glue -----

    def _emit_current_path(self) -> None:
        """Emit currentPathChanged for external UI."""
        self.currentPathChanged.emit(self.current_path())

    def _emit_crop_progress(self, done: int, total: int) -> None:
        """Emit crop progress for external UI."""
        self.cropProgress.emit(done, total)

    # Hooks from CanvasCore
    def _on_mode_changed(self, is_persp: bool) -> None:
        self.modeChanged.emit(bool(is_persp))

    def _on_active_corner_changed(self, idx: int) -> None:
        self.activeCornerChanged.emit(int(idx))

    # ----- small public helpers for UI -----

    def set_paths(
        self,
        base_path: Optional[Path],
        src_dir: Optional[Path],
        align_out: Optional[Path],
        crop_out: Optional[Path],
        preview_max_side: int = 1600,
    ) -> None:
        super().set_paths(base_path, src_dir, align_out, crop_out, preview_max_side)
        self._emit_current_path()

    def next_image(self) -> None:
        super().next_image()
        self._emit_current_path()

    def prev_image(self) -> None:
        super().prev_image()
        self._emit_current_path()
