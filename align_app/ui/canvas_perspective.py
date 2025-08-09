"""Perspective helpers used by CanvasCore."""

from __future__ import annotations

from typing import Dict, List, Tuple

import cv2  # type: ignore
import numpy as np

# pylint: disable=no-member

Point = Tuple[float, float]
Quad = List[Point]


def ensure_perspective_quad(params: Dict[str, object], pw: int, ph: int) -> None:
    """Ensure params['persp'] exists (as preview-dest quad TL,TR,BR,BL)."""
    if (
        "persp" in params
        and isinstance(params["persp"], list)
        and len(params["persp"]) == 4
    ):
        return
    params["persp"] = [
        (0.0, 0.0),
        (pw - 1.0, 0.0),
        (pw - 1.0, ph - 1.0),
        (0.0, ph - 1.0),
    ]


def _overlay(base: np.ndarray, warped: np.ndarray, alpha: float) -> np.ndarray:
    mask = (warped > 0).any(axis=2).astype(np.uint8) * 255
    mask3 = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    return np.where(mask3 > 0, cv2.addWeighted(base, 1 - alpha, warped, alpha, 0), base)


def _outline(img: np.ndarray, quad: Quad) -> None:
    pts = np.array(quad, dtype=np.int32).reshape(-1, 1, 2)
    cv2.polylines(img, [pts], True, (0, 255, 255), 1, cv2.LINE_AA)
    # bigger handles for easier grabbing
    for x, y in quad:
        cv2.circle(img, (int(x), int(y)), 6, (255, 200, 0), -1, cv2.LINE_AA)


def perspective_compose_preview(
    base_prev: np.ndarray,
    mov_prev: np.ndarray,
    dest_quad: Quad,
    overlay: bool,
    alpha: float,
    outline: bool,
) -> np.ndarray:
    """Warp mov_prev with perspective into base_prev dims using preview quad."""
    ph, pw = base_prev.shape[:2]
    src = np.float32(
        [
            [0, 0],
            [mov_prev.shape[1] - 1, 0],
            [mov_prev.shape[1] - 1, mov_prev.shape[0] - 1],
            [0, mov_prev.shape[0] - 1],
        ]
    )
    dst = np.float32(dest_quad)
    h_mat = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(
        mov_prev,
        h_mat,
        (pw, ph),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    out = warped
    if overlay:
        out = _overlay(base_prev.copy(), warped, alpha)
    if outline:
        _outline(out, dest_quad)
    return out


def perspective_warp_full(
    img_full: np.ndarray,
    base_w: int,
    base_h: int,
    dest_quad_prev: Quad,
    preview_scale: float,
) -> np.ndarray:
    """Warp full-res moving image using a PREVIEW quad scaled up to full-res."""
    src = np.float32(
        [
            [0, 0],
            [img_full.shape[1] - 1, 0],
            [img_full.shape[1] - 1, img_full.shape[0] - 1],
            [0, img_full.shape[0] - 1],
        ]
    )
    # scale preview quad up to full-res
    dst = np.float32(
        [(x / preview_scale, y / preview_scale) for (x, y) in dest_quad_prev]
    )
    h_mat = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(
        img_full,
        h_mat,
        (base_w, base_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    return out
