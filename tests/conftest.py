"""Synthetic white-light/fluorescence pairs: a reddish 'organ' ellipse on a grey background."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def synthetic_pair(h=240, w=320, seed=0, fl_inside=150, fl_outside=10):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[:h, :w]
    organ = ((xx - w * 0.5) / (w * 0.25)) ** 2 + ((yy - h * 0.5) / (h * 0.3)) ** 2 <= 1
    wl = np.full((h, w, 3), 128, np.int64)
    wl[organ] = (190, 70, 60)
    wl = np.clip(wl + rng.integers(-6, 7, size=(h, w, 3)), 0, 255).astype(np.uint8)
    fl = np.zeros((h, w, 3), np.uint8)
    fl[..., 0] = fl_outside
    fl[organ, 0] = fl_inside
    return wl, fl, organ


def write_pair(folder: Path, name: str, ext="png", wl_suffix="WL", fl_suffix="FL", **kw):
    wl, fl, organ = synthetic_pair(**kw)
    Image.fromarray(wl).save(Path(folder) / f"{name}_{wl_suffix}.{ext}")
    Image.fromarray(fl).save(Path(folder) / f"{name}_{fl_suffix}.{ext}")
    return organ


@pytest.fixture
def pair_folder(tmp_path):
    """Three valid PNG pairs: Liver, Kidney2, Kidney10."""
    for i, n in enumerate(("Liver", "Kidney2", "Kidney10")):
        write_pair(tmp_path, n, seed=i)
    return tmp_path
