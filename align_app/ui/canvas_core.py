"""Core canvas implementation: drawing, events, affine/perspective/crop plumbing."""

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

        # Viewport pan for zoomed-in view (PREVIEW px)
        self.view_pan = QtCore.QPointF(0.0, 0.0)
        self.hand_pan_mode = False
        self._pan_drag_last: Optional[QtCore.QPoint] = None

        # Per-image params
        self.params: Dict[Path, Dict[str, object]] = {}
        self.idx: int = 0

        # UI state
        self.alpha = 0.5
        self.step = 1.0
        self.rot_step = 0.10
        self.scale_step = 0.005
        self.micro_scale_step = 0.001
        self.persp_step = 1.0
        self.grid_on = True
        self.grid_step = 40
        self.overlay_mode = False
        self.show_outline = True

        # Modes
        self.perspective_mode = False
        self.active_corner = 0  # 0..3

        # Hover/drag
        self.hover_cell: Optional[Tuple[int, int, int, int]] = None
        self.dragging = False
        self.drag_last: Optional[QtCore.QPoint] = None

        # Perspective drag
        self.persp_dragging = False
        self._persp_last: Optional[QtCore.QPoint] = None

        # Crop
        self.crop_mode = False
        self.rubber = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
        self.crop_origin: Optional[QtCore.QPoint] = None
        self.crop_rect_px: Optional[QtCore.QRect] = None
        self.crop_from_aligned: bool = True

        # Cached rects for hit-testing
        self.left_rect = QtCore.QRect()
        self.right_rect = QtCore.QRect()

    # ---------- basic model ----------

    def have_base(self) -> bool:
        return self.base_prev is not None

    def have_files(self) -> bool:
        return bool(self.files)

    def current_path(self) -> Optional[Path]:
        if not self.files:
            return None
        return self.files[self.idx]

    # ---------- load paths ----------

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

        if self.src_dir and self.src_dir.is_dir():
            self.files = sorted(
                (
                    p
                    for p in self.src_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in SUPPORTED_LOWER
                ),
                key=lambda p: str(p).lower(),
            )
            self.params = {
                p: {"tx": 0.0, "ty": 0.0, "theta": 0.0, "scale": 1.0}
                for p in self.files
            }
            self.idx = 0
            self.cache_prev.clear()

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

    # ---------- navigation ----------

    def next_image(self) -> None:
        if self.files and self.idx < len(self.files) - 1:
            self.idx += 1
            self.update()

    def prev_image(self) -> None:
        if self.files and self.idx > 0:
            self.idx -= 1
            self.update()

    # ---------- draw scaling ----------

    def _compute_draw_scale(self) -> None:
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
        vz = clamp(self.view_zoom, 0.25, 5.0)
        self.ds = base_fit * vz
        self.tw = int(round(self.pw * self.ds))
        self.th = int(round(self.ph * self.ds))

    def _apply_pan_bounds(self) -> None:
        if self.tw <= 0 or self.th <= 0:
            self.view_pan = QtCore.QPointF(0.0, 0.0)
            return
        vis_w = max(1, min(self.tw, self.width() // 2 - self.gap // 2))
        vis_h = max(1, min(self.th, self.height()))
        max_x = max(0, self.tw - vis_w)
        max_y = max(0, self.th - vis_h)
        x = max(0.0, min(float(self.view_pan.x()), float(max_x)))
        y = max(0.0, min(float(self.view_pan.y()), float(max_y)))
        self.view_pan = QtCore.QPointF(x, y)

    # ---------- painting ----------

    def paintEvent(self, _evt: QtGui.QPaintEvent) -> None:  # noqa: N802
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(20, 20, 20))

        if not self.have_base():
            p.setPen(QtGui.QColor(220, 220, 220))
            p.drawText(
                self.rect(), QtCore.Qt.AlignCenter, "Create or open a Project to begin."
            )
            p.end()
            return

        self._compute_draw_scale()
        self._apply_pan_bounds()

        ox = int(round(self.view_pan.x()))
        oy = int(round(self.view_pan.y()))

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
            p.drawText(right_rect, QtCore.Qt.AlignCenter, "No source images")

        # Grid (pans with content)
        if self.grid_on:
            step_draw = max(1, int(round(self.grid_step * self.ds)))
            pen = QtGui.QPen(QtGui.QColor(128, 128, 128), 1, QtCore.Qt.SolidLine)
            p.setPen(pen)

            def draw_grid(rect: QtCore.QRect) -> None:
                phase_x = (-rect.x()) % step_draw
                phase_y = (-rect.y()) % step_draw
                x = rect.left() + phase_x
                while x <= rect.right():
                    p.drawLine(x, rect.top(), x, rect.bottom())
                    x += step_draw
                y = rect.top() + phase_y
                while y <= rect.bottom():
                    p.drawLine(rect.left(), y, rect.right(), y)
                    y += step_draw

            draw_grid(left_rect)
            draw_grid(right_rect)

        # Hover highlight (linked)
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

        p.end()

    # ---------- events ----------

    def mouseMoveEvent(self, evt: QtGui.QMouseEvent) -> None:  # noqa: N802
        pos = evt.pos()

        # Hand-pan
        if self.hand_pan_mode and self._pan_drag_last is not None:
            dx = pos.x() - self._pan_drag_last.x()
            dy = pos.y() - self._pan_drag_last.y()
            self.view_pan += QtCore.QPointF(
                -dx / (self.ds if self.ds else 1.0), -dy / (self.ds if self.ds else 1.0)
            )
            self._apply_pan_bounds()
            self._pan_drag_last = pos
            self.update()
            return

        # Perspective drag (right panel)
        if (
            self.perspective_mode
            and self.persp_dragging
            and self._persp_last is not None
        ):
            dx = (pos.x() - self._persp_last.x()) / (self.ds if self.ds else 1.0)
            dy = (pos.y() - self._persp_last.y()) / (self.ds if self.ds else 1.0)
            path = self.current_path()
            if path:
                p = self.params[path]
                ensure_perspective_quad(p, self.pw, self.ph)
                quad = p["persp"]  # type: ignore[index]
                x, y = quad[self.active_corner]
                quad[self.active_corner] = (x + dx, y + dy)
                p["persp"] = quad  # type: ignore[index]
            self._persp_last = pos
            self.update()
            return

        # Hover cell (left panel coords)
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

        # Affine drag (right, hand tool OFF)
        if (
            self.dragging
            and self.drag_last is not None
            and self.have_files()
            and not self.crop_mode
            and not self.perspective_mode
            and not self.hand_pan_mode
        ):
            dx_draw = pos.x() - self.drag_last.x()
            dy_draw = pos.y() - self.drag_last.y()
            dx_prev = dx_draw / (self.ds if self.ds else 1.0)
            dy_prev = dy_draw / (self.ds if self.ds else 1.0)
            path = self.current_path()
            if path:
                pr = self.params[path]
                pr["tx"] = float(pr.get("tx", 0.0)) + dx_prev  # type: ignore[index]
                pr["ty"] = float(pr.get("ty", 0.0)) + dy_prev  # type: ignore[index]
            self.drag_last = pos
            self.update()

        # Crop rubber
        if self.crop_mode and self.crop_origin is not None:
            rect = QtCore.QRect(self.crop_origin, pos).normalized()
            rect = rect.intersected(self.left_rect)
            self.rubber.setGeometry(rect)

        self.update()

    def mousePressEvent(self, evt: QtGui.QMouseEvent) -> None:  # noqa: N802
        pos = evt.pos()

        # Hand pan
        if evt.button() == QtCore.Qt.LeftButton and self.hand_pan_mode:
            self._pan_drag_last = pos
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            return

        # Perspective: start dragging nearest corner on RIGHT
        if (
            evt.button() == QtCore.Qt.LeftButton
            and self.perspective_mode
            and self.right_rect.contains(pos)
            and self.have_files()
        ):
            path = self.current_path()
            if path:
                p = self.params[path]
                ensure_perspective_quad(p, self.pw, self.ph)
                quad = p["persp"]  # type: ignore[index]
                mx = pos.x() - self.right_rect.x()
                my = pos.y() - self.right_rect.y()
                best_i = None
                best_d2 = None
                for i, (qx, qy) in enumerate(quad):
                    dx = mx - qx * self.ds
                    dy = my - qy * self.ds
                    d2 = dx * dx + dy * dy
                    if best_d2 is None or d2 < best_d2:
                        best_d2 = d2
                        best_i = i
                if best_d2 is not None and best_d2 <= 12 * 12:
                    self.active_corner = int(best_i)  # pick new active
                    # notify toolbar if it listens
                    ac = getattr(self, "activeCornerChanged", None)
                    if ac is not None and hasattr(ac, "emit"):
                        ac.emit(self.active_corner)
                    self.persp_dragging = True
                    self._persp_last = pos
                    self.setCursor(QtCore.Qt.ClosedHandCursor)
                    return

        # Affine drag on right (hand OFF)
        if (
            evt.button() == QtCore.Qt.LeftButton
            and self.right_rect.contains(pos)
            and not self.crop_mode
            and self.have_files()
            and not self.perspective_mode
        ):
            self.dragging = True
            self.drag_last = pos
            if not self.hand_pan_mode:
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
        if evt.button() == QtCore.Qt.LeftButton and self._pan_drag_last is not None:
            self._pan_drag_last = None
            if self.hand_pan_mode:
                self.setCursor(QtCore.Qt.OpenHandCursor)

        if evt.button() == QtCore.Qt.LeftButton and self.persp_dragging:
            self.persp_dragging = False
            self._persp_last = None
            self.setCursor(
                QtCore.Qt.OpenHandCursor
                if self.hand_pan_mode
                else QtCore.Qt.ArrowCursor
            )

        if evt.button() == QtCore.Qt.LeftButton and self.dragging:
            self.dragging = False
            self.drag_last = None
            if not self.hand_pan_mode:
                self.setCursor(QtCore.Qt.ArrowCursor)

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

        if path is None:
            return

        p = self.params[path]

        # Corner select (perspective)
        if key in (QtCore.Qt.Key_1, QtCore.Qt.Key_2, QtCore.Qt.Key_3, QtCore.Qt.Key_4):
            self.active_corner = {
                QtCore.Qt.Key_1: 0,
                QtCore.Qt.Key_2: 1,
                QtCore.Qt.Key_3: 2,
                QtCore.Qt.Key_4: 3,
            }[key]
            ac = getattr(self, "activeCornerChanged", None)
            if ac is not None and hasattr(ac, "emit"):
                ac.emit(self.active_corner)
            ensure_perspective_quad(p, self.pw, self.ph)
            self.update()
            return

        # Toggle modes (keyboard P)
        if key == QtCore.Qt.Key_P:
            new_state = not self.perspective_mode
            # try to notify external UI
            mm = getattr(self, "modeChanged", None)
            if mm is not None and hasattr(mm, "emit"):
                # delegate proper init via AlignCanvas.set_perspective_mode if present
                try:
                    # if subclass overrides
                    self.set_perspective_mode(new_state)  # type: ignore[attr-defined]
                    return
                except Exception:
                    pass
                mm.emit(new_state)
            self.perspective_mode = new_state
            self.update()
            return

        # Crop
        if key == QtCore.Qt.Key_C:
            self.start_crop_mode(None)  # provided by crop mixin (in AlignCanvas)
            return

        # Affine vs Perspective controls
        if not self.perspective_mode:
            if key in (QtCore.Qt.Key_Left, QtCore.Qt.Key_A):
                p["tx"] = float(p.get("tx", 0.0)) - self.step  # type: ignore[index]
            elif key in (QtCore.Qt.Key_Right, QtCore.Qt.Key_D):
                p["tx"] = float(p.get("tx", 0.0)) + self.step  # type: ignore[index]
            elif key in (QtCore.Qt.Key_Up, QtCore.Qt.Key_W):
                p["ty"] = float(p.get("ty", 0.0)) - self.step  # type: ignore[index]
            elif key in (QtCore.Qt.Key_Down, QtCore.Qt.Key_S):
                p["ty"] = float(p.get("ty", 0.0)) + self.step  # type: ignore[index]
            elif key == QtCore.Qt.Key_BracketLeft:
                p["theta"] = float(p.get("theta", 0.0)) - self.rot_step  # type: ignore[index]
            elif key == QtCore.Qt.Key_BracketRight:
                p["theta"] = float(p.get("theta", 0.0)) + self.rot_step  # type: ignore[index]
            elif key == QtCore.Qt.Key_Comma:
                p["scale"] = clamp(float(p.get("scale", 1.0)) * (1.0 - self.scale_step), 0.8, 1.2)  # type: ignore[index]
            elif key == QtCore.Qt.Key_Period:
                p["scale"] = clamp(float(p.get("scale", 1.0)) * (1.0 + self.scale_step), 0.8, 1.2)  # type: ignore[index]
            elif key == QtCore.Qt.Key_Z:
                p["scale"] = clamp(float(p.get("scale", 1.0)) * (1.0 - self.micro_scale_step), 0.8, 1.2)  # type: ignore[index]
            elif key == QtCore.Qt.Key_X:
                p["scale"] = clamp(float(p.get("scale", 1.0)) * (1.0 + self.micro_scale_step), 0.8, 1.2)  # type: ignore[index]
            elif key == QtCore.Qt.Key_Equal:
                self.step = min(50.0, self.step + 1.0)
            elif key == QtCore.Qt.Key_Minus:
                self.step = max(0.5, self.step - 0.5)
            elif key == QtCore.Qt.Key_O:
                self.overlay_mode = not self.overlay_mode
            elif key == QtCore.Qt.Key_B:
                self.show_outline = not self.show_outline
            elif key == QtCore.Qt.Key_0:
                p["tx"] = 0.0
                p["ty"] = 0.0
                p["theta"] = 0.0
                p["scale"] = 1.0  # type: ignore[index]
            elif key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_S):
                self.save_current_aligned()
        else:
            ensure_perspective_quad(p, self.pw, self.ph)
            quad = p["persp"]  # type: ignore[index]
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
                x, y = quad[self.active_corner]
                quad[self.active_corner] = (x + dx, y + dy)
                p["persp"] = quad  # type: ignore[index]
            if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_S):
                self.save_current_aligned()
        self.update()

    # ---------- CROP (pulled from mixin) ----------

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
        """Crop base + selected (aligned or source)."""
        if not self.crop_rect_px or self.base_full is None or not self.crop_out:
            return

        rect = self.crop_rect_px
        xw = rect.x() - self.left_rect.x()
        yw = rect.y() - self.left_rect.y()
        ww = rect.width()
        hw = rect.height()

        if self.ds == 0:
            return
        xp = xw / self.ds
        yp = yw / self.ds
        wp = ww / self.ds
        hp_ = hw / self.ds

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
        out_name_base = (
            f"{self.base_path.stem}.png" if self.base_path is not None else "base.png"
        )
        base_crop = self.base_full[cy : cy + ch, cx : cx + cw]
        cv2.imwrite(str((self.crop_out / out_name_base)), base_crop)

        # Decide list
        if self.crop_from_aligned:
            file_list = list(self.align_out.glob("*.png")) if self.align_out else []
        else:
            file_list = self.files

        total = len(file_list)
        done = 0
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
                from align_app.utils.img_io import load_image_bgr

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
