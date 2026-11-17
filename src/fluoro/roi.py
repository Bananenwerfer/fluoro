"""ROI proposal from the white-light image. Identical to fluoro 1.0.0 except that the exclusion area is optional.

Tissue is separated from a grey background by HSV saturation (Otsu threshold within the illuminated field), followed
by morphological opening and closing, hole filling and removal of small components. The proposal is only a starting
point; only the approved mask is measured.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

V_MIN = 40                 # illuminated field: HSV value above this
MIN_COMPONENT = 0.002      # components smaller than this fraction of the image are discarded
OPEN_ITER, CLOSE_ITER = 3, 6


@dataclass
class RoiProposal:
    mask: np.ndarray
    otsu: float
    threshold: float
    threshold_factor: float


def otsu_threshold(values: np.ndarray, bins: int = 256) -> float:
    hist, edges = np.histogram(values, bins=bins, range=(0, 256))
    centers = (edges[:-1] + edges[1:]) / 2
    w = hist / hist.sum()
    w0 = np.cumsum(w)
    w1 = 1 - w0
    cum = np.cumsum(w * centers)
    m0 = cum / np.maximum(w0, 1e-12)
    m1 = (cum[-1] - cum) / np.maximum(w1, 1e-12)
    return float(centers[np.argmax(w0 * w1 * (m0 - m1) ** 2)])


def propose_roi(wl_rgb: np.ndarray, threshold_factor: float = 1.0, exclude=None) -> RoiProposal:
    """exclude: optional numpy index (e.g. a tuple of slices) that is never part of the ROI."""
    hsv = np.asarray(Image.fromarray(wl_rgb).convert("HSV")).astype(float)
    sat, val = hsv[..., 1], hsv[..., 2]
    valid = val > V_MIN
    if exclude is not None:
        valid[exclude] = False
    if not valid.any():
        return RoiProposal(np.zeros(valid.shape, bool), 0.0, 0.0, threshold_factor)
    otsu = otsu_threshold(sat[valid])
    threshold = otsu * threshold_factor
    m = valid & (sat > threshold)
    m = ndi.binary_opening(m, iterations=OPEN_ITER)
    m = ndi.binary_fill_holes(ndi.binary_closing(m, iterations=CLOSE_ITER))
    lab, n = ndi.label(m)
    if n:
        sizes = ndi.sum(m, lab, range(1, n + 1))
        keep = [i + 1 for i, s in enumerate(sizes) if s >= MIN_COMPONENT * m.size]
        m = np.isin(lab, keep)
    if exclude is not None:
        m[exclude] = False
    return RoiProposal(mask=m, otsu=otsu, threshold=threshold, threshold_factor=threshold_factor)
