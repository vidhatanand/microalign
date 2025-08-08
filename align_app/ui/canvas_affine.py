"""Affine helpers used by CanvasCore."""

from __future__ import annotations

from typing import Dict

import cv2  # type: ignore
import numpy as np

# pylint: disable=no-member


def affine_params_to_small(
    mov_prev: np.ndarray, params: Dict[str, object]
) -> np.ndarray:
    """Return 2x3 affine matrix in PREVIEW space from params."""
    h, w = mov_prev.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    theta = float(params.get("theta", 0.0))
    scale = float(params.get("scale", 1.0))
    tx = float(params.get("tx", 0.0))
    ty = float(params.get("ty", 0.0))
    m = cv2.getRotationMatrix2D((cx, cy), theta, scale)
    m[0, 2] += tx
    m[1, 2] += ty
    return m


def affine_lift_small_to_full(preview_scale: float, m_small: np.ndarray) -> np.ndarray:
    """Lift preview-space 2x3 matrix to full-res 2x3."""
    a = np.eye(3, dtype=np.float32)
    a[:2, :3] = m_small
    s = np.diag([preview_scale, preview_scale, 1.0]).astype(np.float32)
    s_inv = np.diag([1.0 / preview_scale, 1.0 / preview_scale, 1.0]).astype(np.float32)
    w = s_inv @ a @ s
    return w[:2, :]


def _overlay(base: np.ndarray, warped: np.ndarray, alpha: float) -> np.ndarray:
    mask = (warped > 0).any(axis=2).astype(np.uint8) * 255
    mask3 = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    return np.where(mask3 > 0, cv2.addWeighted(base, 1 - alpha, warped, alpha, 0), base)


def _outline(img: np.ndarray, mov_prev: np.ndarray, m_small: np.ndarray) -> None:
    h, w = mov_prev.shape[:2]
    corners = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]).reshape(
        -1, 1, 2
    )
    m3 = np.vstack([m_small, [0, 0, 1]]).astype(np.float32)
    tc = cv2.perspectiveTransform(corners, m3).astype(int).reshape(-1, 2)
    cv2.polylines(img, [tc], True, (0, 255, 255), 1, cv2.LINE_AA)


def affine_compose_preview(
    base_prev: np.ndarray,
    mov_prev: np.ndarray,
    m_small: np.ndarray,
    overlay: bool,
    alpha: float,
    outline: bool,
) -> np.ndarray:
    """Warp mov_prev in PREVIEW space to base_prev dims and compose/annotate."""
    ph, pw = base_prev.shape[:2]
    warped = cv2.warpAffine(
        mov_prev,
        m_small,
        (pw, ph),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    out = warped
    if overlay:
        out = _overlay(base_prev.copy(), warped, alpha)
    if outline:
        _outline(out, mov_prev, m_small)
    return out
