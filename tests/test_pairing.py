import numpy as np
import pytest
from PIL import Image

from conftest import write_pair
from fluoro.pairing import scan_folder


def test_pairs_found_and_naturally_sorted(pair_folder):
    s = scan_folder(pair_folder)
    assert [p.name for p in s.pairs] == ["Kidney2", "Kidney10", "Liver"]
    assert s.problems == []


def test_suffix_case_insensitive_and_custom(tmp_path):
    write_pair(tmp_path, "A", wl_suffix="wl", fl_suffix="Fl")
    write_pair(tmp_path, "B", wl_suffix="white", fl_suffix="fluo")
    assert [p.name for p in scan_folder(tmp_path).pairs] == ["A"]
    assert [p.name for p in scan_folder(tmp_path, "white", "fluo").pairs] == ["B"]


def test_missing_partner_reported(tmp_path):
    write_pair(tmp_path, "A")
    (tmp_path / "A_FL.png").unlink()
    s = scan_folder(tmp_path)
    assert s.pairs == [] and "no fluorescence image" in s.problems[0].reason


def test_size_mismatch_reported(tmp_path):
    write_pair(tmp_path, "A")
    Image.fromarray(np.zeros((10, 10, 3), np.uint8)).save(tmp_path / "A_FL.png")
    assert "sizes differ" in scan_folder(tmp_path).problems[0].reason


def test_16bit_rejected(tmp_path):
    write_pair(tmp_path, "A")
    Image.fromarray(np.zeros((240, 320), np.uint16)).save(tmp_path / "A_FL.png")
    assert "8-bit" in scan_folder(tmp_path).problems[0].reason


def test_duplicate_reported(tmp_path):
    write_pair(tmp_path, "A")
    write_pair(tmp_path, "A", ext="jpg")
    assert "more than one" in scan_folder(tmp_path).problems[0].reason


def test_unrelated_files_ignored(pair_folder):
    (pair_folder / "notes.txt").write_text("x")
    Image.fromarray(np.zeros((5, 5, 3), np.uint8)).save(pair_folder / "overview.png")
    assert len(scan_folder(pair_folder).pairs) == 3


def test_equal_suffixes_rejected(tmp_path):
    with pytest.raises(ValueError):
        scan_folder(tmp_path, "WL", "wl")
