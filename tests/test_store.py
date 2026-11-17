import csv

import numpy as np
import pytest
from PIL import Image

from conftest import synthetic_pair
from fluoro.pairing import scan_folder
from fluoro.store import (RESULTS, RoiMismatchError, load_approval, load_skipped, save_approval, set_skipped,
                          write_results)


def approve(folder, pair, mask, **kw):
    args = dict(threshold_factor=1.0, otsu=50.0, threshold=50.0, edited=False, blind=True,
                approved_at="2026-11-17T12:00:00")
    args.update(kw)
    return save_approval(folder, pair, mask, **args)


def organ_mask():
    return synthetic_pair()[2]


def test_roundtrip(pair_folder):
    p = scan_folder(pair_folder).pairs[0]
    approve(pair_folder, p, organ_mask())
    a = load_approval(pair_folder, p)
    assert np.array_equal(a.mask, organ_mask()) and a.meta["blind"] is True and a.meta["fluoro_version"] == "1.1.0"


def test_none_when_not_approved(pair_folder):
    assert load_approval(pair_folder, scan_folder(pair_folder).pairs[0]) is None


def test_empty_mask_rejected(pair_folder):
    with pytest.raises(ValueError):
        approve(pair_folder, scan_folder(pair_folder).pairs[0], np.zeros((240, 320), bool))


def test_changed_image_detected(pair_folder):
    p = scan_folder(pair_folder).pairs[0]
    approve(pair_folder, p, organ_mask())
    Image.fromarray(np.zeros((240, 320, 3), np.uint8)).save(p.fl)
    with pytest.raises(RoiMismatchError):
        load_approval(pair_folder, p)


def test_skipped_persists_and_clears_on_approval(pair_folder):
    p = scan_folder(pair_folder).pairs[0]
    set_skipped(pair_folder, p.name, True)
    assert load_skipped(pair_folder) == {p.name}
    approve(pair_folder, p, organ_mask())
    assert load_skipped(pair_folder) == set()


def test_results_written_and_channel_recomputed(pair_folder):
    pairs = scan_folder(pair_folder).pairs
    approve(pair_folder, pairs[0], organ_mask())
    rows = write_results(pair_folder, pairs, "red")
    assert len(rows) == 1 and rows[0]["mean"] == "150.000000"
    with open(pair_folder / RESULTS, newline="") as fh:
        assert list(csv.DictReader(fh))[0]["channel"] == "red"
    assert write_results(pair_folder, pairs, "green")[0]["mean"] == "0.000000"
