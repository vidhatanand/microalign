from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QRect, QPoint, QSize, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QColor, QPixmap
from PyQt5.QtWidgets import QWidget, QMessageBox, QRubberBand

from align_app.utils.img_io import (
    load_image_bgr,
    uniform_preview_scale,
    clamp,
    bgr_to_qimage,
    SUPPORTED_LOWER,
)


class AlignCanvas(QWidget):
    """Widget that renders base/current panels and handles manual alignment."""

    gap = 8  # gap between left/right panels in widget (draw space)

    # notify when the “current” moving image changes
    currentPathChanged = pyqtSignal(object)  # emits Path or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        # Paths
        self.base_path: Optional[Path] = None
        self.src_dir: Optional[Path] = None
        self.align_out: Optional[Path] = None
        self.crop_out: Optional[Path] = None

        # Images
        self.base_full: Optional[np.ndarray] = None
        self.base_prev: Optional[np.ndarray] = None
        self.files: List[Path] = []
        self.cache_prev: Dict[Path, np.ndarray] = {}

        # Preview sizing (canonical preview scale & size)
        self.s: float = 1.0  # preview scale relative to full-res
        self.pw: int = 0  # preview width (canonical)
        self.ph: int = 0  # preview height (canonical)

        # Draw sizing (dynamic per paint to fit the widget)
        self.ds: float = 1.0  # extra draw scale applied to preview
        self.tw: int = 0  # drawn panel width  = int(pw * ds)
        self.th: int = 0  # drawn panel height = int(ph * ds)

        # Per-image params (preview-space; i.e., before applying ds)
        # For each path -> dict:
        #   mode: 'affine' or 'persp'
        #   tx, ty, theta, scale   (affine)
        #   corners: Optional[np.ndarray shape (4,2) in preview coords] (persp)
        self.params: Dict[Path, Dict[str, object]] = {}
        self.idx: int = 0

        # UI state
        self.alpha = 0.5
        self.step = 1.0  # MOVE step (px in preview space)
        self.rot_step = 0.10  # degrees per tick
        self.scale_step = 0.005  # 0.5% zoom
        self.micro_scale_step = 0.001  # 0.1% zoom
        self.grid_on = True
        self.grid_step = 40  # in preview px
        self.overlay_mode = False
        self.show_outline = True

        # Perspective controls (preview space)
        self.corner_idx = 0  # 0..3 (tl,tr,br,bl)
        self.corner_step = 2.0
        self.corner_micro_step = 0.5

        # Hover & drag
        self.hover_cell: Optional[Tuple[int, int, int, int]] = None  # in DRAW coords
        self.dragging = False
        self.drag_last: Optional[QPoint] = None

        # Crop
        self.crop_mode = False
        self.rubber = QRubberBand(QRubberBand.Rectangle, self)
        self.crop_origin: Optional[QPoint] = None
        self.crop_rect_px: Optional[QRect] = None  # in WIDGET/DRAW coords on base
        self.crop_from_aligned: bool = True  # True = crop only aligned PNGs

        # Cached rects for hit-testing
        self.left_rect = QRect()
        self.right_rect = QRect()

    # ---- public API ----

    def set_paths(
        self,
        base_path: Optional[Path],
        src_dir: Optional[Path],
        align_out: Optional[Path],
        crop_out: Optional[Path],
        preview_max_side: int = 1600,
    ):
        """Set any subset of paths; load/reload when enough info is present."""
        if base_path is not None:
            self.base_path = base_path
        if src_dir is not None:
            self.src_dir = src_dir
        if align_out is not None:
            self.align_out = align_out
        if crop_out is not None:
            self.crop_out = crop_out

        # Load base if set
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

        # Collect files if dir set (RECURSIVE)
        if self.src_dir and self.src_dir.is_dir():
            self.files = sorted(
                (
                    p
                    for p in self.src_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in SUPPORTED_LOWER
                ),
                key=lambda p: str(p).lower(),
            )
            # reset params for new files (lazy-init corners when needed)
            self.params = {
                p: {
                    "mode": "affine",
                    "tx": 0.0,
                    "ty": 0.0,
                    "theta": 0.0,
                    "scale": 1.0,
                    "corners": None,
                }
                for p in self.files
            }
            self.idx = 0
            self.cache_prev.clear()

        # notify current file (may be None)
        self.currentPathChanged.emit(self.current_path())
        self.update()

    def prev_image(self):
        if not self.files:
            return
        if self.idx > 0:
            self.idx -= 1
            self.currentPathChanged.emit(self.current_path())
            self.update()

    def next_image(self):
        if not self.files:
            return
        if self.idx < len(self.files) - 1:
            self.idx += 1
            self.currentPathChanged.emit(self.current_path())
            self.update()

    def move_dxdy(self, dx: float, dy: float):
        """Toolbar nudges. In perspective mode, nudge selected corner; else translate."""
        path = self.current_path()
        if not path:
            return
        p = self.params[path]
        if p["mode"] == "persp":
            self._nudge_corner(dx, dy, micro=False)
        else:
            p["tx"] = float(p["tx"]) + dx
            p["ty"] = float(p["ty"]) + dy
        self.update()

    def rotate_deg(self, dtheta: float):
        path = self.current_path()
        if not path:
            return
        p = self.params[path]
        if p["mode"] == "persp":
            # ignore rotate in perspective mode (keeps things simple)
            return
        p["theta"] = float(p["theta"]) + dtheta
        self.update()

    def zoom_factor(self, mul: float):
        path = self.current_path()
        if not path:
            return
        p = self.params[path]
        if p["mode"] == "persp":
            # ignore zoom in perspective mode
            return
        p["scale"] = clamp(float(p["scale"]) * mul, 0.8, 1.2)
        self.update()

    def reset_current(self):
        path = self.current_path()
        if not path:
            return
        p = self.params[path]
        p["tx"] = p["ty"] = 0.0
        p["theta"] = 0.0
        p["scale"] = 1.0
        p["mode"] = "affine"
        p["corners"] = None
        self.update()

    def save_current_aligned(self):
        if not (self.align_out and self.base_full is not None):
            QMessageBox.warning(
                self, "Missing path", "Please set Align Out folder in the toolbar."
            )
            return
        self.align_out.mkdir(parents=True, exist_ok=True)
        path = self.current_path()
        if not path:
            return
        mov_prev = self._get_preview(path)
        p = self.params[path]
        img_full = load_image_bgr(str(path))
        bw, bh = self.base_full.shape[1], self.base_full.shape[0]

        if p["mode"] == "persp":
            H_small = self._params_to_homography_small(mov_prev, p)
            H_full = self._lift_homography_small_to_full(H_small)
            out = cv2.warpPerspective(
                img_full,
                H_full,
                (bw, bh),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0),
            )
        else:
            M_small = self._params_to_matrix_small(mov_prev, p)
            M_full = self._lift_small_to_full(M_small)
            out = cv2.warpAffine(
                img_full,
                M_full,
                (bw, bh),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0),
            )

        out_path = self.align_out / f"{path.stem}.png"
        cv2.imwrite(str(out_path), out)
        QMessageBox.information(self, "Saved", f"Aligned -> {out_path}")

    def start_crop_mode(self, use_aligned: Optional[bool] = None):
        """Begin crop rectangle interaction. If use_aligned is given,
        True => crop only aligned pngs, False => crop original sources."""
        if self.base_full is None:
            return
        if not self.crop_out:
            QMessageBox.warning(
                self, "Missing path", "Please set Crops Out folder in the toolbar."
            )
            return

        if use_aligned is not None:
            self.crop_from_aligned = bool(use_aligned)

        self.crop_mode = True
        self.crop_origin = None
        self.rubber.hide()
        QMessageBox.information(
            self,
            "Crop",
            "Drag a rectangle on the BASE (left) panel.\n" "Release mouse to confirm.",
        )

    # ---- internals ----

    def have_base(self) -> bool:
        return self.base_prev is not None

    def have_files(self) -> bool:
        return bool(self.files)

    def current_path(self) -> Optional[Path]:
        if not self.files:
            return None
        return self.files[self.idx]

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

    def _ensure_corners(self, mov_prev: np.ndarray, p: Dict[str, object]) -> np.ndarray:
        """Lazy init corners from current affine transform (preview space)."""
        if p.get("corners") is not None:
            return p["corners"]  # type: ignore[return-value]
        h, w = mov_prev.shape[:2]
        src = np.float32(
            [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]
        )  # tl,tr,br,bl
        M = self._params_to_matrix_small(mov_prev, p)
        M3 = np.vstack([M, [0, 0, 1]]).astype(np.float32)
        dst = cv2.perspectiveTransform(src.reshape(-1, 1, 2), M3).reshape(4, 2)
        p["corners"] = dst.astype(np.float32)
        return p["corners"]  # type: ignore[return-value]

    def _params_to_matrix_small(
        self, mov_prev: np.ndarray, p: Dict[str, object]
    ) -> np.ndarray:
        """2x3 affine (preview space)"""
        h, w = mov_prev.shape[:2]
        cx, cy = w / 2.0, h / 2.0
        theta = float(p["theta"])
        scale = float(p["scale"])
        tx = float(p["tx"])
        ty = float(p["ty"])
        M = cv2.getRotationMatrix2D((cx, cy), theta, scale)
        M[0, 2] += tx
        M[1, 2] += ty
        return M

    def _params_to_homography_small(
        self, mov_prev: np.ndarray, p: Dict[str, object]
    ) -> np.ndarray:
        """3x3 perspective H (preview space) using p['corners'] as dst"""
        h, w = mov_prev.shape[:2]
        src = np.float32(
            [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]
        )  # tl,tr,br,bl
        dst = self._ensure_corners(mov_prev, p).astype(np.float32)
        H = cv2.getPerspectiveTransform(src, dst)
        return H

    def _lift_small_to_full(self, M_small: np.ndarray) -> np.ndarray:
        # Lift preview-space affine to full-res affine
        A = np.eye(3, dtype=np.float32)
        A[:2, :3] = M_small
        S = np.diag([self.s, self.s, 1.0]).astype(np.float32)
        S_inv = np.diag([1.0 / self.s, 1.0 / self.s, 1.0]).astype(np.float32)
        W = S_inv @ A @ S
        return W[:2, :]

    def _lift_homography_small_to_full(self, H_small: np.ndarray) -> np.ndarray:
        # H_full = S^{-1} * H_small * S
        S = np.diag([self.s, self.s, 1.0]).astype(np.float32)
        S_inv = np.diag([1.0 / self.s, 1.0 / self.s, 1.0]).astype(np.float32)
        return S_inv @ H_small @ S

    def _compose_right_preview(
        self, mov_prev: np.ndarray, p: Dict[str, object]
    ) -> np.ndarray:
        """Return preview composite for right panel based on current mode."""
        if p["mode"] == "persp":
            H = self._params_to_homography_small(mov_prev, p)
            warped = cv2.warpPerspective(
                mov_prev,
                H,
                (self.pw, self.ph),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0),
            )
            comp = warped
            if self.overlay_mode and self.base_prev is not None:
                base = self.base_prev.copy()
                mask = (warped > 0).any(axis=2).astype(np.uint8) * 255
                mask3 = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                comp = np.where(
                    mask3 > 0,
                    cv2.addWeighted(base, 1 - self.alpha, warped, self.alpha, 0),
                    base,
                )

            if self.show_outline:
                h, w = mov_prev.shape[:2]
                src = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
                tc = (
                    cv2.perspectiveTransform(src.reshape(-1, 1, 2), H)
                    .astype(int)
                    .reshape(-1, 2)
                )
                cv2.polylines(comp, [tc], True, (0, 255, 255), 1, cv2.LINE_AA)
            return comp

        # affine path
        M_small = self._params_to_matrix_small(mov_prev, p)
        warped = cv2.warpAffine(
            mov_prev,
            M_small,
            (self.pw, self.ph),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )
        comp = warped
        if self.overlay_mode and self.base_prev is not None:
            base = self.base_prev.copy()
            mask = (warped > 0).any(axis=2).astype(np.uint8) * 255
            mask3 = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            comp = np.where(
                mask3 > 0,
                cv2.addWeighted(base, 1 - self.alpha, warped, self.alpha, 0),
                base,
            )

        if self.show_outline:
            h, w = mov_prev.shape[:2]
            corners = np.float32(
                [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]
            ).reshape(-1, 1, 2)
            M3 = np.vstack([M_small, [0, 0, 1]]).astype(np.float32)
            tc = cv2.perspectiveTransform(corners, M3).astype(int).reshape(-1, 2)
            cv2.polylines(comp, [tc], True, (0, 255, 255), 1, cv2.LINE_AA)
        return comp

    # ---- painting / events ----

    def sizeHint(self) -> QSize:
        return QSize(1200, 700)

    def _compute_draw_scale(self):
        """Compute self.ds, self.tw, self.th so both panels fit the widget."""
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
        self.ds = min(sx, sy, 1.0)  # never upscale beyond preview
        self.tw = int(round(self.pw * self.ds))
        self.th = int(round(self.ph * self.ds))

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(20, 20, 20))

        if not self.have_base():
            p.setPen(QColor(220, 220, 220))
            p.drawText(
                self.rect(), Qt.AlignCenter, "Pick a Base image from the toolbar."
            )
            p.end()
            return

        self._compute_draw_scale()

        # Draw left (base)
        left_bgr = self.base_prev.copy()
        if self.ds != 1.0:
            left_bgr = cv2.resize(
                left_bgr, (self.tw, self.th), interpolation=cv2.INTER_AREA
            )
        left_img = QPixmap.fromImage(bgr_to_qimage(left_bgr))

        # Right (moving) if any file exists
        right_img = None
        cur_params = None
        if self.have_files():
            path = self.current_path()
            mov_prev = self._get_preview(path)
            cur_params = self.params[path]
            right_bgr = self._compose_right_preview(mov_prev, cur_params)
            if self.ds != 1.0:
                right_bgr = cv2.resize(
                    right_bgr, (self.tw, self.th), interpolation=cv2.INTER_AREA
                )
            right_img = QPixmap.fromImage(bgr_to_qimage(right_bgr))

        # Panel rects (draw coords)
        left_rect = QRect(0, 0, self.tw, self.th)
        right_rect = QRect(self.tw + self.gap, 0, self.tw, self.th)
        self.left_rect = left_rect
        self.right_rect = right_rect

        p.drawPixmap(left_rect, left_img)

        if right_img is not None:
            p.drawPixmap(right_rect, right_img)
            # If perspective mode, draw corner handles
            if cur_params is not None and cur_params["mode"] == "persp":
                mov_prev = self._get_preview(self.current_path())
                corners = self._ensure_corners(mov_prev, cur_params).astype(float)
                # scale to draw coords and offset to right panel
                for i, (cx, cy) in enumerate(corners):
                    dx = int(round(cx * self.ds)) + right_rect.left()
                    dy = int(round(cy * self.ds)) + right_rect.top()
                    pen = QPen(
                        (
                            QColor(255, 0, 0)
                            if i == self.corner_idx
                            else QColor(0, 255, 0)
                        ),
                        2,
                        Qt.SolidLine,
                    )
                    p.setPen(pen)
                    p.drawEllipse(QPoint(dx, dy), 4, 4)
        else:
            # Placeholder on the right
            p.fillRect(right_rect, QColor(40, 40, 40))
            p.setPen(QColor(200, 200, 200))
            p.drawText(right_rect, Qt.AlignCenter, "Pick a Source directory")

        # Grid (draw space)
        if self.grid_on:
            step_draw = max(1, int(round(self.grid_step * self.ds)))
            pen = QPen(QColor(128, 128, 128), 1, Qt.SolidLine)
            p.setPen(pen)
            # left
            for x in range(0, self.tw, step_draw):
                p.drawLine(x, 0, x, self.th)
            for y in range(0, self.th, step_draw):
                p.drawLine(0, y, self.tw, y)
            # right
            for x in range(right_rect.left(), right_rect.left() + self.tw, step_draw):
                p.drawLine(x, 0, x, self.th)
            for y in range(0, self.th, step_draw):
                p.drawLine(right_rect.left(), y, right_rect.left() + self.tw, y)

        # Hover-linked grid highlight (draw space)
        if self.grid_on and self.hover_cell is not None:
            x0, y0, x1, y1 = self.hover_cell
            hp = QPen(QColor(255, 255, 0), 2, Qt.SolidLine)
            p.setPen(hp)
            p.drawRect(QRect(x0, y0, x1 - x0, y1 - y0))
            p.drawRect(QRect(x0 + self.tw + self.gap, y0, x1 - x0, y1 - y0))

        # File label if we have a moving image
        if self.have_files():
            path = self.current_path()
            p.setPen(QColor(240, 240, 240))
            p.drawText(8, self.th - 8, f"{path.name}  [{self.idx+1}/{len(self.files)}]")

        p.end()

    def mouseMoveEvent(self, evt):
        pos = evt.pos()
        # Hover cell on base (draw space)
        if 0 <= pos.x() < self.tw and 0 <= pos.y() < self.th:
            step_draw = max(1, int(round(self.grid_step * self.ds)))
            gx0 = (pos.x() // step_draw) * step_draw
            gy0 = (pos.y() // step_draw) * step_draw
            gx1 = min(gx0 + step_draw, self.tw - 1)
            gy1 = min(gy0 + step_draw, self.th - 1)
            self.hover_cell = (int(gx0), int(gy0), int(gx1), int(gy1))
        else:
            self.hover_cell = None

        # Drag pan on right panel (convert draw delta -> preview delta) — only in affine mode
        if self.dragging and self.drag_last is not None and self.have_files():
            dx_draw = pos.x() - self.drag_last.x()
            dy_draw = pos.y() - self.drag_last.y()
            dx_prev = dx_draw / self.ds if self.ds != 0 else 0.0
            dy_prev = dy_draw / self.ds if self.ds != 0 else 0.0
            path = self.current_path()
            if path:
                pr = self.params[path]
                if pr["mode"] == "persp":
                    # drag in persp mode moves selected corner
                    self._nudge_corner(dx_prev, dy_prev, micro=False)
                else:
                    pr["tx"] = float(pr["tx"]) + dx_prev
                    pr["ty"] = float(pr["ty"]) + dy_prev
            self.drag_last = pos
            self.update()

        # Update crop rubber band (clamp to base panel)
        if self.crop_mode and self.crop_origin is not None:
            rect = QRect(self.crop_origin, pos).normalized()
            rect = rect.intersected(self.left_rect)
            self.rubber.setGeometry(rect)

        self.update()

    def mousePressEvent(self, evt):
        pos = evt.pos()
        # Begin drag on right panel
        if (
            evt.button() == Qt.LeftButton
            and self.right_rect.contains(pos)
            and not self.crop_mode
            and self.have_files()
        ):
            self.dragging = True
            self.drag_last = pos
            self.setCursor(Qt.ClosedHandCursor)

        # Begin crop on left panel
        if (
            evt.button() == Qt.LeftButton
            and self.crop_mode
            and self.left_rect.contains(pos)
        ):
            self.crop_origin = pos
            self.rubber.setGeometry(QRect(pos, QSize()))
            self.rubber.show()

    def mouseReleaseEvent(self, evt):
        if evt.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self.drag_last = None
            self.setCursor(Qt.ArrowCursor)

        # Finish crop
        if evt.button() == Qt.LeftButton and self.crop_mode and self.rubber.isVisible():
            self.rubber.hide()
            rect = self.rubber.geometry()
            if rect.width() > 2 and rect.height() > 2:
                self.crop_rect_px = rect
                self._confirm_crop_all()
            self.crop_mode = False
            self.crop_origin = None
            self.update()

    def keyPressEvent(self, evt):
        path = self.current_path()
        key = evt.key()

        # allow toggles even without a moving image
        if path is None:
            if key == Qt.Key_G:
                self.grid_on = not self.grid_on
                self.update()
            return

        p = self.params[path]
        shift = bool(evt.modifiers() & Qt.ShiftModifier)
        amt = self.corner_micro_step if shift else self.corner_step

        # Mode toggle
        if key == Qt.Key_P:
            p["mode"] = "persp" if p["mode"] == "affine" else "affine"
            self.update()
            return

        # Corner select
        if key in (Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4):
            self.corner_idx = {Qt.Key_1: 0, Qt.Key_2: 1, Qt.Key_3: 2, Qt.Key_4: 3}[key]
            self.update()
            return

        if p["mode"] == "persp":
            # Arrow keys nudge selected corner
            if key in (Qt.Key_Left, Qt.Key_A):
                self._nudge_corner(-amt, 0, micro=shift)
            elif key in (Qt.Key_Right, Qt.Key_D):
                self._nudge_corner(+amt, 0, micro=shift)
            elif key in (Qt.Key_Up, Qt.Key_W):
                self._nudge_corner(0, -amt, micro=shift)
            elif key in (Qt.Key_Down, Qt.Key_S):
                self._nudge_corner(0, +amt, micro=shift)
            elif key == Qt.Key_0:
                # reset corners from current affine
                mov_prev = self._get_preview(path)
                p["corners"] = None
                self._ensure_corners(mov_prev, p)
            # other keys (rotate/zoom) are ignored in persp mode
            self.update()
            return

        # ----- affine controls (existing) -----
        # Move (Arrows + WASD) – step is in PREVIEW pixels
        if key in (Qt.Key_Left, Qt.Key_A):
            p["tx"] = float(p["tx"]) - self.step
        elif key in (Qt.Key_Right, Qt.Key_D):
            p["tx"] = float(p["tx"]) + self.step
        elif key in (Qt.Key_Up, Qt.Key_W):
            p["ty"] = float(p["ty"]) - self.step
        elif key in (Qt.Key_Down, Qt.Key_S):
            p["ty"] = float(p["ty"]) + self.step

        # Rotate
        elif key == Qt.Key_BracketLeft:
            p["theta"] = float(p["theta"]) - self.rot_step
        elif key == Qt.Key_BracketRight:
            p["theta"] = float(p["theta"]) + self.rot_step

        # Zoom
        elif key == Qt.Key_Comma:
            p["scale"] = clamp(float(p["scale"]) * (1.0 - self.scale_step), 0.8, 1.2)
        elif key == Qt.Key_Period:
            p["scale"] = clamp(float(p["scale"]) * (1.0 + self.scale_step), 0.8, 1.2)
        elif key == Qt.Key_Z:
            p["scale"] = clamp(
                float(p["scale"]) * (1.0 - self.micro_scale_step), 0.8, 1.2
            )
        elif key == Qt.Key_X:
            p["scale"] = clamp(
                float(p["scale"]) * (1.0 + self.micro_scale_step), 0.8, 1.2
            )

        # Step
        elif key == Qt.Key_Equal:
            self.step = min(50.0, self.step + 1.0)
        elif key == Qt.Key_Minus:
            self.step = max(0.5, self.step - 0.5)

        # Toggles
        elif key == Qt.Key_O:
            self.overlay_mode = not self.overlay_mode
        elif key == Qt.Key_G:
            self.grid_on = not self.grid_on
        elif key == Qt.Key_B:
            self.show_outline = not self.show_outline

        # Reset
        elif key == Qt.Key_0:
            p["tx"] = p["ty"] = 0.0
            p["theta"] = 0.0
            p["scale"] = 1.0

        # Save (no next)
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_S):
            self.save_current_aligned()

        # Crop mode start (uses last chosen target)
        elif key == Qt.Key_C:
            self.start_crop_mode()

        self.update()

    # ---- crop + warp helpers ----

    def _confirm_crop_all(self):
        if not self.crop_rect_px or self.base_full is None or not self.crop_out:
            return

        # Map DRAW/widget rect to FULL-res
        rect = self.crop_rect_px
        # position relative to left panel
        xw = rect.x() - self.left_rect.x()
        yw = rect.y() - self.left_rect.y()
        ww = rect.width()
        hw = rect.height()

        # draw -> preview
        if self.ds == 0:
            return
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

        # Decide file list based on target choice
        if self.crop_from_aligned:
            file_list = list(self.align_out.glob("*.png")) if self.align_out else []
        else:
            file_list = self.files  # source images

        for pth in file_list:
            if self.crop_from_aligned:
                img = cv2.imread(str(pth), cv2.IMREAD_COLOR)
                if img is None:
                    continue  # skip unreadable
                out_name = pth.name
            else:
                img = load_image_bgr(str(pth))
                out_name = f"{pth.stem}.png"

            crop = img[cy : cy + ch, cx : cx + cw]
            cv2.imwrite(str(self.crop_out / out_name), crop)

        QMessageBox.information(
            self,
            "Cropped",
            f"Cropped {'aligned' if self.crop_from_aligned else 'source'} images -> {self.crop_out}",
        )

    # ---- perspective helpers ----
    def _nudge_corner(self, dx: float, dy: float, micro: bool):
        """Move selected corner in preview space."""
        path = self.current_path()
        if not path:
            return
        p = self.params[path]
        mov_prev = self._get_preview(path)
        corners = self._ensure_corners(mov_prev, p)
        i = int(self.corner_idx) % 4
        corners[i, 0] += float(dx)
        corners[i, 1] += float(dy)
        p["corners"] = corners
        self.update()

    def _warp_full_from_params(self, path: Path) -> np.ndarray:
        mov_prev = self._get_preview(path)
        p = self.params[path]
        img_full = load_image_bgr(str(path))
        bw, bh = self.base_full.shape[1], self.base_full.shape[0]
        if p["mode"] == "persp":
            H_small = self._params_to_homography_small(mov_prev, p)
            H_full = self._lift_homography_small_to_full(H_small)
            out = cv2.warpPerspective(
                img_full,
                H_full,
                (bw, bh),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0),
            )
        else:
            M_small = self._params_to_matrix_small(mov_prev, p)
            M_full = self._lift_small_to_full(M_small)
            out = cv2.warpAffine(
                img_full,
                M_full,
                (bw, bh),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0),
            )
        return out
