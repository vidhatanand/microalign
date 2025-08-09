from __future__ import annotations

from PyQt5 import QtCore, QtGui  # pylint: disable=no-name-in-module
from .canvas_perspective import ensure_perspective_quad


class CanvasInteractMixin:
    """Mouse & keyboard interactions."""

    def _init_interact(self) -> None:
        # attrs provided by CanvasViewMixin; ensure they exist for linters
        self.view_pan_xp = getattr(self, "view_pan_xp", 0.0)  # type: ignore[attr-defined]
        self.view_pan_yp = getattr(self, "view_pan_yp", 0.0)  # type: ignore[attr-defined]
        # Perspective drag state
        self._persp_dragging: bool = False
        self._persp_last: QtCore.QPoint | None = None
        self._persp_start_point: QtCore.QPoint | None = None

    # ---- events ----
    def mouseMoveEvent(self, evt: QtGui.QMouseEvent) -> None:  # noqa: N802
        pos = evt.pos()

        # View panning (hand tool) => shift image content inside fixed frames
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

        # Perspective drag (right panel)
        if (
            self.perspective_editing
            and self._persp_dragging
            and self._persp_last is not None
        ):
            dx_draw = pos.x() - self._persp_last.x()
            dy_draw = pos.y() - self._persp_last.y()
            dx_prev = dx_draw / self.ds if self.ds else 0.0
            dy_prev = dy_draw / self.ds if self.ds else 0.0
            path = self.current_path()
            if path:
                if self._persp_last == self._persp_start_point:
                    # first motion -> history snapshot
                    self._push_history(path)
                p = self.params[path]
                ensure_perspective_quad(p, self.pw, self.ph)
                quad = p["persp"]  # type: ignore[index]
                x, y = quad[self.active_corner]
                quad[self.active_corner] = (x + dx_prev, y + dy_prev)
                p["persp"] = quad  # type: ignore[index]
            self._persp_last = pos
            self.update()
            return

        # Hover cell (base panel only) – align with grid phase (locked to content)
        if self.left_rect.contains(pos):
            step_draw = max(1, int(round(self.grid_step * self.ds)))
            px = pos.x() - self.left_rect.x()
            py = pos.y() - self.left_rect.y()
            # grid phase due to view pan
            ox = int(round(self.view_pan_xp * self.ds))
            oy = int(round(self.view_pan_yp * self.ds))
            phase_x = (-ox) % step_draw
            phase_y = (-oy) % step_draw
            gx0 = ((px - phase_x) // step_draw) * step_draw + phase_x
            gy0 = ((py - phase_y) // step_draw) * step_draw + phase_y
            gx1 = min(gx0 + step_draw, self.tw - 1)
            gy1 = min(gy0 + step_draw, self.th - 1)
            self.hover_cell = (int(gx0), int(gy0), int(gx1), int(gy1))
        else:
            self.hover_cell = None

        # Affine drag pan on right when hand tool is OFF
        if (
            self.dragging
            and self.drag_last is not None
            and self.have_files()
            and not self.crop_mode
            and not self.perspective_editing
            and not self.pan_mode
        ):
            dx_draw = pos.x() - self.drag_last.x()
            dy_draw = pos.y() - self.drag_last.y()
            dx_prev = dx_draw / self.ds if self.ds else 0.0
            dy_prev = dy_draw / self.ds if self.ds else 0.0
            path = self.current_path()
            if path:
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
            and not self.perspective_editing
            and not self.pan_mode
        ):
            self.dragging = True
            self.drag_last = pos
            self._drag_start_point = pos
            self.setCursor(QtCore.Qt.ClosedHandCursor)

        # Begin perspective drag on right (choose nearest corner)
        if (
            evt.button() == QtCore.Qt.LeftButton
            and self.perspective_editing
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
                # adjust for view pan & zoom
                ox = int(round(self.view_pan_xp * self.ds))
                oy = int(round(self.view_pan_yp * self.ds))
                mx += ox
                my += oy
                best_i = None
                best_d2 = None
                for i, (qx, qy) in enumerate(quad):
                    dx = mx - qx * self.ds
                    dy = my - qy * self.ds
                    d2 = dx * dx + dy * dy
                    if best_d2 is None or d2 < best_d2:
                        best_d2 = d2
                        best_i = i
                # 16px pick radius (in draw pixels)
                if best_d2 is not None and best_d2 <= 16 * 16:
                    self.set_active_corner(int(best_i))
                    self._persp_dragging = True
                    self._persp_last = pos
                    self._persp_start_point = pos
                    self.setCursor(QtCore.Qt.ClosedHandCursor)
                    return

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

        if evt.button() == QtCore.Qt.LeftButton and self._persp_dragging:
            self._persp_dragging = False
            self._persp_last = None
            self._persp_start_point = None
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

    # ---- key handling ----
    def keyPressEvent(self, evt: QtGui.QKeyEvent) -> None:  # noqa: N802
        path = self.current_path()
        key = evt.key()

        # grid toggle
        if key == QtCore.Qt.Key_G:
            self.grid_on = not self.grid_on
            self.update()
            return

        # toggle hand tool with H
        if key == QtCore.Qt.Key_H:
            self.set_pan_mode(not self.pan_mode)
            return

        if path is None:
            return

        if key == QtCore.Qt.Key_P:
            self.set_perspective_editing(not self.perspective_editing)
            return

        if key == QtCore.Qt.Key_C:
            self.start_crop_mode(None)
            return

        # Corner select (1..4) while in perspective
        if self.perspective_editing and key in (
            QtCore.Qt.Key_1,
            QtCore.Qt.Key_2,
            QtCore.Qt.Key_3,
            QtCore.Qt.Key_4,
        ):
            self.set_active_corner(
                {
                    QtCore.Qt.Key_1: 0,
                    QtCore.Qt.Key_2: 1,
                    QtCore.Qt.Key_3: 2,
                    QtCore.Qt.Key_4: 3,
                }[key]
            )
            self.update()
            return

        if not self.perspective_editing:
            if key in (QtCore.Qt.Key_Left, QtCore.Qt.Key_A):
                self.move_dxdy(-self.step, 0)
            elif key in (QtCore.Qt.Key_Right, QtCore.Qt.Key_D):
                self.move_dxdy(+self.step, 0)
            elif key in (QtCore.Qt.Key_Up, QtCore.Qt.Key_W):
                self.move_dxdy(0, -self.step)
            elif key in (QtCore.Qt.Key_Down, QtCore.Qt.Key_S):
                self.move_dxdy(0, +self.step)

            elif key == QtCore.Qt.Key_BracketLeft:
                self.rotate_deg(-self.rot_step)
            elif key == QtCore.Qt.Key_BracketRight:
                self.rotate_deg(+self.rot_step)

            elif key == QtCore.Qt.Key_Comma:
                self.zoom_factor(1.0 - self.scale_step)
            elif key == QtCore.Qt.Key_Period:
                self.zoom_factor(1.0 + self.scale_step)
            elif key == QtCore.Qt.Key_Z:
                self.zoom_factor(1.0 - self.micro_scale_step)
            elif key == QtCore.Qt.Key_X:
                self.zoom_factor(1.0 + self.micro_scale_step)

            elif key == QtCore.Qt.Key_Equal:
                self.step = min(50.0, self.step + 1.0)
            elif key == QtCore.Qt.Key_Minus:
                self.step = max(0.5, self.step - 0.5)

            elif key == QtCore.Qt.Key_O:
                self.overlay_mode = not self.overlay_mode
            elif key == QtCore.Qt.Key_B:
                self.show_outline = not self.show_outline

            elif key == QtCore.Qt.Key_0:
                self.reset_current()

            elif key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_S):
                self.save_current_aligned()

        else:
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

            if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_S):
                self.save_current_aligned()
