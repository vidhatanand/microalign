from __future__ import annotations

from typing import Optional, Tuple

# pylint: disable=no-member
import cv2  # type: ignore
from PyQt5 import QtCore, QtGui  # pylint: disable=no-name-in-module

from align_app.utils.img_io import bgr_to_qimage, clamp
from .canvas_affine import affine_params_to_small, affine_compose_preview
from .canvas_perspective import (
    ensure_perspective_quad,
    perspective_with_affine_compose_preview,
)


class CanvasViewMixin:
    """Painting, draw scale, view zoom/pan, and grid overlay."""

    def _init_view(self) -> None:
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

        # Hover cell
        self.hover_cell: Optional[Tuple[int, int, int, int]] = None

        # Cached rects for hit-testing in widget coords
        self.left_rect = QtCore.QRect()
        self.right_rect = QtCore.QRect()

        # Drag state for affine move
        self.dragging = False
        self._drag_start_point: Optional[QtCore.QPoint] = None
        self.drag_last: Optional[QtCore.QPoint] = None

    def _compute_draw_scale(self) -> None:
        """Compute ds, tw, th so both panels fit plus user zoom."""
        if not self.have_base():
            self.ds = 1.0
            self.tw = self.th = 0
            return
        avail_w = max(1, self.width())
        avail_h = max(1, self.height())
        need_w = self.pw * 2 + 8  # gap is 8
        need_h = self.ph
        sx = avail_w / float(need_w)
        sy = avail_h / float(need_h)
        base_fit = min(sx, sy, 1.0)
        vz = clamp(self.view_zoom, 0.25, 5.0)
        self.ds = base_fit * vz
        self.tw = int(round(self.pw * self.ds))
        self.th = int(round(self.ph * self.ds))

    def set_pan_mode(self, enabled: bool) -> None:
        self.pan_mode = bool(enabled)
        if self.pan_mode:
            self.setCursor(QtCore.Qt.OpenHandCursor)
        else:
            self._view_panning = False
            self._pan_last = None
            self.setCursor(QtCore.Qt.ArrowCursor)
        self.update()

    # ---- painting ----
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

        # Compute view pan offsets in DRAW pixels (images move; frame stays fixed)
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

                # Always compute affine (may be identity)
                m_small = affine_params_to_small(mov_prev, params)  # type: ignore[arg-type]

                # Use combined affine+perspective ONLY when quad is non-default
                use_persp = (
                    "persp" in params
                    and isinstance(params["persp"], list)
                    and not self._is_default_quad(params["persp"])
                )

                if use_persp:
                    ensure_perspective_quad(params, self.pw, self.ph)
                    right_bgr = perspective_with_affine_compose_preview(
                        base_prev=self.base_prev,
                        mov_prev=mov_prev,
                        dest_quad=params["persp"],  # type: ignore[index]
                        m_small=m_small,
                        overlay=self.overlay_mode,
                        alpha=self.alpha,
                        outline=self.show_outline,
                    )
                else:
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

        # Panel rects (apply pan offset to IMAGES)
        gap = 8
        self.left_rect = QtCore.QRect(-ox, -oy, self.tw, self.th)
        self.right_rect = QtCore.QRect(self.tw + gap - ox, -oy, self.tw, self.th)

        p.drawPixmap(self.left_rect, left_img)
        if right_img is not None:
            p.drawPixmap(self.right_rect, right_img)
        else:
            p.fillRect(self.right_rect, QtGui.QColor(40, 40, 40))
            p.setPen(QtGui.QColor(200, 200, 200))
            p.drawText(
                self.right_rect, QtCore.Qt.AlignCenter, "Pick a Source directory"
            )

        # Grid
        if self.grid_on:
            step_draw = max(1, int(round(self.grid_step * self.ds)))
            pen = QtGui.QPen(QtGui.QColor(128, 128, 128), 1, QtCore.Qt.SolidLine)
            p.setPen(pen)

            # lock grid to content (so it pans with images)
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

            draw_grid(self.left_rect)
            draw_grid(self.right_rect)

        # Hover-linked grid highlight
        if self.grid_on and self.hover_cell is not None:
            x0, y0, x1, y1 = self.hover_cell
            hp = QtGui.QPen(QtGui.QColor(255, 255, 0), 2, QtCore.Qt.SolidLine)
            p.setPen(hp)
            p.drawRect(
                QtCore.QRect(
                    self.left_rect.x() + x0, self.left_rect.y() + y0, x1 - x0, y1 - y0
                )
            )
            p.drawRect(
                QtCore.QRect(
                    self.right_rect.x() + x0, self.right_rect.y() + y0, x1 - x0, y1 - y0
                )
            )

        p.end()
