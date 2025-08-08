"""AlignCanvas widget that exposes signals and delegates to CanvasCore.

Adds Qt signals, undo/redo, pan mode, and small glue for external UI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any

from PyQt5 import QtCore, QtWidgets  # type: ignore
import cv2

from .canvas_core import CanvasCore
from .canvas_affine import affine_params_to_small
from .canvas_perspective import ensure_perspective_quad


class AlignCanvas(CanvasCore):
    """Public widget API with signals and helpers."""

    # Emits Path or None whenever current file changes
    currentPathChanged = QtCore.pyqtSignal(object)  # type: ignore[attr-defined]
    # Emits (done, total) during crop
    cropProgress = QtCore.pyqtSignal(int, int)  # type: ignore[attr-defined]
    # Mode changed
    modeChanged = QtCore.pyqtSignal(bool)  # True if perspective
    # Corner changed
    activeCornerChanged = QtCore.pyqtSignal(int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._hand_pan = False
        self._undo_stack: Dict[Path, list] = {}
        self._redo_stack: Dict[Path, list] = {}

    # ----- signal glue -----

    def _emit_current_path(self) -> None:
        """Emit currentPathChanged for external UI."""
        self.currentPathChanged.emit(self.current_path())

    def _emit_crop_progress(self, done: int, total: int) -> None:
        """Emit crop progress for external UI."""
        self.cropProgress.emit(done, total)

    # ----- history -----

    def _push_undo(self) -> None:
        p = self.current_path()
        if not p:
            return
        snap = self.params.get(p, {}).copy()
        self._undo_stack.setdefault(p, []).append(snap)
        # clear redo on new change
        self._redo_stack[p] = []

    def undo(self) -> None:
        p = self.current_path()
        if not p:
            return
        stack = self._undo_stack.get(p, [])
        if not stack:
            return
        cur = self.params.get(p, {}).copy()
        prev = stack.pop()
        self._redo_stack.setdefault(p, []).append(cur)
        self.params[p] = prev
        self.update()

    def redo(self) -> None:
        p = self.current_path()
        if not p:
            return
        stack = self._redo_stack.get(p, [])
        if not stack:
            return
        cur = self.params.get(p, {}).copy()
        nxt = stack.pop()
        self._undo_stack.setdefault(p, []).append(cur)
        self.params[p] = nxt
        self.update()

    def reset_current_image(self) -> None:
        p = self.current_path()
        if not p:
            return
        self._push_undo()
        self.params[p] = {"tx": 0.0, "ty": 0.0, "theta": 0.0, "scale": 1.0}
        self.update()

    # ----- public helpers for UI -----

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

    def set_hand_pan_mode(self, enabled: bool) -> None:
        self._hand_pan = bool(enabled)
        self.hand_pan_mode = bool(enabled)
        if enabled:
            self.setCursor(QtCore.Qt.OpenHandCursor)
        else:
            self.setCursor(QtCore.Qt.ArrowCursor)
        self.update()

    # ----- mode / perspective helpers -----

    def set_perspective_mode(self, is_persp: bool) -> None:
        if self.perspective_mode == bool(is_persp):
            return
        self.perspective_mode = bool(is_persp)
        # Initialize perspective quad from current affine transform once
        if self.perspective_mode:
            pth = self.current_path()
            if pth:
                pr = self.params.get(pth, None)
                if pr is not None:
                    # Only init if no quad exists
                    if "persp" not in pr:
                        mov_prev = self._get_preview(pth)
                        m_small = affine_params_to_small(mov_prev, pr)
                        # transform corners
                        import numpy as np

                        h, w = mov_prev.shape[:2]
                        corners = np.float32(
                            [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]
                        ).reshape(-1, 1, 2)
                        m3 = np.vstack([m_small, [0, 0, 1]]).astype(np.float32)
                        tc = cv2.perspectiveTransform(corners, m3).reshape(-1, 2)
                        pr["persp"] = [(float(x), float(y)) for x, y in tc]
        self.modeChanged.emit(self.perspective_mode)
        self.update()

    def set_active_corner(self, idx: int) -> None:
        self.active_corner = max(0, min(3, int(idx)))
        self.activeCornerChanged.emit(self.active_corner)
        self.update()

    def nudge_corner(self, dx: float, dy: float) -> None:
        if not self.perspective_mode:
            return
        p = self.current_path()
        if not p:
            return
        pr = self.params.get(p, None)
        if pr is None:
            return
        ensure_perspective_quad(pr, self.pw, self.ph)
        quad = pr["persp"]  # type: ignore[index]
        x, y = quad[self.active_corner]
        quad[self.active_corner] = (x + dx, y + dy)
        pr["persp"] = quad  # type: ignore[index]
        self.update()

    # ----- transform helpers -----

    def move_dxdy(self, dx: float, dy: float) -> None:
        if self.perspective_mode:
            # In perspective mode, use corner nudge via context group
            return
        p = self.current_path()
        if not p:
            return
        pr = self.params[p]
        self._push_undo()
        pr["tx"] = float(pr.get("tx", 0.0)) + dx
        pr["ty"] = float(pr.get("ty", 0.0)) + dy
        self.update()

    def rotate_deg(self, deg: float) -> None:
        if self.perspective_mode:
            return
        p = self.current_path()
        if not p:
            return
        pr = self.params[p]
        self._push_undo()
        pr["theta"] = float(pr.get("theta", 0.0)) + float(deg)
        self.update()

    def zoom_factor(self, factor: float) -> None:
        if self.perspective_mode:
            return
        p = self.current_path()
        if not p:
            return
        pr = self.params[p]
        self._push_undo()
        from align_app.utils.img_io import clamp

        pr["scale"] = clamp(float(pr.get("scale", 1.0)) * float(factor), 0.8, 1.2)
        self.update()
