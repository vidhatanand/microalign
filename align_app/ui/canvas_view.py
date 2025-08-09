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
    """Painting, draw scale (fit), independent view zoom/pan, and grid overlay.

    Frames (left/right panels) remain FIXED to the toolbar-sized fit.
    The images inside those frames zoom/pan coherently (top-left anchored).
    """

    def _init_view(self) -> None:
        # Fit scale (frame size) + independent user zoom of content
        self.ds: float = 1.0  # fit scale for the frame
        self.view_zoom: float = 1.0  # user zoom for content
        self.scale_draw: float = 1.0  # effective content scale = ds * view_zoom
        self.tw: int = 0  # frame width in draw px
        self.th: int = 0  # frame height in draw px

        # View panning (shared across both panels), expressed in PREVIEW pixels
        self.pan_mode: bool = False
        self.view_pan_xp: float = 0.0
        self.view_pan_yp: float = 0.0
        self._view_panning: bool = False
        self._pan_last: Optional[QtCore.QPoint] = None

        # Hover cell
        self.hover_cell: Optional[Tuple[int, int, int, int]] = None

        # Rects: frames (fixed) + content-rects (image placement)
        self.left_rect = QtCore.QRect()  # frame rect (left panel)
        self.right_rect = QtCore.QRect()  # frame rect (right panel)

        # Drag state for affine move
        self.dragging = False
        self._drag_start_point: Optional[QtCore.QPoint] = None
        self.drag_last: Optional[QtCore.QPoint] = None

    def _compute_draw_scale(self) -> None:
        """Compute frame fit scale ds, frame size (tw, th), and content scale."""
        if not self.have_base():
            self.ds = 1.0
            self.scale_draw = 1.0
            self.tw = self.th = 0
            return

        avail_w = max(1, self.width())
        avail_h = max(1, self.height())
        need_w = self.pw * 2 + 8  # two panels + gap
        need_h = self.ph
        sx = avail_w / float(need_w)
        sy = avail_h / float(need_h)
        base_fit = min(sx, sy, 1.0)

        # Frame size is based ONLY on base_fit (fixed when zooming)
        self.ds = base_fit
        self.tw = int(round(self.pw * self.ds))
        self.th = int(round(self.ph * self.ds))

        # Actual content scale = frame fit * user zoom
        vz = clamp(self.view_zoom, 0.25, 5.0)
        self.scale_draw = self.ds * vz

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

        # Frames are fixed to fit; content (images) zoom/pan within them.
        gap = 8
        frame_left = QtCore.QRect(0, 0, self.tw, self.th)
        frame_right = QtCore.QRect(self.tw + gap, 0, self.tw, self.th)
        self.left_rect = frame_left
        self.right_rect = frame_right

        # Pan offsets in DRAW pixels (content shift), top-left anchored
        ox = int(round(self.view_pan_xp * self.scale_draw))
        oy = int(round(self.view_pan_yp * self.scale_draw))

        # Prepare scaled images (content size in draw pixels)
        w_img = int(round(self.pw * self.scale_draw))
        h_img = int(round(self.ph * self.scale_draw))

        # Base (left content)
        left_bgr = self.base_prev.copy() if self.base_prev is not None else None
        if left_bgr is None:
            p.end()
            return
        if w_img > 0 and h_img > 0:
            left_bgr = cv2.resize(
                left_bgr, (w_img, h_img), interpolation=cv2.INTER_AREA
            )
        left_pix = QtGui.QPixmap.fromImage(bgr_to_qimage(left_bgr))

        # Moving (right content)
        right_pix = None
        if self.have_files():
            path = self.current_path()
            mov_prev = self._get_preview(path) if path else None
            if mov_prev is not None:
                params = self.params[path]  # type: ignore[index]
                m_small = affine_params_to_small(mov_prev, params)  # type: ignore[arg-type]

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

                if w_img > 0 and h_img > 0:
                    right_bgr = cv2.resize(
                        right_bgr, (w_img, h_img), interpolation=cv2.INTER_AREA
                    )
                right_pix = QtGui.QPixmap.fromImage(bgr_to_qimage(right_bgr))

        # Content origins (top-left of the scaled images) inside the widget
        left_img_pos = QtCore.QPoint(frame_left.x() - ox, frame_left.y() - oy)
        right_img_pos = QtCore.QPoint(frame_right.x() - ox, frame_right.y() - oy)

        # Draw with clipping to keep images inside frames
        p.save()
        p.setClipRect(frame_left)
        p.drawPixmap(left_img_pos, left_pix)
        p.restore()

        p.save()
        p.setClipRect(frame_right)
        if right_pix is not None:
            p.drawPixmap(right_img_pos, right_pix)
        else:
            p.fillRect(frame_right, QtGui.QColor(40, 40, 40))
            p.setPen(QtGui.QColor(200, 200, 200))
            p.drawText(frame_right, QtCore.Qt.AlignCenter, "Pick a Source directory")
        p.restore()

        # Grid (pans/zooms with content)
        if self.grid_on:
            step_draw = max(1, int(round(self.grid_step * self.scale_draw)))
            pen = QtGui.QPen(QtGui.QColor(128, 128, 128), 1, QtCore.Qt.SolidLine)
            p.setPen(pen)

            def draw_grid(frame: QtCore.QRect, origin: QtCore.QPoint) -> None:
                # origin = where the (0,0) of the preview sits in draw pixels
                phase_x = (-origin.x()) % step_draw
                phase_y = (-origin.y()) % step_draw
                x = frame.left() + phase_x
                while x <= frame.right():
                    p.drawLine(x, frame.top(), x, frame.bottom())
                    x += step_draw
                y = frame.top() + phase_y
                while y <= frame.bottom():
                    p.drawLine(frame.left(), y, frame.right(), y)
                    y += step_draw

            draw_grid(frame_left, left_img_pos)
            draw_grid(frame_right, right_img_pos)

        # Hover-linked grid highlight (draw-space rects relative to frames)
        if self.grid_on and self.hover_cell is not None:
            x0, y0, x1, y1 = self.hover_cell
            hp = QtGui.QPen(QtGui.QColor(255, 255, 0), 2, QtCore.Qt.SolidLine)
            p.setPen(hp)
            p.drawRect(
                QtCore.QRect(frame_left.x() + x0, frame_left.y() + y0, x1 - x0, y1 - y0)
            )
            p.drawRect(
                QtCore.QRect(
                    frame_right.x() + x0, frame_right.y() + y0, x1 - x0, y1 - y0
                )
            )

        p.end()
