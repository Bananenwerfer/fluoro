"""Main window: open a folder of image pairs, review the ROI on the white-light image, approve and measure.

All analysis decisions live in pairing/roi/measure/store; this module only displays and dispatches.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton, QRadioButton, QSlider, QVBoxLayout, QWidget)

from . import __version__
from .canvas import ImageCanvas
from .measure import CHANNELS, measure, read_rgb
from .pairing import scan_folder
from .roi import propose_roi
from .store import (RESULTS, RoiMismatchError, load_approval, load_skipped, save_approval, set_skipped,
                    write_results)

COLORS = {"approved": "#1D9E75", "skipped": "#888780", "problem": "#EF9F27", "error": "#E24B4A"}


class SettingsDialog(QDialog):
    def __init__(self, wl: str, fl: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.wl, self.fl = QLineEdit(wl), QLineEdit(fl)
        form = QFormLayout(self)
        form.addRow("White-light suffix", self.wl)
        form.addRow("Fluorescence suffix", self.fl)
        form.addRow(QLabel("Files are paired by name: <name>_<suffix>.jpg/.png/.tif"))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"fluoro {__version__}")
        self.folder: Path | None = None
        self.pairs, self.status, self.index = [], {}, -1
        self.wl_suffix, self.fl_suffix = "WL", "FL"
        self.wl = self.fl = self.mask = None
        self.factor, self.otsu, self.threshold = 1.0, 0.0, 0.0
        self.edited = self.approved = self.fl_seen = False
        self.view = "wl"
        self._build()

    # ---- layout ------------------------------------------------------------------------------
    def _build(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.addAction("Open folder", self.open_folder)
        self.results_action = tb.addAction("Show results", self.show_results)
        self.results_action.setEnabled(False)
        self.results_action.setToolTip("Open the image folder, which contains fluoro_results.csv and fluoro_rois/")
        tb.addAction("Settings", self.settings)

        self.list = QListWidget()
        self.list.setFixedWidth(260)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.currentRowChanged.connect(self._row_clicked)
        self.progress = QLabel("Open a folder to start.")
        self.progress.setWordWrap(True)
        left = QVBoxLayout()
        left.addWidget(self.progress)
        left.addWidget(self.list)

        self.canvas = ImageCanvas()
        self.canvas.edited.connect(self._mask_edited)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(50, 150)
        self.slider.setValue(100)
        self.slider.valueChanged.connect(self._threshold_changed)
        self.slider_label = QLabel("Threshold factor 1.00")
        self.brush, self.eraser = QRadioButton("Brush (B)"), QRadioButton("Eraser (E)")
        self.brush.setChecked(True)
        group = QButtonGroup(self)
        for b in (self.brush, self.eraser):
            group.addButton(b)
            b.toggled.connect(self._tool_changed)
        self.size = QSlider(Qt.Orientation.Horizontal)
        self.size.setRange(2, 200)
        self.size.setValue(20)
        self.size.valueChanged.connect(lambda v: setattr(self.canvas, "radius", v))
        reset, clear = QPushButton("Reset to proposal"), QPushButton("Clear")
        reset.clicked.connect(self._reset)
        clear.clicked.connect(self._clear)

        self.wl_button, self.fl_button = QPushButton("White light"), QPushButton("Fluorescence")
        self.wl_button.clicked.connect(lambda: self.set_view("wl"))
        self.fl_button.clicked.connect(lambda: self.set_view("fl"))
        self.channel_box = QComboBox()
        self.channel_box.addItems(CHANNELS)
        self.channel_box.currentTextChanged.connect(self._channel_changed)
        self.blind = QCheckBox("Blind mode")
        self.blind.setChecked(True)
        self.blind.setToolTip("Hide the fluorescence image and values until the ROI is approved")
        blind_hint = QLabel("Fluorescence and values stay hidden until approval.")
        blind_hint.setWordWrap(True)
        blind_hint.setStyleSheet("color: gray")
        self.blind.toggled.connect(self._blind_changed)
        self.approve_button, skip = QPushButton("Approve (Enter)"), QPushButton("Skip")
        self.approve_button.clicked.connect(self.approve)
        skip.clicked.connect(self.skip)
        self.values = QLabel("")
        self.values.setWordWrap(True)

        right = QVBoxLayout()
        for w in (QLabel("<b>ROI</b>"), self.slider_label, self.slider, self.brush, self.eraser, QLabel("Brush size"),
                  self.size, reset, clear, QLabel("<b>View</b>"), self.wl_button, self.fl_button,
                  QLabel("<b>Measurement</b>"), QLabel("Channel"), self.channel_box, self.blind,
                  blind_hint, self.approve_button, skip, self.values):
            right.addWidget(w)
        right.addStretch()
        panel = QWidget()
        panel.setLayout(right)
        panel.setFixedWidth(270)

        central = QWidget()
        row = QHBoxLayout(central)
        lw = QWidget()
        lw.setLayout(left)
        row.addWidget(lw)
        row.addWidget(self.canvas, 1)
        row.addWidget(panel)
        self.setCentralWidget(central)

        for key, fn in (("Return", self.approve), ("Enter", self.approve), ("Right", lambda: self.go(self.index + 1)),
                        ("Left", lambda: self.go(self.index - 1)), ("B", lambda: self.brush.setChecked(True)),
                        ("E", lambda: self.eraser.setChecked(True))):
            QShortcut(QKeySequence(key), self, activated=fn)
        self._update_panel()

    # ---- folder and navigation ---------------------------------------------------------------
    def open_folder(self, folder=None):
        if folder is None:
            folder = QFileDialog.getExistingDirectory(self, "Open folder with image pairs")
            if not folder:
                return
        if not Path(folder).is_dir():
            QMessageBox.warning(self, "Open folder", f"Folder not found:\n{folder}")
            return
        self.folder = Path(folder)
        scan = scan_folder(self.folder, self.wl_suffix, self.fl_suffix)
        self.pairs, self.status, skipped = scan.pairs, {}, load_skipped(self.folder)
        for p in self.pairs:
            try:
                a = load_approval(self.folder, p)
                self.status[p.name] = "approved" if a else ("skipped" if p.name in skipped else "open")
            except RoiMismatchError:
                self.status[p.name] = "error"
        self.list.blockSignals(True)
        self.list.clear()
        for p in self.pairs:
            self.list.addItem(QListWidgetItem(p.name))
        for pr in scan.problems:
            item = QListWidgetItem(f"{pr.name}: {pr.reason}")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setForeground(QColor(COLORS["problem"]))
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.setWindowTitle(f"fluoro {__version__}  {self.folder}")
        self.results_action.setEnabled(True)
        self.index = -1
        self._repaint_list()
        if not self.pairs:
            self.progress.setText(f"No image pairs found (expected <name>_{self.wl_suffix} and "
                                  f"<name>_{self.fl_suffix}).")
            return
        self.go(next((i for i, p in enumerate(self.pairs) if self.status[p.name] == "open"), 0))

    def go(self, i: int):
        if not self.pairs or not 0 <= i < len(self.pairs):
            return
        self.index = i
        p = self.pairs[i]
        self.list.blockSignals(True)
        self.list.setCurrentRow(i)
        self.list.blockSignals(False)
        self.wl, self.fl = read_rgb(p.wl), read_rgb(p.fl)
        approval = None
        if self.status[p.name] == "approved":
            approval = load_approval(self.folder, p)
        if approval:
            m = approval.meta
            self.factor, self.otsu, self.threshold = m["threshold_factor"], m["otsu"], m["threshold"]
            self.mask, self.edited, self.approved, self.fl_seen = approval.mask.copy(), m["edited"], True, True
        else:
            self.factor, self.approved, self.fl_seen = 1.0, False, False
            self._propose()
        self.slider.blockSignals(True)
        self.slider.setValue(round(self.factor * 100))
        self.slider.blockSignals(False)
        self.slider_label.setText(f"Threshold factor {self.factor:.2f}")
        self.view = "wl"
        self.canvas.editable = self.canvas.fill = True
        self.canvas.set_image(self.wl)
        self.canvas.set_mask(self.mask)
        self._update_panel()

    def _row_clicked(self, row: int):
        if 0 <= row < len(self.pairs) and row != self.index:
            self.go(row)

    # ---- ROI editing -------------------------------------------------------------------------
    def _propose(self):
        prop = propose_roi(self.wl, self.factor)
        self.otsu, self.threshold, self.mask, self.edited = prop.otsu, prop.threshold, prop.mask.copy(), False
        self.canvas.set_mask(self.mask)

    def _changed(self):
        self.approved = False
        if self.view == "fl" and self.blind.isChecked():
            self.set_view("wl")
        self._update_panel()

    def _threshold_changed(self, v: int):
        if self.wl is None:
            return
        self.factor = v / 100
        self.slider_label.setText(f"Threshold factor {self.factor:.2f}")
        self._propose()
        self._changed()

    def _reset(self):
        if self.wl is not None:
            self._propose()
            self._changed()

    def _clear(self):
        if self.mask is not None:
            self.mask[:] = False
            self.edited = True
            self.canvas.refresh_overlay()
            self._changed()

    def _mask_edited(self):
        self.edited = True
        self._changed()

    def _tool_changed(self):
        self.canvas.tool = "brush" if self.brush.isChecked() else "eraser"

    # ---- view, approval, measurement ---------------------------------------------------------
    def fl_allowed(self) -> bool:
        return self.fl is not None and (self.approved or not self.blind.isChecked())

    def set_view(self, v: str):
        if v == "fl" and not self.fl_allowed():
            return
        self.view = v
        if v == "fl" and not self.approved:
            self.fl_seen = True
        self.canvas.editable = self.canvas.fill = v == "wl"
        self.canvas.refresh_overlay()
        self.canvas.set_image(self.fl if v == "fl" else self.wl, fit=False)
        self._update_panel()

    def approve(self):
        if self.index < 0:
            return
        if self.mask is None or not self.mask.any():
            QMessageBox.information(self, "Approve", "The ROI is empty. Draw a region first.")
            return
        p = self.pairs[self.index]
        save_approval(self.folder, p, self.mask, threshold_factor=self.factor, otsu=self.otsu,
                      threshold=self.threshold, edited=self.edited, blind=not self.fl_seen,
                      approved_at=dt.datetime.now().isoformat(timespec="seconds"))
        self.status[p.name], self.approved = "approved", True
        self._write_results()
        self._repaint_list()
        self._update_panel()

    def skip(self):
        if self.index < 0:
            return
        p = self.pairs[self.index]
        if self.status[p.name] != "approved":
            set_skipped(self.folder, p.name, True)
            self.status[p.name] = "skipped"
        self._repaint_list()
        self.go(self.index + 1)

    def channel(self) -> str:
        return self.channel_box.currentText()

    def _channel_changed(self, _):
        if self.folder:
            self._write_results()
        self._update_panel()

    def _blind_changed(self, _):
        if self.blind.isChecked() and self.view == "fl" and not self.approved:
            self.set_view("wl")
        self._update_panel()

    def _write_results(self):
        try:
            write_results(self.folder, self.pairs, self.channel())
        except PermissionError:
            QMessageBox.warning(self, "Results", f"{RESULTS} could not be written. Close it in other programs "
                                                 "(e.g. Excel) and approve again.")

    def show_results(self):
        if self.folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder)))

    def settings(self):
        d = SettingsDialog(self.wl_suffix, self.fl_suffix, self)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        wl, fl = d.wl.text().strip(), d.fl.text().strip()
        if not wl or not fl or wl.lower() == fl.lower():
            QMessageBox.warning(self, "Settings", "The two suffixes must be different and not empty.")
            return
        self.wl_suffix, self.fl_suffix = wl, fl
        if self.folder:
            self.open_folder(self.folder)

    # ---- display -----------------------------------------------------------------------------
    def _repaint_list(self):
        for i, p in enumerate(self.pairs):
            c = COLORS.get(self.status[p.name])
            self.list.item(i).setForeground(QColor(c) if c else self.palette().text().color())
        n = sum(s == "approved" for s in self.status.values())
        self.progress.setText(f"{n} of {len(self.pairs)} approved<br><span style='color: gray'>Results: "
                              f"{RESULTS} in the image folder (Show results)</span>")

    def _update_panel(self):
        self.fl_button.setEnabled(self.fl_allowed())
        has = self.index >= 0
        self.approve_button.setEnabled(has)
        if has and self.status[self.pairs[self.index].name] == "error" and not self.approved:
            self.values.setText("The saved ROI does not match the images any more. Approve again to replace it.")
        elif self.approved:
            m = measure(self.fl, self.mask, self.channel())
            warn = "<br><b>Warning:</b> more than 0.1 % saturated pixels." if m["flag_saturation"] else ""
            self.values.setText(f"Mean {m['mean']:.2f}<br>Min {m['min']}  Max {m['max']}<br>"
                                f"Area {m['area_px']} px<br>Saturated {m['n_saturated']} px{warn}")
        else:
            self.values.setText("Values appear after approval." if has else "")
