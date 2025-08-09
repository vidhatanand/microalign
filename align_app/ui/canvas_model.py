from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

# pylint: disable=no-member
import cv2  # type: ignore
import numpy as np
from PyQt5 import QtWidgets  # pylint: disable=no-name-in-module

from align_app.utils.img_io import (
    SUPPORTED_LOWER,
    load_image_bgr,
    uniform_preview_scale,
    clamp,
)
from .canvas_affine import (
    affine_lift_small_to_full,
    affine_params_to_small,
)
from .canvas_perspective import (
    ensure_perspective_quad,
    perspective_warp_full,
)


class CanvasModelMixin:
    """State, params, history, paths, and transform helpers."""

    # ---- init ----
    def _init_model(self) -> None:
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

        # Per-image params
        # affine: tx,ty,theta,scale
        # perspective: quad in PREVIEW coords (dest points TL,TR,BR,BL)
        self.params: Dict[Path, Dict[str, object]] = {}
        self.idx: int = 0

        # History (per image)
        self._hist: Dict[Path, List[Dict[str, object]]] = {}
        self._hist_idx: Dict[Path, int] = {}

        # Mode flags
        # 'perspective_mode' remains for legacy; we'll use '_persp_editing' as the truth.
        self.perspective_mode: bool = False  # legacy name
        self._persp_editing: bool = False  # true = drawing handles / editing
        self.active_corner = 0  # 0..3 when perspective is active

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

    # ---- signals hooks (overridden by AlignCanvas) ----
    def _on_mode_changed(self, _is_persp: bool) -> None:
        pass

    def _on_active_corner_changed(self, _idx: int) -> None:
        pass

    # ---- model access ----
    def have_base(self) -> bool:
        return self.base_prev is not None

    def have_files(self) -> bool:
        return bool(self.files)

    def current_path(self) -> Optional[Path]:
        if not self.files:
            return None
        return self.files[self.idx]

    # ---- history ----
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
        if idx < len(lst) - 1:
            del lst[idx + 1 :]
        lst.append(self._clone_state(self.params[path]))
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
        if "persp" in p:
            del p["persp"]
        self.update()

    # ---- paths / loading ----
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
            self.params = {
                p: {"tx": 0.0, "ty": 0.0, "theta": 0.0, "scale": 1.0}
                for p in self.files
            }
            self.idx = 0
            self.cache_prev.clear()
            self._hist.clear()
            self._hist_idx.clear()

        self.update()

    # ---- preview cache ----
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

    # ---- navigation ----
    def next_image(self) -> None:
        if self.files and self.idx < len(self.files) - 1:
            self.idx += 1
            self.update()

    def prev_image(self) -> None:
        if self.files and self.idx > 0:
            self.idx -= 1
            self.update()

    # ---- perspective helpers ----
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

    def has_perspective(self) -> bool:
        """True if current image has a non-default perspective quad."""
        path = self.current_path()
        if not path:
            return False
        p = self.params.get(path, {})
        if "persp" not in p:
            return False
        try:
            quad = p["persp"]  # type: ignore[index]
            return not self._is_default_quad(quad)
        except Exception:
            return False

    # ---- editing/legacy toggles ----
    def set_perspective_mode(self, enabled: bool) -> None:
        """Legacy entry point; now maps to 'editing' (handles visibility)."""
        self.set_perspective_editing(bool(enabled))

    def set_perspective_editing(self, editing: bool) -> None:
        """Enable/disable perspective *editing* (handles); warp persists regardless."""
        editing = bool(editing)
        if self._persp_editing == editing:
            return
        self._persp_editing = editing
        # keep legacy flag in sync for any old code
        self.perspective_mode = editing

        if editing:
            path = self.current_path()
            if path:
                p = self.params[path]
                # make sure a quad exists
                ensure_perspective_quad(p, self.pw, self.ph)
                quad = p["persp"]  # type: ignore[index]
                # seed from current affine if still default-ish
                if self._is_default_quad(quad):
                    mov_prev = self._get_preview(path)
                    m_small = affine_params_to_small(mov_prev, p)
                    h, w = mov_prev.shape[:2]
                    corners = np.float32(
                        [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]
                    ).reshape(-1, 1, 2)
                    tc = cv2.transform(corners, m_small).reshape(-1, 2)
                    p["persp"] = [(float(x), float(y)) for (x, y) in tc]

        self._on_mode_changed(self._persp_editing)
        self.update()

    def set_active_corner(self, idx: int) -> None:
        idx = int(max(0, min(3, idx)))
        if self.active_corner != idx:
            self.active_corner = idx
            self._on_active_corner_changed(self.active_corner)
            self.update()

    # ---- affine ops (disabled only while actively editing) ----
    def move_dxdy(self, dx: float, dy: float) -> None:
        if not self.have_files() or self._persp_editing:
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
        if not self.have_files() or self._persp_editing:
            return
        path = self.current_path()
        if not path:
            return
        self._push_history(path)
        p = self.params[path]
        p["theta"] = float(p.get("theta", 0.0)) + float(dtheta)  # type: ignore[index]
        self.update()

    def zoom_factor(self, factor: float) -> None:
        if not self.have_files() or self._persp_editing:
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

    # ---- saving aligned output ----
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

        if self.has_perspective():
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
