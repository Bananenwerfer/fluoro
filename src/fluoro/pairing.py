"""Find white-light/fluorescence image pairs in one folder by file name: <name>_WL.<ext> + <name>_FL.<ext>."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
EIGHT_BIT_MODES = {"L", "P", "RGB", "RGBA", "LA"}


@dataclass(frozen=True)
class Pair:
    name: str
    wl: Path
    fl: Path


@dataclass(frozen=True)
class Problem:
    name: str
    files: tuple[Path, ...]
    reason: str


@dataclass
class Scan:
    pairs: list[Pair]
    problems: list[Problem]


def natural_key(text: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def _split(stem: str, wl_suffix: str, fl_suffix: str):
    for role, suf in (("wl", wl_suffix), ("fl", fl_suffix)):
        tail = "_" + suf
        if len(stem) > len(tail) and stem.lower().endswith(tail.lower()):
            return stem[: -len(tail)], role
    return None


def _info(path: Path):
    with Image.open(path) as im:
        return im.size, im.mode


def scan_folder(folder, wl_suffix: str = "WL", fl_suffix: str = "FL") -> Scan:
    if not wl_suffix or not fl_suffix or wl_suffix.lower() == fl_suffix.lower():
        raise ValueError("white-light and fluorescence suffixes must be different and not empty")
    groups: dict[str, dict[str, list[Path]]] = {}
    for p in sorted(Path(folder).iterdir()):
        if not p.is_file() or p.name.startswith(".") or p.suffix.lower() not in EXTENSIONS:
            continue
        hit = _split(p.stem, wl_suffix, fl_suffix)
        if hit:
            groups.setdefault(hit[0], {"wl": [], "fl": []})[hit[1]].append(p)

    pairs, problems = [], []
    for name in sorted(groups, key=natural_key):
        g = groups[name]
        files = tuple(g["wl"] + g["fl"])
        if len(g["wl"]) > 1 or len(g["fl"]) > 1:
            problems.append(Problem(name, files, "more than one white-light or fluorescence image with this name"))
            continue
        if not g["wl"]:
            problems.append(Problem(name, files, f"no white-light image (*_{wl_suffix})"))
            continue
        if not g["fl"]:
            problems.append(Problem(name, files, f"no fluorescence image (*_{fl_suffix})"))
            continue
        wl, fl = g["wl"][0], g["fl"][0]
        try:
            (s1, m1), (s2, m2) = _info(wl), _info(fl)
        except OSError as e:
            problems.append(Problem(name, files, f"cannot be read ({e})"))
            continue
        if m1 not in EIGHT_BIT_MODES or m2 not in EIGHT_BIT_MODES:
            problems.append(Problem(name, files, "only 8-bit images are supported (16-bit or float found)"))
        elif s1 != s2:
            problems.append(Problem(name, files,
                                    f"image sizes differ (white light {s1[0]}x{s1[1]}, fluorescence {s2[0]}x{s2[1]})"))
        else:
            pairs.append(Pair(name, wl, fl))
    return Scan(pairs, problems)
