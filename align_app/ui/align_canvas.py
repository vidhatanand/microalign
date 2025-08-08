# [FULL FILE — paste replaces your current align_canvas.py]
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QRect, QPoint, QSize
from PyQt5.QtGui import QPainter, QPen, QColor, QPixmap
from PyQt5.QtWidgets import QWidget, QMessageBox, QRubberBand

from align_app.utils.img_io import (
    load_image_bgr, uniform_preview_scale, clamp, bgr_to_qimage, SUPPORTED_LOWER
)


class AlignCanvas(QWidget):
    """Widget that renders base/current panels and handles manual alignment."""
    gap = 8  # gap between left/right panels in widget (draw space)

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
        self.s: float = 1.0            # preview scale relative to full-res
        self.pw: int = 0               # preview width (canonical)
        self.ph: int = 0               # preview height (canonical)

        # Draw sizing (dynamic per paint to fit the widget)
        self.ds: float = 1.0           # extra draw scale applied to preview
        self.tw: int = 0               # drawn panel width  = int(pw * ds)
        self.th: int = 0               # drawn panel height = int(ph * ds)

        # Per-image params (preview-space; i.e., before applying ds)
        self.params: Dict[Path, Dict[str, float]] = {}
        self.idx: int = 0

        # UI state
        self.alpha = 0.5
        self.step = 1.0                # MOVE step (px in preview space)
        self.rot_step = 0.10           # degrees per tick
        self.scale_step = 0.005        # 0.5% zoom
        self.micro_scale_step = 0.001  # 0.1% zoom
        self.grid_on = True
        self.grid_step = 40            # in preview px
        self.overlay_mode = False
        self.show_outline = True

        # Hover & drag
        self.hover_cell: Optional[Tuple[int, int, int, int]] = None  # in DRAW coords
        self.dragging = False
        self.drag_last: Optional[QPoint] = None

        # Crop
        self.crop_mode = False
        self.rubber = QRubberBand(QRubberBand.Rectangle, self)
        self.crop_origin: Optional[QPoint] = None
        self.crop_rect_px: Optional[QRect] = None  # in WIDGET/DRAW coords on base

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
            self.base_prev = cv2.resize(self.base_full, (self.pw, self.ph), interpolation=cv2.INTER_AREA)
        else:
            self.base_full = None
            self.base_prev = None
            self.pw = self.ph = 0

        # Collect files if dir set (RECURSIVE)
        if self.src_dir and self.src_dir.is_dir():
            self.files = sorted(
                (p for p in self.src_dir.rglob("*")
                 if p.is_file() and p.suffix.lower() in SUPPORTED_LOWER),
                key=lambda p: str(p).lower()
            )
            # reset params for new files
            self.params = {p: {"tx": 0.0, "ty": 0.0, "theta": 0.0, "scale": 1.0} for p in self.files}
            self.idx = 0
            self.cache_prev.clear()

        self.update()

    def prev_image(self):
        if not self.files:
            return
        if self.idx > 0:
            self.idx -= 1
            self.update()

    def next_image(self):
        if not self.files:
            return
        if self.idx < len(self.files) - 1:
            self.idx += 1
            self.update()

    def move_dxdy(self, dx: float, dy: float):
        path = self.current_path()
        if not path:
            return
        p = self.params[path]
        p["tx"] += dx
        p["ty"] += dy
        self.update()

    def rotate_deg(self, dtheta: float):
        path = self.current_path()
        if not path:
            return
        p = self.params[path]
        p["theta"] += dtheta
        self.update()

    def zoom_factor(self, mul: float):
        path = self.current_path()
        if not path:
            return
        p = self.params[path]
        p["scale"] = clamp(p["scale"] * mul, 0.8, 1.2)
        self.update()

    def reset_current(self):
        path = self.current_path()
        if not path:
            return
        p = self.params[path]
        p["tx"] = p["ty"] = 0.0
        p["theta"] = 0.0
        p["scale"] = 1.0
        self.update()

    def save_current_aligned(self):
        if not (self.align_out and self.base_full is not None):
            QMessageBox.warning(self, "Missing path", "Please set Align Out folder in the toolbar.")
            return
        self.align_out.mkdir(parents=True, exist_ok=True)
        path = self.current_path()
        if not path:
            return
        mov_prev = self._get_preview(path)
        p = self.params[path]
        M_small = self._params_to_matrix_small(mov_prev, p)
        M_full = self._lift_small_to_full(M_small)
        img_full = load_image_bgr(str(path))
        bw, bh = self.base_full.shape[1], self.base_full.shape[0]
        out = cv2.warpAffine(img_full, M_full, (bw, bh),
                             flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
        out_path = self.align_out / f"{path.stem}.png"
        cv2.imwrite(str(out_path), out)
        QMessageBox.information(self, "Saved", f"Aligned -> {out_path}")

    def start_crop_mode(self):
        if self.base_full is None:
            return
        if not self.crop_out:
            QMessageBox.warning(self, "Missing path", "Please set Crops Out folder in the toolbar.")
            return
        self.crop_mode = True
        self.crop_origin = None
        self.rubber.hide()
        QMessageBox.information(self, "Crop",
                                "Drag a rectangle on the BASE (left) panel.\n"
                                "Release mouse to confirm.")

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
        prev = cv2.resize(full, (int(round(full.shape[1] * self.s)),
                                 int(round(full.shape[0] * self.s))),
                          interpolation=cv2.INTER_AREA)
        self.cache_prev[path] = prev
        return prev

    def _params_to_matrix_small(self, mov_prev: np.ndarray, p: Dict[str, float]) -> np.ndarray:
        h, w = mov_prev.shape[:2]
        cx, cy = w / 2.0, h / 2.0
        M = cv2.getRotationMatrix2D((cx, cy), p["theta"], p["scale"])
        M[0, 2] += p["tx"]
        M[1, 2] += p["ty"]
        return M

    def _lift_small_to_full(self, M_small: np.ndarray) -> np.ndarray:
        # Lift preview-space affine to full-res affine
        A = np.eye(3, dtype=np.float32)
        A[:2, :3] = M_small
        S = np.diag([self.s, self.s, 1.0]).astype(np.float32)
        S_inv = np.diag([1.0 / self.s, 1.0 / self.s, 1.0]).astype(np.float32)
        W = S_inv @ A @ S
        return W[:2, :]

    def _compose_right_preview(self, mov_prev: np.ndarray, M_small: np.ndarray) -> np.ndarray:
        # Warp at PREVIEW size (pw,ph)
        warped = cv2.warpAffine(
            mov_prev, M_small, (self.pw, self.ph),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0)
        )
        comp = warped
        if self.overlay_mode and self.base_prev is not None:
            base = self.base_prev.copy()
            mask = (warped > 0).any(axis=2).astype(np.uint8) * 255
            mask3 = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            comp = np.where(mask3 > 0,
                            cv2.addWeighted(base, 1 - self.alpha, warped, self.alpha, 0),
                            base)

        if self.show_outline:
            h, w = mov_prev.shape[:2]
            corners = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]).reshape(-1, 1, 2)
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
            p.drawText(self.rect(), Qt.AlignCenter, "Pick a Base image from the toolbar.")
            p.end()
            return

        self._compute_draw_scale()

        # Draw left (base)
        left_bgr = self.base_prev.copy()
        if self.ds != 1.0:
            left_bgr = cv2.resize(left_bgr, (self.tw, self.th), interpolation=cv2.INTER_AREA)
        left_img = QPixmap.fromImage(bgr_to_qimage(left_bgr))

        # Right (moving) if any file exists
        right_img = None
        if self.have_files():
            path = self.current_path()
            mov_prev = self._get_preview(path)
            params = self.params[path]
            M_small = self._params_to_matrix_small(mov_prev, params)
            right_bgr = self._compose_right_preview(mov_prev, M_small)
            if self.ds != 1.0:
                right_bgr = cv2.resize(right_bgr, (self.tw, self.th), interpolation=cv2.INTER_AREA)
            right_img = QPixmap.fromImage(bgr_to_qimage(right_bgr))

        # Panel rects (draw coords)
        left_rect = QRect(0, 0, self.tw, self.th)
        right_rect = QRect(self.tw + self.gap, 0, self.tw, self.th)
        self.left_rect = left_rect
        self.right_rect = right_rect

        p.drawPixmap(left_rect, left_img)

        if right_img is not None:
            p.drawPixmap(right_rect, right_img)
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

        # Drag pan on right panel (convert draw delta -> preview delta)
        if self.dragging and self.drag_last is not None and self.have_files():
            dx_draw = pos.x() - self.drag_last.x()
            dy_draw = pos.y() - self.drag_last.y()
            dx_prev = dx_draw / self.ds if self.ds != 0 else 0.0
            dy_prev = dy_draw / self.ds if self.ds != 0 else 0.0
            path = self.current_path()
            if path:
                pr = self.params[path]
                pr["tx"] += dx_prev
                pr["ty"] += dy_prev
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
        if evt.button() == Qt.LeftButton and self.right_rect.contains(pos) and not self.crop_mode and self.have_files():
            self.dragging = True
            self.drag_last = pos
            self.setCursor(Qt.ClosedHandCursor)

        # Begin crop on left panel
        if evt.button() == Qt.LeftButton and self.crop_mode and self.left_rect.contains(pos):
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
        if path is None:
            # allow toggles even without a moving image
            key = evt.key()
            if key == Qt.Key_G:
                self.grid_on = not self.grid_on
                self.update()
            return

        p = self.params[path]
        key = evt.key()

        # Move (Arrows + WASD) – step is in PREVIEW pixels
        if key in (Qt.Key_Left, Qt.Key_A):
            p["tx"] -= self.step
        elif key in (Qt.Key_Right, Qt.Key_D):
            p["tx"] += self.step
        elif key in (Qt.Key_Up, Qt.Key_W):
            p["ty"] -= self.step
        elif key in (Qt.Key_Down, Qt.Key_S):
            p["ty"] += self.step

        # Rotate
        elif key == Qt.Key_BracketLeft:
            p["theta"] -= self.rot_step
        elif key == Qt.Key_BracketRight:
            p["theta"] += self.rot_step

        # Zoom
        elif key == Qt.Key_Comma:
            p["scale"] = clamp(p["scale"] * (1.0 - self.scale_step), 0.8, 1.2)
        elif key == Qt.Key_Period:
            p["scale"] = clamp(p["scale"] * (1.0 + self.scale_step), 0.8, 1.2)
        elif key == Qt.Key_Z:
            p["scale"] = clamp(p["scale"] * (1.0 - self.micro_scale_step), 0.8, 1.2)
        elif key == Qt.Key_X:
            p["scale"] = clamp(p["scale"] * (1.0 + self.micro_scale_step), 0.8, 1.2)

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

        # Crop mode start
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
        base_crop = self.base_full[cy:cy+ch, cx:cx+cw]
        cv2.imwrite(str((self.crop_out / f"{self.base_path.stem}.png")), base_crop)

        # Each aligned image: use saved aligned if exists, else warp from params
        for pth in self.files:
            aligned_png = (self.align_out / f"{pth.stem}.png") if self.align_out else None
            if aligned_png and aligned_png.exists():
                img = cv2.imread(str(aligned_png), cv2.IMREAD_COLOR)
                if img is None:
                    img = self._warp_full_from_params(pth)
            else:
                img = self._warp_full_from_params(pth)
            crop = img[cy:cy+ch, cx:cx+cw]
            cv2.imwrite(str((self.crop_out / f"{pth.stem}.png")), crop)

        QMessageBox.information(self, "Cropped", f"Crops -> {self.crop_out}")

    def _warp_full_from_params(self, path: Path) -> np.ndarray:
        mov_prev = self._get_preview(path)
        p = self.params[path]
        M_small = self._params_to_matrix_small(mov_prev, p)
        img_full = load_image_bgr(str(path))
        bw, bh = self.base_full.shape[1], self.base_full.shape[0]
        M_full = self._lift_small_to_full(M_small)
        out = cv2.warpAffine(
            img_full, M_full, (bw, bh),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0)
        )
        return out
