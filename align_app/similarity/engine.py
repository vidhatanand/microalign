from __future__ import annotations

from typing import Dict, List, Tuple, Optional

# pylint: disable=no-member
import cv2  # type: ignore
import numpy as np

from align_app.ui.canvas_affine import affine_params_to_small
from align_app.ui.canvas_perspective import (
    ensure_perspective_quad,
    perspective_with_affine_compose_preview,
)
# We’ll reuse the plain affine compose helper for the non-perspective path
from align_app.ui.canvas_affine import affine_compose_preview

Point = Tuple[float, float]
Quad = List[Point]

# --------------------------
# Preview composition helpers
# --------------------------

def compose_aligned_preview(
    base_prev: np.ndarray,
    mov_prev: np.ndarray,
    params: Dict[str, object],
    pw: int,
    ph: int,
) -> np.ndarray:
    """Return a preview-size BGR image of 'mov_prev' warped into base space.

    This mirrors the canvas paint-path but without overlays/outlines.
    """
    m_small = affine_params_to_small(mov_prev, params)

    use_persp = (
        "persp" in params
        and isinstance(params["persp"], list)
        and len(params["persp"]) == 4
    )
    if use_persp:
        ensure_perspective_quad(params, pw, ph)
        out = perspective_with_affine_compose_preview(
            base_prev=base_prev,
            mov_prev=mov_prev,
            dest_quad=params["persp"],  # type: ignore[index]
            m_small=m_small,
            overlay=False,
            alpha=0.5,
            outline=False,
        )
    else:
        out = affine_compose_preview(
            base_prev=base_prev,
            mov_prev=mov_prev,
            m_small=m_small,
            overlay=False,
            alpha=0.5,
            outline=False,
        )
    return out


# --------------------------
# Similarity metrics
# --------------------------

def _to_gray_f32(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3 and img.shape[2] == 3:
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        g = img
    return (g.astype(np.float32) / 255.0).copy()


def _masked_mean(x: np.ndarray, mask: np.ndarray) -> float:
    s = float(np.sum(x[mask > 0]))
    n = int(np.sum(mask > 0))
    return s / max(1, n)


def ssim(img1: np.ndarray, img2: np.ndarray, mask: Optional[np.ndarray] = None) -> float:
    """SSIM (grayscale, gaussian window). Returns [0..1]."""
    x = _to_gray_f32(img1)
    y = _to_gray_f32(img2)
    if mask is None:
        mask = np.ones_like(x, dtype=np.uint8)
    else:
        mask = (mask > 0).astype(np.uint8)

    # Gaussian smoothing (11x11, sigma~1.5)
    ksize = 11
    sigma = 1.5
    ux = cv2.GaussianBlur(x, (ksize, ksize), sigma)
    uy = cv2.GaussianBlur(y, (ksize, ksize), sigma)
    uxx = cv2.GaussianBlur(x * x, (ksize, ksize), sigma)
    uyy = cv2.GaussianBlur(y * y, (ksize, ksize), sigma)
    uxy = cv2.GaussianBlur(x * y, (ksize, ksize), sigma)

    vx = uxx - ux * uy * 0 + (uxx - ux * ux)
    vy = uyy - uy * ux * 0 + (uyy - uy * uy)
    cxy = uxy - ux * uy

    # Constants from original SSIM paper (L = 1)
    C1 = (0.01) ** 2
    C2 = (0.03) ** 2

    num = (2 * ux * uy + C1) * (2 * cxy + C2)
    den = (ux * ux + uy * uy + C1) * (vx + vy + C2)
    ssim_map = (num / (den + 1e-12)).clip(0.0, 1.0)

    # masked average
    return float(_masked_mean(ssim_map, mask))


def corrcoef(img1: np.ndarray, img2: np.ndarray, mask: Optional[np.ndarray]) -> float:
    """Pearson correlation in [0..1] (mapped from [-1..1])."""
    x = _to_gray_f32(img1)
    y = _to_gray_f32(img2)
    if mask is not None:
        m = mask > 0
        xv = x[m].reshape(-1)
        yv = y[m].reshape(-1)
    else:
        xv = x.reshape(-1)
        yv = y.reshape(-1)
    if len(xv) < 16 or len(yv) < 16:
        return 0.0
    c = np.corrcoef(xv, yv)[0, 1]
    return float((c + 1.0) * 0.5)


def psnr_norm(img1: np.ndarray, img2: np.ndarray, mask: Optional[np.ndarray]) -> float:
    """PSNR normalized to [0..1] by clamping at 60 dB."""
    if mask is not None:
        m = mask > 0
        if not np.any(m):
            return 0.0
        diff = (img1.astype(np.float32) - img2.astype(np.float32))[m]
        mse = float(np.mean(diff * diff))
    else:
        mse = float(np.mean((img1.astype(np.float32) - img2.astype(np.float32)) ** 2))
    if mse <= 1e-10:
        return 1.0
    ps = 20.0 * np.log10(255.0) - 10.0 * np.log10(mse)
    return float(max(0.0, min(1.0, ps / 60.0)))


def hist_correlation(img1: np.ndarray, img2: np.ndarray, mask: Optional[np.ndarray]) -> float:
    """HSV histogram correlation mapped to [0..1]."""
    hsv1 = cv2.cvtColor(img1, cv2.COLOR_BGR2HSV)
    hsv2 = cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)
    # 30x32x32 bins on H,S,V respectively
    hist1 = cv2.calcHist([hsv1], [0, 1, 2], mask, [30, 32, 32], [0, 180, 0, 256, 0, 256])
    hist2 = cv2.calcHist([hsv2], [0, 1, 2], mask, [30, 32, 32], [0, 180, 0, 256, 0, 256])
    cv2.normalize(hist1, hist1)
    cv2.normalize(hist2, hist2)
    c = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)  # [-1..1]
    return float((c + 1.0) * 0.5)


def orb_inlier_ratio(
    img1: np.ndarray,
    img2: np.ndarray,
    mask: Optional[np.ndarray],
) -> float:
    """ORB + RANSAC inlier ratio [0..1]."""
    g1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(nfeatures=500, scaleFactor=1.2, nlevels=8)
    kp1, des1 = orb.detectAndCompute(g1, mask)
    kp2, des2 = orb.detectAndCompute(g2, mask)
    if des1 is None or des2 is None or len(kp1) < 8 or len(kp2) < 8:
        return 0.0

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = bf.knnMatch(des1, des2, k=2)
    good = []
    for m, n in matches:
        if m.distance < 0.75 * n.distance:
            good.append(m)
    if len(good) < 8:
        return 0.0

    pts1 = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    pts2 = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, inliers = cv2.findHomography(pts1, pts2, cv2.RANSAC, 3.0)
    if H is None or inliers is None:
        return 0.0
    inl = int(inliers.sum())
    return float(inl / max(1, len(good)))


def compute_similarity_metrics(
    base_prev: np.ndarray,
    aligned_prev: np.ndarray,
) -> Dict[str, float]:
    """Compute a set of metrics and an overall score in [0..1]."""
    # Focus metrics on the aligned content (non-black)
    mask = (aligned_prev > 0).any(axis=2).astype(np.uint8) * 255

    ssim_v = ssim(base_prev, aligned_prev, mask)
    corr_v = corrcoef(base_prev, aligned_prev, mask)
    psnr_v = psnr_norm(base_prev, aligned_prev, mask)
    hist_v = hist_correlation(base_prev, aligned_prev, mask)
    orb_v = 0.0
    try:
        # ORB is the slowest; guard but don’t crash UI if it fails
        orb_v = orb_inlier_ratio(base_prev, aligned_prev, mask)
    except Exception:
        orb_v = 0.0

    # Weighted blend (tweakable)
    score = (
        0.45 * ssim_v
        + 0.20 * corr_v
        + 0.10 * hist_v
        + 0.15 * orb_v
        + 0.10 * psnr_v
    )

    return {
        "ssim": float(ssim_v),
        "corr": float(corr_v),
        "hist": float(hist_v),
        "orb": float(orb_v),
        "psnr": float(psnr_v),
        "score": float(max(0.0, min(1.0, score))),
    }


def compute_similarity_for_params(
    base_prev: np.ndarray,
    mov_prev: np.ndarray,
    params: Dict[str, object],
    pw: int,
    ph: int,
) -> Dict[str, float]:
    """High-level helper: compose aligned preview then compute metrics."""
    aligned = compose_aligned_preview(base_prev, mov_prev, params, pw, ph)
    return compute_similarity_metrics(base_prev, aligned)
