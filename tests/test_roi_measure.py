import numpy as np
import pytest

from conftest import synthetic_pair
from fluoro.measure import CHANNELS, measure
from fluoro.roi import propose_roi


def iou(a, b):
    return (a & b).sum() / (a | b).sum()


def test_proposal_finds_organ():
    wl, _, organ = synthetic_pair()
    p = propose_roi(wl)
    assert iou(p.mask, organ) > 0.95 and p.threshold == p.otsu


def test_factor_scales_threshold():
    wl, _, _ = synthetic_pair()
    p = propose_roi(wl, 1.2)
    assert p.threshold == pytest.approx(p.otsu * 1.2)


def test_exclusion_respected():
    wl, _, _ = synthetic_pair()
    ex = (slice(0, 240), slice(0, 160))
    assert not propose_roi(wl, exclude=ex).mask[ex].any()


def test_dark_image_gives_empty_mask():
    p = propose_roi(np.zeros((50, 50, 3), np.uint8))
    assert not p.mask.any()


def test_measure_exact_mean_and_channels():
    _, fl, organ = synthetic_pair()
    r = measure(fl, organ, "red")
    assert r["mean"] == 150.0 and r["min"] == 150 and r["area_px"] == int(organ.sum())
    assert measure(fl, organ, "green")["mean"] == 0.0
    assert set(CHANNELS) == {"red", "green", "blue", "grayscale"}


def test_grayscale_uses_luma():
    _, fl, organ = synthetic_pair()
    assert measure(fl, organ, "grayscale")["mean"] == pytest.approx(150 * 0.299, abs=1)


def test_saturation_flag():
    _, fl, organ = synthetic_pair(fl_inside=255)
    r = measure(fl, organ, "red")
    assert r["n_saturated"] == organ.sum() and r["flag_saturation"]


def test_empty_or_mismatched_mask_rejected():
    _, fl, organ = synthetic_pair()
    with pytest.raises(ValueError):
        measure(fl, np.zeros_like(organ), "red")
    with pytest.raises(ValueError):
        measure(fl, organ[:10], "red")
