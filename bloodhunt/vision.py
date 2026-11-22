"""Seeing: screen capture and template matching."""
import json

import cv2
import mss
import numpy as np

from . import settings as cfg
from .common import imread, log, rel

KINDS = ("click", "ingame", "stop", "routine")
PREFIXES = "click_, ingame, stop_ or routine_"


def shrink(img):
    return cv2.resize(img, None, fx=cfg.MATCH_SCALE, fy=cfg.MATCH_SCALE, interpolation=cv2.INTER_AREA)


def kind_of(name):
    return next((k for k in KINDS if name.lower().startswith(k)), None)


class Template:
    def __init__(self, path, img):
        self.name = path.stem
        self.kind = kind_of(self.name)
        self.h, self.w = img.shape[:2]
        self.small = shrink(img)
        self.contrast = max(float(self.small.std()), 1.0)
        self.spot = None     # (x, y, w, h) on screen where it was cropped from (from NAME.json)
        self.screen = None   # (width, height) of the screenshot it was cropped from
        side = path.with_suffix(".json")
        if side.exists():
            try:
                d = json.loads(side.read_text(encoding="utf-8"))
                self.spot = (int(d["x"]), int(d["y"]), int(d["w"]), int(d["h"]))
                if "screen_w" in d:
                    self.screen = (int(d["screen_w"]), int(d["screen_h"]))
            except (ValueError, KeyError, TypeError, OSError):
                log(f"couldn't read {rel(side)} - searching the whole screen for {self.name}")

    @property
    def locked(self):
        return self.spot is not None and cfg.SEARCH_MARGIN is not None


def load_templates(folder):
    out = []
    for p in sorted(folder.glob("*.png")):
        if not kind_of(p.stem):
            log(f"ignoring {rel(p)}: name must start with {PREFIXES}")
            continue
        img = imread(p)
        if img is None:
            log(f"couldn't read {rel(p)}")
            continue
        if min(img.shape[:2]) * cfg.MATCH_SCALE < 6:
            log(f"ignoring {rel(p)}: too small, crop a bigger area")
            continue
        out.append(Template(p, img))
    return out


def warn_size(templates, frame):
    """Images only match at the size they were cropped at, so a resolution change breaks them."""
    h, w = frame.shape[:2]
    bad = [t.name for t in templates if t.screen and t.screen != (w, h)]
    if bad:
        log(f"WARNING: the screen is {w}x{h} but {', '.join(bad)} were cropped from a different-sized "
            "screenshot. Re-crop them, or set the game back to the resolution you cropped at.")
    return not bad


def find(small_frame, t):
    """Best spot for template t in a shrunk frame -> (score 0-1, (x, y) centre in full-size pixels,
    contrast vs the template: about 1.0 normally, lower when greyed out / behind a translucent layer).
    Locked templates are only searched for around the spot they were cropped from."""
    ox = oy = 0
    if t.locked:
        sx, sy, sw, sh = t.spot
        m, s = cfg.SEARCH_MARGIN, cfg.MATCH_SCALE
        fh, fw = small_frame.shape[:2]
        ox = max(0, int((sx - m) * s))
        oy = max(0, int((sy - m) * s))
        x1 = min(fw, int((sx + sw + m) * s) + 1)
        y1 = min(fh, int((sy + sh + m) * s) + 1)
        small_frame = small_frame[oy:y1, ox:x1]
    fh, fw = small_frame.shape[:2]
    th, tw = t.small.shape[:2]
    if th > fh or tw > fw:
        return 0.0, None, 0.0
    res = cv2.matchTemplate(small_frame, t.small, cv2.TM_CCOEFF_NORMED)
    res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
    _, score, _, (x, y) = cv2.minMaxLoc(res)
    contrast = float(small_frame[y:y + th, x:x + tw].std()) / t.contrast
    centre = (int((ox + x + tw / 2) / cfg.MATCH_SCALE), int((oy + y + th / 2) / cfg.MATCH_SCALE))
    return float(score), centre, contrast


def best(small_frame, templates, skip_dimmed=False):
    """Highest-scoring template above the threshold -> (template, score, pos), or None."""
    top = None
    for t in templates:
        score, pos, contrast = find(small_frame, t)
        if score < cfg.MATCH_THRESHOLD or (skip_dimmed and contrast < cfg.CLICK_MIN_CONTRAST):
            continue
        if top is None or score > top[1]:
            top = (t, score, pos)
    return top


def click_point(t, pos, click_at) -> tuple[int, int]:
    """Where to click for template t: its fixed spot from the profile's click_at, else the match centre."""
    return click_at.get(t.name.lower(), pos)


def report(frame, templates, click_at):
    """Print every template's score on this frame -> [(template, score, pos, counts as a match)]."""
    small = shrink(frame)
    rows = []
    for t in templates:
        score, pos, contrast = find(small, t)
        found = score >= cfg.MATCH_THRESHOLD
        dimmed = t.kind == "click" and found and contrast < cfg.CLICK_MIN_CONTRAST
        rows.append((t, score, pos, found and not dimmed))
        mark = "DIMMED" if dimmed else ("MATCH " if found else "  -   ")
        notes = [f"at {pos[0]},{pos[1]}" if pos else "(bigger than its search area?)"]
        if dimmed:
            notes.append(f"contrast {contrast:.2f}: looks greyed out, won't be clicked")
        elif found and t.kind == "click":
            cx, cy = click_point(t, pos, click_at)
            notes.append(f"-> clicks {cx},{cy}" + (" (fixed spot)" if t.name.lower() in click_at else ""))
        if not t.locked:
            notes.append("[no .json: searching the whole screen]")
        print(f"   {t.name:<26} {score:5.2f}  {mark}  {'  '.join(notes)}")
    return rows


class Screen:
    def __init__(self):
        self.sct = (getattr(mss, "MSS", None) or mss.mss)()   # mss 10 renamed mss.mss to mss.MSS
        # Always the primary monitor: pydirectinput clicks only reach that one. The primary is the
        # monitor whose top-left is 0,0. mss doesn't reliably list it first (monitors[1]).
        self.mon = next((m for m in self.sct.monitors[1:] if m["left"] == 0 and m["top"] == 0),
                        self.sct.monitors[1])

    @property
    def size(self):
        return self.mon["width"], self.mon["height"]

    def grab(self):
        return cv2.cvtColor(np.array(self.sct.grab(self.mon)), cv2.COLOR_BGRA2BGR)

    def to_screen(self, pos):
        return self.mon["left"] + pos[0], self.mon["top"] + pos[1]
