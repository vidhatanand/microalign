"""Core canvas implementation: drawing, events, affine/perspective/crop plumbing.

This module contains the shared state and logic that both toolbars and
helpers (affine/perspective/crop) rely on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2  # type: ignore
import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets  # pylint: disable=no-name-in-module

from align_app.utils.img_io import (
    SUPPORTED_LOWER,
    bgr_to_qimage,
    clamp,
    load_image_bgr,
    uniform_preview_scale,
)
from .canvas_affine import (
    affine_compose_preview,
    affine_lift_small_to_full,
    affine_params_to_small,
)
from .canvas_perspective import (
    ensure_perspective_quad,
    perspective_compose_preview,
    perspective_warp_full,
)

# Silence cv2 "no-member" false positives for static analyzers
# pylint: disable=no-member


class CanvasCore(QtWidgets.QWidget):
    """Handles rendering two panels (base/moving) and edit modes."""

    gap = 8  # gap between panels

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setMouseTracking(True)

        # Paths
        self.base_path: Optional[Path] = None
        self.src_dir: Optional[Path] = None
        self.align_out: Optional[Path] = None
        self.crop_out: Optional[Path] = None

        # Images/cache
        self.base_full: Optional[np.ndarray] = None
        self.base_prev: Optional[np.ndarray] = None
        self.files: List[Path] = []
        self.cache_prev: Dict[Path, np.ndarray] = {}

        # Preview scale/size
        self.s: float = 1.0
        self.pw: int = 0
        self.ph: int = 0

        # Draw scale (fitting) + user view zoom (collective)
        self.ds: float = 1.0
        self.view_zoom: float = 1.0
        self.tw: int = 0
        self.th: int = 0

        # View panning (shared across both panels), expressed in PREVIEW pixels
        self.pan_mode: bool = False
        self.view_pan_xp: float = 0.0
        self.view_pan_yp: float = 0.0
        self._view_panning: bool = False
        self._pan_last: Optional[QtCore.QPoint] = None

        # Per-image params
        # affine: tx,ty,theta,scale
        # perspective: quad in PREVIEW coords (dest points TL,TR,BR,BL)
        self.params: Dict[Path, Dict[str, object]] = {}
        self.idx: int = 0

        # History (per image)
        self._hist: Dict[Path, List[Dict[str, object]]] = {}
        self._hist_idx: Dict[Path, int] = {}

        # UI state
        self.alpha = 0.5
        self.step = 1.0
        self.rot_step = 0.10
        self.scale_step = 0.005
        self.micro_scale_step = 0.001
        self.persp_step = 1.0  # nudge step for perspective corner

        self.grid_on = True
        self.grid_step = 40
        self.overlay_mode = False
        self.show_outline = True

        # Mode flags
        self.perspective_mode = False
        self.active_corner = 0  # 0..3 when perspective is active

        # Hover & drag
        self.hover_cell: Optional[Tuple[int, int, int, int]] = None
        self.dragging = False
        self.drag_last: Optional[QtCore.QPoint] = None

        # Crop
        self.crop_mode = False
        self.rubber = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
        self.crop_origin: Optional[QtCore.QPoint] = None
        self.crop_rect_px: Optional[QtCore.QRect] = None
        self.crop_from_aligned: bool = True  # user choice remembered

        # Cached rects for hit-testing in widget coords
        self.left_rect = QtCore.QRect()
        self.right_rect = QtCore.QRect()

    # ---------- overridable hooks for signals (AlignCanvas overrides) ----------

    def _on_mode_changed(self, _is_persp: bool) -> None:
        """Hook: called whenever perspective mode toggles."""
        pass

    def _on_active_corner_changed(self, _idx: int) -> None:
        """Hook: called whenever active corner changes."""
        pass

    # ---------- model access ----------

    def have_base(self) -> bool:
        return self.base_prev is not None

    def have_files(self) -> bool:
        return bool(self.files)

    def current_path(self) -> Optional[Path]:
        if not self.files:
            return None
        return self.files[self.idx]

    # ---------- history ----------

    def _clone_state(self, p: Dict[str, object]) -> Dict[str, object]:
        q = {
            "tx": float(p.get("tx", 0.0)),
            "ty": float(p.get("ty", 0.0)),
            "theta": float(p.get("theta", 0.0)),
            "scale": float(p.get("scale", 1.0)),
        }
        if "persp" in p and isinstance(p["persp"], list) and len(p["persp"]) == 4:
            q["persp"] = [(float(x), float(y)) for (x, y) in p["persp"]]  # type: ignore[index]
        return q

    def _ensure_hist_init(self, path: Path) -> None:
        if path not in self._hist:
            self._hist[path] = [self._clone_state(self.params[path])]
            self._hist_idx[path] = 0

    def _push_history(self, path: Path) -> None:
        self._ensure_hist_init(path)
        lst = self._hist[path]
        idx = self._hist_idx[path]
        # truncate redo tail
        if idx < len(lst) - 1:
            del lst[idx + 1 :]
        lst.append(self._clone_state(self.params[path]))
        # trim very long histories
        if len(lst) > 200:
            lst.pop(0)
            self._hist_idx[path] = len(lst) - 1
        else:
            self._hist_idx[path] = len(lst) - 1

    def _apply_hist_state(self, path: Path, state: Dict[str, object]) -> None:
        p = self.params[path]
        p["tx"] = float(state.get("tx", 0.0))
        p["ty"] = float(state.get("ty", 0.0))
        p["theta"] = float(state.get("theta", 0.0))
        p["scale"] = float(state.get("scale", 1.0))
        if "persp" in state:
            p["persp"] = [(float(x), float(y)) for (x, y) in state["persp"]]  # type: ignore[index]
        elif "persp" in p:
            # keep as-is if not in state
            pass

    def undo(self) -> None:
        path = self.current_path()
        if not path or path not in self._hist:
            return
        idx = self._hist_idx[path]
        if idx <= 0:
            return
        idx -= 1
        self._hist_idx[path] = idx
        self._apply_hist_state(path, self._hist[path][idx])
        self.update()

    def redo(self) -> None:
        path = self.current_path()
        if not path or path not in self._hist:
            return
        idx = self._hist_idx[path]
        if idx >= len(self._hist[path]) - 1:
            return
        idx += 1
        self._hist_idx[path] = idx
        self._apply_hist_state(path, self._hist[path][idx])
        self.update()

    def reset_current(self) -> None:
        path = self.current_path()
        if not path:
            return
        self._push_history(path)
        p = self.params[path]
        p["tx"] = 0.0
        p["ty"] = 0.0
        p["theta"] = 0.0
        p["scale"] = 1.0
        # clear perspective quad; will re-init on demand
        if "persp" in p:
            del p["persp"]
        self.update()

    # ---------- public helpers for UI (used by toolbars) ----------

    def set_perspective_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self.perspective_mode == enabled:
            return
        self.perspective_mode = enabled

        # When enabling perspective, if the quad is "default", initialize it from current affine
        if enabled:
            path = self.current_path()
            if path:
                p = self.params[path]
                ensure_perspective_quad(p, self.pw, self.ph)
                quad = p["persp"]  # type: ignore[index]
                if self._is_default_quad(quad):
                    mov_prev = self._get_preview(path)
                    m_small = affine_params_to_small(mov_prev, p)
                    h, w = mov_prev.shape[:2]
                    corners = np.float32(
                        [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]
                    ).reshape(-1, 1, 2)
                    # apply 2x3 affine to corners
                    tc = cv2.transform(corners, m_small).reshape(-1, 2)
                    p["persp"] = [(float(x), float(y)) for (x, y) in tc]
        self._on_mode_changed(self.perspective_mode)
        self.update()

    def _is_default_quad(self, quad) -> bool:
        default = [
            (0.0, 0.0),
            (self.pw - 1.0, 0.0),
            (self.pw - 1.0, self.ph - 1.0),
            (0.0, self.ph - 1.0),
        ]
        if len(quad) != 4:
            return True
        eps = 1e-3
        for (x1, y1), (x2, y2) in zip(quad, default):
            if abs(x1 - x2) > eps or abs(y1 - y2) > eps:
                return False
        return True

    def set_active_corner(self, idx: int) -> None:
        idx = int(max(0, min(3, idx)))
        if self.active_corner != idx:
            self.active_corner = idx
            self._on_active_corner_changed(self.active_corner)
            self.update()

    def set_pan_mode(self, enabled: bool) -> None:
        self.pan_mode = bool(enabled)
        if self.pan_mode:
            self.setCursor(QtCore.Qt.OpenHandCursor)
        else:
            self._view_panning = False
            self._pan_last = None
            self.setCursor(QtCore.Qt.ArrowCursor)
        self.update()

    def move_dxdy(self, dx: float, dy: float) -> None:
        """Move current image in affine mode by dx/dy (preview pixels)."""
        if not self.have_files() or self.perspective_mode:
            return
        path = self.current_path()
        if not path:
            return
        self._push_history(path)
        p = self.params[path]
        p["tx"] = float(p.get("tx", 0.0)) + float(dx)  # type: ignore[index]
        p["ty"] = float(p.get("ty", 0.0)) + float(dy)  # type: ignore[index]
        self.update()

    def rotate_deg(self, dtheta: float) -> None:
        if not self.have_files() or self.perspective_mode:
            return
        path = self.current_path()
        if not path:
            return
        self._push_history(path)
        p = self.params[path]
        p["theta"] = float(p.get("theta", 0.0)) + float(dtheta)  # type: ignore[index]
        self.update()

    def zoom_factor(self, factor: float) -> None:
        if not self.have_files() or self.perspective_mode:
            return
        path = self.current_path()
        if not path:
            return
        self._push_history(path)
        p = self.params[path]
        cur = float(p.get("scale", 1.0))  # type: ignore[index]
        p["scale"] = clamp(cur * float(factor), 0.8, 1.2)  # type: ignore[index]
        self.update()

    def nudge_corner(self, dx: float, dy: float) -> None:
        """Nudge active perspective corner by dx/dy (preview pixels)."""
        path = self.current_path()
        if not path:
            return
        p = self.params[path]
        ensure_perspective_quad(p, self.pw, self.ph)
        quad = p["persp"]  # type: ignore[index]
        self._push_history(path)
        x, y = quad[self.active_corner]
        quad[self.active_corner] = (x + dx, y + dy)
        p["persp"] = quad  # type: ignore[index]
        self.update()

    # ---------- paths / loading ----------

    def set_paths(
        self,
        base_path: Optional[Path],
        src_dir: Optional[Path],
        align_out: Optional[Path],
        crop_out: Optional[Path],
        preview_max_side: int = 1600,
    ) -> None:
        if base_path is not None:
            self.base_path = base_path
        if src_dir is not None:
            self.src_dir = src_dir
        if align_out is not None:
            self.align_out = align_out
        if crop_out is not None:
            self.crop_out = crop_out

        # Base
        if self.base_path and self.base_path.exists():
            self.base_full = load_image_bgr(str(self.base_path))
            bh, bw = self.base_full.shape[:2]
            self.s = uniform_preview_scale(bw, bh, preview_max_side)
            self.pw, self.ph = int(round(bw * self.s)), int(round(bh * self.s))
            self.base_prev = cv2.resize(
                self.base_full, (self.pw, self.ph), interpolation=cv2.INTER_AREA
            )
        else:
            self.base_full = None
            self.base_prev = None
            self.pw = self.ph = 0

        # Files
        if self.src_dir and self.src_dir.is_dir():
            self.files = sorted(
                (
                    p
                    for p in self.src_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in SUPPORTED_LOWER
                ),
                key=lambda p: str(p).lower(),
            )
            # reset params
            self.params = {
                p: {
                    "tx": 0.0,
                    "ty": 0.0,
                    "theta": 0.0,
                    "scale": 1.0,
                    # quad is lazy-created when needed
                }
                for p in self.files
            }
            self.idx = 0
            self.cache_prev.clear()
            self._hist.clear()
            self._hist_idx.clear()

        self.update()

    # ---------- preview cache ----------

    def _get_preview(self, path: Path) -> np.ndarray:
        if path in self.cache_prev:
            return self.cache_prev[path]
        full = load_image_bgr(str(path))
        prev = cv2.resize(
            full,
            (int(round(full.shape[1] * self.s)), int(round(full.shape[0] * self.s))),
            interpolation=cv2.INTER_AREA,
        )
        self.cache_prev[path] = prev
        return prev

    # ---------- nav ----------

    def next_image(self) -> None:
        if self.files and self.idx < len(self.files) - 1:
            self.idx += 1
            self.update()

    def prev_image(self) -> None:
        if self.files and self.idx > 0:
            self.idx -= 1
            self.update()

    # ---------- compute draw scale ----------

    def _compute_draw_scale(self) -> None:
        """Compute ds, tw, th so both panels fit plus user zoom."""
        if not self.have_base():
            self.ds = 1.0
            self.tw = self.th = 0
            return
        avail_w = max(1, self.width())
        avail_h = max(1, self.height())
        need_w = self.pw * 2 + self.gap
        need_h = self.ph
        sx = avail_w / float(need_w)
        sy = avail_h / float(need_h)
        base_fit = min(sx, sy, 1.0)
        # collective view zoom (applies to both panels)
        vz = clamp(self.view_zoom, 0.25, 5.0)
        self.ds = base_fit * vz
        self.tw = int(round(self.pw * self.ds))
        self.th = int(round(self.ph * self.ds))

    # ---------- painting ----------

    def paintEvent(self, _evt: QtGui.QPaintEvent) -> None:  # noqa: N802
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(20, 20, 20))

        if not self.have_base():
            p.setPen(QtGui.QColor(220, 220, 220))
            p.drawText(
                self.rect(),
                QtCore.Qt.AlignCenter,
                "Pick a Base image from the toolbar.",
            )
            p.end()
            return

        self._compute_draw_scale()

        # Compute view pan offsets in DRAW pixels
        ox = int(round(self.view_pan_xp * self.ds))
        oy = int(round(self.view_pan_yp * self.ds))

        # Left (base)
        left_bgr = self.base_prev.copy() if self.base_prev is not None else None
        if left_bgr is None:
            p.end()
            return
        if self.ds != 1.0:
            left_bgr = cv2.resize(
                left_bgr, (self.tw, self.th), interpolation=cv2.INTER_AREA
            )
        left_img = QtGui.QPixmap.fromImage(bgr_to_qimage(left_bgr))

        # Right (moving)
        right_img = None
        if self.have_files():
            path = self.current_path()
            mov_prev = self._get_preview(path) if path else None
            if mov_prev is not None:
                params = self.params[path]  # type: ignore[index]
                if self.perspective_mode:
                    ensure_perspective_quad(params, self.pw, self.ph)
                    right_bgr = perspective_compose_preview(
                        base_prev=self.base_prev,
                        mov_prev=mov_prev,
                        dest_quad=params["persp"],  # type: ignore[index]
                        overlay=self.overlay_mode,
                        alpha=self.alpha,
                        outline=self.show_outline,
                    )
                else:
                    m_small = affine_params_to_small(mov_prev, params)  # type: ignore[arg-type]
                    right_bgr = affine_compose_preview(
                        base_prev=self.base_prev,
                        mov_prev=mov_prev,
                        m_small=m_small,
                        overlay=self.overlay_mode,
                        alpha=self.alpha,
                        outline=self.show_outline,
                    )
                if self.ds != 1.0:
                    right_bgr = cv2.resize(
                        right_bgr, (self.tw, self.th), interpolation=cv2.INTER_AREA
                    )
                right_img = QtGui.QPixmap.fromImage(bgr_to_qimage(right_bgr))

        # Panel rects (apply pan offset)
        left_rect = QtCore.QRect(-ox, -oy, self.tw, self.th)
        right_rect = QtCore.QRect(self.tw + self.gap - ox, -oy, self.tw, self.th)
        self.left_rect = left_rect
        self.right_rect = right_rect

        p.drawPixmap(left_rect, left_img)

        if right_img is not None:
            p.drawPixmap(right_rect, right_img)
        else:
            p.fillRect(right_rect, QtGui.QColor(40, 40, 40))
            p.setPen(QtGui.QColor(200, 200, 200))
            p.drawText(right_rect, QtCore.Qt.AlignCenter, "Pick a Source directory")

        # Grid
        if self.grid_on:
            step_draw = max(1, int(round(self.grid_step * self.ds)))
            pen = QtGui.QPen(QtGui.QColor(128, 128, 128), 1, QtCore.Qt.SolidLine)
            p.setPen(pen)

            # left (lock grid to content)
            phase_x = (-left_rect.x()) % step_draw
            phase_y = (-left_rect.y()) % step_draw
            x_start = left_rect.left() + phase_x
            while x_start <= left_rect.right():
                p.drawLine(x_start, left_rect.top(), x_start, left_rect.bottom())
                x_start += step_draw
            y_start = left_rect.top() + phase_y
            while y_start <= left_rect.bottom():
                p.drawLine(left_rect.left(), y_start, left_rect.right(), y_start)
                y_start += step_draw

            # right
            phase_x_r = (-right_rect.x()) % step_draw
            phase_y_r = (-right_rect.y()) % step_draw
            xr = right_rect.left() + phase_x_r
            while xr <= right_rect.right():
                p.drawLine(xr, right_rect.top(), xr, right_rect.bottom())
                xr += step_draw
            yr = right_rect.top() + phase_y_r
            while yr <= right_rect.bottom():
                p.drawLine(right_rect.left(), yr, right_rect.right(), yr)
                yr += step_draw

        # Hover-linked grid highlight
        if self.grid_on and self.hover_cell is not None:
            x0, y0, x1, y1 = self.hover_cell
            hp = QtGui.QPen(QtGui.QColor(255, 255, 0), 2, QtCore.Qt.SolidLine)
            p.setPen(hp)
            p.drawRect(
                QtCore.QRect(left_rect.x() + x0, left_rect.y() + y0, x1 - x0, y1 - y0)
            )
            p.drawRect(
                QtCore.QRect(right_rect.x() + x0, right_rect.y() + y0, x1 - x0, y1 - y0)
            )

        # (Removed) filename label overlay

        p.end()

    # ---------- events ----------

    def mouseMoveEvent(self, evt: QtGui.QMouseEvent) -> None:  # noqa: N802
        pos = evt.pos()

        # View panning (hand tool)
        if (
            self.pan_mode
            and not self.crop_mode
            and self._view_panning
            and self._pan_last is not None
        ):
            dx = pos.x() - self._pan_last.x()
            dy = pos.y() - self._pan_last.y()
            self.view_pan_xp -= dx / (self.ds if self.ds else 1.0)
            self.view_pan_yp -= dy / (self.ds if self.ds else 1.0)
            self._pan_last = pos
            self.update()

        # Hover cell (base panel only)
        if self.left_rect.contains(pos):
            step_draw = max(1, int(round(self.grid_step * self.ds)))
            px = pos.x() - self.left_rect.x()
            py = pos.y() - self.left_rect.y()
            gx0 = (px // step_draw) * step_draw
            gy0 = (py // step_draw) * step_draw
            gx1 = min(gx0 + step_draw, self.tw - 1)
            gy1 = min(gy0 + step_draw, self.th - 1)
            self.hover_cell = (int(gx0), int(gy0), int(gx1), int(gy1))
        else:
            self.hover_cell = None

        # Affine drag pan on right (hand tool OFF)
        if (
            self.dragging
            and self.drag_last is not None
            and self.have_files()
            and not self.crop_mode
            and not self.perspective_mode
            and not self.pan_mode
        ):
            dx_draw = pos.x() - self.drag_last.x()
            dy_draw = pos.y() - self.drag_last.y()
            dx_prev = dx_draw / self.ds if self.ds else 0.0
            dy_prev = dy_draw / self.ds if self.ds else 0.0
            path = self.current_path()
            if path:
                # push once at the start of drag
                if self.drag_last == self._drag_start_point:
                    self._push_history(path)
                pr = self.params[path]
                pr["tx"] = float(pr.get("tx", 0.0)) + dx_prev  # type: ignore[index]
                pr["ty"] = float(pr.get("ty", 0.0)) + dy_prev  # type: ignore[index]
            self.drag_last = pos
            self.update()

        # Crop rubber band
        if self.crop_mode and self.crop_origin is not None:
            rect = QtCore.QRect(self.crop_origin, pos).normalized()
            rect = rect.intersected(self.left_rect)
            self.rubber.setGeometry(rect)

        self.update()

    def mousePressEvent(self, evt: QtGui.QMouseEvent) -> None:  # noqa: N802
        pos = evt.pos()

        # Begin global view pan (hand tool)
        if (
            evt.button() == QtCore.Qt.LeftButton
            and self.pan_mode
            and not self.crop_mode
        ):
            self._view_panning = True
            self._pan_last = pos
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            return

        # Begin affine pan on right (affine only, hand tool off)
        if (
            evt.button() == QtCore.Qt.LeftButton
            and self.right_rect.contains(pos)
            and not self.crop_mode
            and self.have_files()
            and not self.perspective_mode
            and not self.pan_mode
        ):
            self.dragging = True
            self.drag_last = pos
            self._drag_start_point = pos
            self.setCursor(QtCore.Qt.ClosedHandCursor)

        # Begin crop on left
        if (
            evt.button() == QtCore.Qt.LeftButton
            and self.crop_mode
            and self.left_rect.contains(pos)
        ):
            self.crop_origin = pos
            self.rubber.setGeometry(QtCore.QRect(pos, QtCore.QSize()))
            self.rubber.show()

    def mouseReleaseEvent(self, evt: QtGui.QMouseEvent) -> None:  # noqa: N802
        if evt.button() == QtCore.Qt.LeftButton and self._view_panning:
            self._view_panning = False
            self._pan_last = None
            self.setCursor(
                QtCore.Qt.OpenHandCursor if self.pan_mode else QtCore.Qt.ArrowCursor
            )

        if evt.button() == QtCore.Qt.LeftButton and self.dragging:
            self.dragging = False
            self.drag_last = None
            self.setCursor(
                QtCore.Qt.OpenHandCursor if self.pan_mode else QtCore.Qt.ArrowCursor
            )

        # Finish crop
        if (
            evt.button() == QtCore.Qt.LeftButton
            and self.crop_mode
            and self.rubber.isVisible()
        ):
            self.rubber.hide()
            rect = self.rubber.geometry()
            if rect.width() > 2 and rect.height() > 2:
                self.crop_rect_px = rect
                self._confirm_crop_all()
            self.crop_mode = False
            self.crop_origin = None
            self.update()

    # ---------- key handling ----------

    def keyPressEvent(self, evt: QtGui.QKeyEvent) -> None:  # noqa: N802
        path = self.current_path()
        key = evt.key()

        if key == QtCore.Qt.Key_G:
            self.grid_on = not self.grid_on
            self.update()
            return

        # Toggle hand tool with H
        if key == QtCore.Qt.Key_H:
            self.set_pan_mode(not self.pan_mode)
            return

        if path is None:
            return

        p = self.params[path]

        # Corner select (perspective)
        if key in (QtCore.Qt.Key_1, QtCore.Qt.Key_2, QtCore.Qt.Key_3, QtCore.Qt.Key_4):
            self.set_active_corner(
                {
                    QtCore.Qt.Key_1: 0,
                    QtCore.Qt.Key_2: 1,
                    QtCore.Qt.Key_3: 2,
                    QtCore.Qt.Key_4: 3,
                }[key]
            )
            ensure_perspective_quad(p, self.pw, self.ph)
            self.update()
            return

        # Toggle modes
        if key == QtCore.Qt.Key_P:
            self.set_perspective_mode(not self.perspective_mode)
            return

        # Crop
        if key == QtCore.Qt.Key_C:
            # keep previous user choice; if first time will ask inside
            self.start_crop_mode(None)
            return

        # Affine vs Perspective controls
        if not self.perspective_mode:
            # Move (Arrows/WASD)
            if key in (QtCore.Qt.Key_Left, QtCore.Qt.Key_A):
                self.move_dxdy(-self.step, 0)
            elif key in (QtCore.Qt.Key_Right, QtCore.Qt.Key_D):
                self.move_dxdy(+self.step, 0)
            elif key in (QtCore.Qt.Key_Up, QtCore.Qt.Key_W):
                self.move_dxdy(0, -self.step)
            elif key in (QtCore.Qt.Key_Down, QtCore.Qt.Key_S):
                self.move_dxdy(0, +self.step)

            # Rotate
            elif key == QtCore.Qt.Key_BracketLeft:
                self.rotate_deg(-self.rot_step)
            elif key == QtCore.Qt.Key_BracketRight:
                self.rotate_deg(+self.rot_step)

            # Zoom (image-local)
            elif key == QtCore.Qt.Key_Comma:
                self.zoom_factor(1.0 - self.scale_step)
            elif key == QtCore.Qt.Key_Period:
                self.zoom_factor(1.0 + self.scale_step)
            elif key == QtCore.Qt.Key_Z:
                self.zoom_factor(1.0 - self.micro_scale_step)
            elif key == QtCore.Qt.Key_X:
                self.zoom_factor(1.0 + self.micro_scale_step)

            # Step
            elif key == QtCore.Qt.Key_Equal:
                self.step = min(50.0, self.step + 1.0)
            elif key == QtCore.Qt.Key_Minus:
                self.step = max(0.5, self.step - 0.5)

            # Toggles
            elif key == QtCore.Qt.Key_O:
                self.overlay_mode = not self.overlay_mode
            elif key == QtCore.Qt.Key_B:
                self.show_outline = not self.show_outline

            # Reset
            elif key == QtCore.Qt.Key_0:
                self.reset_current()

            # Save
            elif key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_S):
                self.save_current_aligned()

        else:
            # Perspective mode: nudge active corner with arrows
            dx = dy = 0.0
            if key in (QtCore.Qt.Key_Left, QtCore.Qt.Key_A):
                dx = -self.persp_step
            elif key in (QtCore.Qt.Key_Right, QtCore.Qt.Key_D):
                dx = self.persp_step
            elif key in (QtCore.Qt.Key_Up, QtCore.Qt.Key_W):
                dy = -self.persp_step
            elif key in (QtCore.Qt.Key_Down, QtCore.Qt.Key_S):
                dy = self.persp_step
            if dx or dy:
                self.nudge_corner(dx, dy)

            # Save
            if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_S):
                self.save_current_aligned()

        self.update()

    # ---------- save / crop ----------

    def save_current_aligned(self) -> None:
        if not (self.align_out and self.base_full is not None):
            QtWidgets.QMessageBox.warning(
                self, "Missing path", "Please set Align Out folder in the toolbar."
            )
            return
        self.align_out.mkdir(parents=True, exist_ok=True)
        path = self.current_path()
        if not path:
            return
        img_full = load_image_bgr(str(path))
        bw, bh = self.base_full.shape[1], self.base_full.shape[0]

        if self.perspective_mode:
            p = self.params[path]
            ensure_perspective_quad(p, self.pw, self.ph)
            out = perspective_warp_full(
                img_full=img_full,
                base_w=bw,
                base_h=bh,
                dest_quad_prev=p["persp"],  # type: ignore[index]
                preview_scale=self.s,
            )
        else:
            mov_prev = self._get_preview(path)
            p = self.params[path]
            m_small = affine_params_to_small(mov_prev, p)  # type: ignore[arg-type]
            m_full = affine_lift_small_to_full(self.s, m_small)
            out = cv2.warpAffine(
                img_full,
                m_full,
                (bw, bh),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0),
            )

        out_path = self.align_out / f"{path.stem}.png"
        cv2.imwrite(str(out_path), out)
        QtWidgets.QMessageBox.information(self, "Saved", f"Aligned -> {out_path}")

    def start_crop_mode(self, use_aligned: Optional[bool]) -> None:
        """Enter crop mode; if use_aligned is None, ask the user."""
        if self.base_full is None:
            return
        if not self.crop_out:
            QtWidgets.QMessageBox.warning(
                self, "Missing path", "Please set Crops Out folder in the toolbar."
            )
            return

        if use_aligned is None:
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("Crop which images?")
            box.setText(
                "Choose which images to crop with the rectangle drawn on the Base:"
            )
            btn_aligned = box.addButton(
                "Aligned images", QtWidgets.QMessageBox.AcceptRole
            )
            btn_source = box.addButton(
                "Original source images", QtWidgets.QMessageBox.ActionRole
            )
            box.addButton(QtWidgets.QMessageBox.Cancel)
            box.exec_()
            clicked = box.clickedButton()
            if clicked == btn_aligned:
                self.crop_from_aligned = True
            elif clicked == btn_source:
                self.crop_from_aligned = False
            else:
                return
        else:
            self.crop_from_aligned = bool(use_aligned)

        self.crop_mode = True
        self.crop_origin = None
        self.rubber.hide()
        QtWidgets.QMessageBox.information(
            self,
            "Crop",
            "Drag a rectangle on the BASE (left) panel.\nRelease mouse to confirm.",
        )

    def _confirm_crop_all(self) -> None:
        """Crop base + selected (aligned or source) with a progress callback."""
        if not self.crop_rect_px or self.base_full is None or not self.crop_out:
            return

        rect = self.crop_rect_px
        # pos relative to left panel
        xw = rect.x() - self.left_rect.x()
        yw = rect.y() - self.left_rect.y()
        ww = rect.width()
        hw = rect.height()

        if self.ds == 0:
            return
        # draw -> preview
        xp = xw / self.ds
        yp = yw / self.ds
        wp = ww / self.ds
        hp_ = hw / self.ds

        # preview -> full
        cx = int(round(xp / self.s))
        cy = int(round(yp / self.s))
        cw = int(round(wp / self.s))
        ch = int(round(hp_ / self.s))

        bw, bh = self.base_full.shape[1], self.base_full.shape[0]
        cx = max(0, min(cx, bw - 2))
        cy = max(0, min(cy, bh - 2))
        cw = max(2, min(cw, bw - cx))
        ch = max(2, min(ch, bh - cy))

        self.crop_out.mkdir(parents=True, exist_ok=True)

        # Base crop
        base_crop = self.base_full[cy : cy + ch, cx : cx + cw]
        cv2.imwrite(str((self.crop_out / f"{self.base_path.stem}.png")), base_crop)

        # Decide list
        if self.crop_from_aligned:
            file_list = list(self.align_out.glob("*.png")) if self.align_out else []
        else:
            file_list = self.files

        total = len(file_list)
        done = 0

        # Notify external UI if available (AlignCanvas overrides)
        notify = getattr(self, "_emit_crop_progress", None)

        for pth in file_list:
            if self.crop_from_aligned:
                img = cv2.imread(str(pth), cv2.IMREAD_COLOR)
                if img is None:
                    done += 1
                    if notify:
                        notify(done, total)
                    continue
                out_name = pth.name
            else:
                img = load_image_bgr(str(pth))
                out_name = f"{pth.stem}.png"

            crop = img[cy : cy + ch, cx : cx + cw]
            cv2.imwrite(str(self.crop_out / out_name), crop)

            done += 1
            if notify:
                notify(done, total)

        if notify:
            notify(total, total)

        QtWidgets.QMessageBox.information(
            self,
            "Cropped",
            f"Cropped {'aligned' if self.crop_from_aligned else 'source'} images -> {self.crop_out}",
        )
