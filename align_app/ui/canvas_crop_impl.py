from __future__ import annotations

from typing import Callable, Optional

# pylint: disable=no-member
import cv2  # type: ignore
from PyQt5 import QtCore, QtWidgets  # type: ignore

from align_app.utils.img_io import load_image_bgr


class CanvasCropMixin:
    """Crop UI + export logic."""

    def _init_crop(self) -> None:
        self.crop_mode = False
        self.rubber = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
        self.crop_origin: Optional[QtCore.QPoint] = None
        self.crop_rect_px: Optional[QtCore.QRect] = None
        self.crop_from_aligned: bool = True  # user choice remembered

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
        if self.base_path is not None:
            out_name_base = f"{self.base_path.stem}.png"
        else:
            out_name_base = "base.png"
        cv2.imwrite(str((self.crop_out / out_name_base)), base_crop)

        # Decide list
        if self.crop_from_aligned:
            file_list = list(self.align_out.glob("*.png")) if self.align_out else []
        else:
            file_list = self.files

        total = len(file_list)
        done = 0

        # Robust, typed progress callback to appease linters
        notify_attr = getattr(self, "_emit_crop_progress", None)

        def _noop_progress(_a: int, _b: int) -> None:
            return

        notify_fn: Callable[[int, int], None]
        if callable(notify_attr):
            notify_fn = notify_attr  # type: ignore[assignment]
        else:
            notify_fn = _noop_progress

        for pth in file_list:
            if self.crop_from_aligned:
                img = cv2.imread(str(pth), cv2.IMREAD_COLOR)
                if img is None:
                    done += 1
                    notify_fn(done, total)
                    continue
                out_name = pth.name
            else:
                img = load_image_bgr(str(pth))
                out_name = f"{pth.stem}.png"

            crop = img[cy : cy + ch, cx : cx + cw]
            cv2.imwrite(str(self.crop_out / out_name), crop)

            done += 1
            notify_fn(done, total)

        notify_fn(total, total)

        QtWidgets.QMessageBox.information(
            self,
            "Cropped",
            f"Cropped {'aligned' if self.crop_from_aligned else 'source'} images -> {self.crop_out}",
        )
