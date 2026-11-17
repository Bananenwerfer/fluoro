"""Everything fluoro saves lives in the opened folder: fluoro_rois/ (masks, metadata, skipped list) and
fluoro_results.csv (one row per approved pair, rewritten completely after every change)."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from . import __version__
from .measure import measure, read_rgb
from .pairing import Pair

ROI_DIR = "fluoro_rois"
RESULTS = "fluoro_results.csv"
SKIPPED = "skipped.txt"
CSV_FIELDS = ["name", "wl_file", "fl_file", "channel", "mean", "min", "max", "area_px", "n_saturated",
              "flag_saturation", "blind", "threshold_factor", "edited", "approved_at", "fluoro_version"]


class RoiMismatchError(Exception):
    """A saved ROI no longer matches its images or was modified."""


@dataclass
class Approval:
    mask: np.ndarray
    meta: dict


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _paths(folder, name):
    d = Path(folder) / ROI_DIR
    return d / f"{name}.png", d / f"{name}.json"


def save_approval(folder, pair: Pair, mask, *, threshold_factor, otsu, threshold, edited, blind,
                  approved_at) -> Approval:
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        raise ValueError("an empty ROI cannot be approved")
    png, js = _paths(folder, pair.name)
    png.parent.mkdir(exist_ok=True)
    Image.fromarray(mask.astype(np.uint8) * 255).save(png, optimize=False)
    meta = {"name": pair.name, "wl_file": pair.wl.name, "fl_file": pair.fl.name,
            "wl_sha256": sha256(pair.wl), "fl_sha256": sha256(pair.fl), "mask_sha256": sha256(png),
            "area_px": int(mask.sum()), "threshold_factor": float(threshold_factor), "otsu": float(otsu),
            "threshold": float(threshold), "edited": bool(edited), "blind": bool(blind),
            "approved_at": approved_at, "fluoro_version": __version__}
    js.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    set_skipped(folder, pair.name, False)
    return Approval(mask, meta)


def load_approval(folder, pair: Pair) -> Approval | None:
    png, js = _paths(folder, pair.name)
    if not png.exists() and not js.exists():
        return None
    if not (png.exists() and js.exists()):
        raise RoiMismatchError(f"saved ROI incomplete: {pair.name}")
    meta = json.loads(js.read_text(encoding="utf-8"))
    for key, path in (("mask_sha256", png), ("wl_sha256", pair.wl), ("fl_sha256", pair.fl)):
        if sha256(path) != meta[key]:
            raise RoiMismatchError(f"{path.name} changed after the ROI was approved")
    with Image.open(png) as im:
        mask = np.asarray(im.convert("L")) > 127
    return Approval(mask, meta)


def load_skipped(folder) -> set[str]:
    f = Path(folder) / ROI_DIR / SKIPPED
    return {l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip()} if f.exists() else set()


def set_skipped(folder, name: str, skipped: bool) -> None:
    names = load_skipped(folder)
    if (name in names) == skipped:
        return
    names = names | {name} if skipped else names - {name}
    d = Path(folder) / ROI_DIR
    d.mkdir(exist_ok=True)
    (d / SKIPPED).write_text("".join(f"{n}\n" for n in sorted(names)), encoding="utf-8")


def write_results(folder, pairs: list[Pair], channel: str) -> list[dict]:
    rows = []
    for p in pairs:
        try:
            a = load_approval(folder, p)
        except RoiMismatchError:
            continue
        if a is None:
            continue
        m = measure(read_rgb(p.fl), a.mask, channel)
        rows.append({"name": p.name, "wl_file": p.wl.name, "fl_file": p.fl.name, "channel": channel,
                     "mean": f"{m['mean']:.6f}", "min": m["min"], "max": m["max"], "area_px": m["area_px"],
                     "n_saturated": m["n_saturated"], "flag_saturation": str(m["flag_saturation"]).lower(),
                     "blind": str(a.meta["blind"]).lower(), "threshold_factor": a.meta["threshold_factor"],
                     "edited": str(a.meta["edited"]).lower(), "approved_at": a.meta["approved_at"],
                     "fluoro_version": a.meta["fluoro_version"]})
    path = Path(folder) / RESULTS
    tmp = path.with_name(RESULTS + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)
    return rows
