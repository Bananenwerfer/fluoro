import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import csv

import pytest

from fluoro.app import MainWindow
from fluoro.store import RESULTS


def rows(folder):
    with open(folder / RESULTS, newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_open_folder_lists_pairs(win, pair_folder):
    win.open_folder(pair_folder)
    assert [p.name for p in win.pairs] == ["Kidney2", "Kidney10", "Liver"]
    assert win.index == 0 and win.mask.any()


def test_blind_mode_hides_fluorescence_until_approval(win, pair_folder):
    win.open_folder(pair_folder)
    assert win.blind.isChecked() and not win.fl_button.isEnabled()
    win.set_view("fl")
    assert win.view == "wl"
    win.approve()
    assert win.fl_button.isEnabled() and "Mean" in win.values.text()


def test_approve_writes_csv_and_channel_change_rewrites(win, pair_folder):
    win.open_folder(pair_folder)
    win.approve()
    r = rows(pair_folder)
    assert r[0]["name"] == "Kidney2" and r[0]["blind"] == "true"
    win.channel_box.setCurrentText("green")
    assert rows(pair_folder)[0]["mean"] == "0.000000"


def test_painting_marks_edited_and_unapproves(win, pair_folder):
    win.open_folder(pair_folder)
    win.approve()
    win.canvas.tool = "eraser"
    assert win.canvas.paint_at(160, 120)
    win.canvas.edited.emit()
    assert win.edited and not win.approved and not win.fl_button.isEnabled()


def test_blind_off_records_not_blind(win, pair_folder):
    win.open_folder(pair_folder)
    win.blind.setChecked(False)
    win.set_view("fl")
    win.approve()
    assert rows(pair_folder)[0]["blind"] == "false"


def test_skip_moves_on_and_persists(win, pair_folder):
    win.open_folder(pair_folder)
    win.skip()
    assert win.index == 1 and win.status["Kidney2"] == "skipped"


def test_reopen_restores_approval(win, pair_folder, qtbot):
    win.open_folder(pair_folder)
    win.approve()
    w2 = MainWindow()
    qtbot.addWidget(w2)
    w2.open_folder(pair_folder)
    assert w2.status["Kidney2"] == "approved" and w2.index == 1


def test_show_results_enabled_after_open(win, pair_folder):
    assert not win.results_action.isEnabled()
    win.open_folder(pair_folder)
    assert win.results_action.isEnabled() and "fluoro_results.csv" in win.progress.text()


def test_missing_folder_shows_message(win, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr("fluoro.app.QMessageBox.warning", lambda *a: shown.append(a))
    win.open_folder(tmp_path / "does_not_exist")
    assert shown and win.folder is None


def test_help(capsys, monkeypatch):
    from fluoro.__main__ import main
    monkeypatch.setattr("sys.argv", ["fluoro", "--help"])
    assert main() == 0 and "usage: fluoro" in capsys.readouterr().out
