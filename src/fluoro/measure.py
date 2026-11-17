"""Read images and measure one channel of the fluorescence image within the approved ROI.

Mean over all ROI pixels as an exact integer sum followed by one division; no background subtraction, no erosion.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

CHANNELS = ("red", "green", "blue", "grayscale")
SATURATION_FRACTION = 0.001        # warning above 0.1 % pixels at 255 in the measured channel


def read_rgb(path: Path) -> np.ndarray:
    """Image as (height, width, 3) uint8 array; greyscale images become three equal channels."""
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.uint8).copy()


def channel_image(rgb: np.ndarray, channel: str) -> np.ndarray:
    if channel == "grayscale":
        return np.asarray(Image.fromarray(rgb).convert("L"))       # ITU-R 601-2 luma
    return rgb[..., {"red": 0, "green": 1, "blue": 2}[channel]]


def measure(fl_rgb: np.ndarray, mask: np.ndarray, channel: str = "red") -> dict:
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")
    if mask.shape != fl_rgb.shape[:2]:
        raise ValueError(f"mask {mask.shape} does not match image {fl_rgb.shape[:2]}")
    area = int(mask.sum())
    if area == 0:
        raise ValueError("empty ROI")
    v = channel_image(fl_rgb, channel)[mask].astype(np.int64)
    n_sat = int((v == 255).sum())
    return {
        "mean": float(v.sum() / area),
        "min": int(v.min()),
        "max": int(v.max()),
        "area_px": area,
        "n_saturated": n_sat,
        "flag_saturation": bool(n_sat / area > SATURATION_FRACTION),
    }
