"""Seeing: screen capture and template matching."""
import json

import cv2
import mss
import numpy as np

from . import settings as cfg
from . import winapi
from .common import imread, log, rel

KINDS = ("click", "ingame", "stop", "routine")
PREFIXES = "click_, ingame, stop_ or routine_"


def shrink(img):
    return cv2.resize(img, None, fx=cfg.MATCH_SCALE, fy=cfg.MATCH_SCALE, interpolation=cv2.INTER_AREA)


def kind_of(name):
    return next((k for k in KINDS if name.lower().startswith(k)), None)


class Template:
    def __init__(self, name, img, spot=None, screen=None, resized=False):
        self.name = name
        self.resized = resized   # resized from the size it was cropped at (uses MATCH_THRESHOLD_SCALED)
        self.kind = kind_of(self.name)
        self.h, self.w = img.shape[:2]
        self.small = shrink(img)
        self.contrast = max(float(self.small.std()), 1.0)
        self.spot = spot      # (x, y, w, h) on screen where it was cropped from (from NAME.json)
        self.screen = screen  # (width, height) of the screen it's for

    @property
    def locked(self):
        return self.spot is not None and cfg.SEARCH_MARGIN is not None


def read_spot(side):
    """NAME.json -> (spot (x, y, w, h), screen (w, h)), either None if missing or unreadable."""
    if not side.exists():
        return None, None
    try:
        d = json.loads(side.read_text(encoding="utf-8"))
        spot = (int(d["x"]), int(d["y"]), int(d["w"]), int(d["h"]))
        return spot, ((int(d["screen_w"]), int(d["screen_h"])) if "screen_w" in d else None)
    except (ValueError, KeyError, TypeError, OSError):
        log(f"couldn't read {rel(side)} - searching the whole screen for {side.stem}")
        return None, None


def resample(img, spot, sx, sy):
    """Template img, cropped at spot (x, y, w, h), as it would look on a screen scaled by sx, sy
    -> (image, new spot). It's sampled exactly onto the new screen's pixel grid, starting on an even
    pixel like `crop` does (matching runs at half size). A plain resize would leave the content up to a
    pixel out of step with the real screen, which costs small images a lot of score (0.69 vs 0.99 for the
    SPACE box at 1280x720, tested on resized 1080p screenshots)."""
    x0, y0, w0, h0 = spot
    x, y = int(x0 * sx) // 2 * 2, int(y0 * sy) // 2 * 2
    tw, th = int((x0 + w0) * sx) - x, int((y0 + h0) * sy) - y
    if sx < 1 or sy < 1:                   # soften first, so shrinking doesn't alias
        img = cv2.GaussianBlur(img, (0, 0), 0.5 * max(1 / sx - 1, 0.01) ** 0.5,
                               sigmaY=0.5 * max(1 / sy - 1, 0.01) ** 0.5)
    m = np.array([[1 / sx, 0, (x + 0.5) / sx - 0.5 - x0], [0, 1 / sy, (y + 0.5) / sy - 0.5 - y0]],
                 dtype=np.float32)
    out = cv2.warpAffine(img, m, (tw, th), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                         borderMode=cv2.BORDER_REPLICATE)
    return out, (x, y, tw, th)


def load_templates(folder, size=None, base=None):
    """Every template in folder. With size (the screen's (w, h)): each one cropped at another size is
    resized to fit it, along with where it's searched for. A template's own size comes from its NAME.json,
    else base (the profile's size)."""
    out = []
    for p in sorted(folder.glob("*.png")):
        if not kind_of(p.stem):
            log(f"ignoring {rel(p)}: name must start with {PREFIXES}")
            continue
        img = imread(p)
        if img is None:
            log(f"couldn't read {rel(p)}")
            continue
        spot, screen = read_spot(p.with_suffix(".json"))
        cropped_at = screen or base
        too_small = ", crop a bigger area"
        resized = size is not None and cropped_at is not None and tuple(size) != tuple(cropped_at)
        if size is not None and cropped_at is not None and resized:
            if spot is None:
                log(f"ignoring {rel(p)}: it has no .json, so it can't be resized for {size[0]}x{size[1]}")
                continue
            img, spot = resample(img, spot, size[0] / cropped_at[0], size[1] / cropped_at[1])
            screen = (int(size[0]), int(size[1]))
            too_small = f" at {size[0]}x{size[1]}, crop it on this screen size"
        if min(img.shape[:2]) * cfg.MATCH_SCALE < 6:
            log(f"ignoring {rel(p)}: too small{too_small}")
            continue
        out.append(Template(p.stem, img, spot, screen, resized))
    return out


def threshold(t):
    """The score template t needs to count as a match. Lower for an image resized to another screen size:
    the game draws text at whole font sizes, so a resized copy never matches as closely as a crop."""
    return cfg.MATCH_THRESHOLD_SCALED if t.resized else cfg.MATCH_THRESHOLD


def warn_size(templates, frame):
    """Images only match at the size they're loaded for. The profile is fitted to the screen, so this only
    fires for an image cropped at another size than the rest of its profile."""
    h, w = frame.shape[:2]
    bad = [f"{t.name} ({t.screen[0]}x{t.screen[1]})" for t in templates if t.screen and t.screen != (w, h)]
    if bad:
        log(f"WARNING: the screen is {w}x{h}, but these images are sized for another screen and won't match: "
            f"{', '.join(bad)}. Crop them again from a screenshot at the profile's size.")
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
        if score < threshold(t) or (skip_dimmed and contrast < cfg.CLICK_MIN_CONTRAST):
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
        found = score >= threshold(t)
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
        if t.resized:
            notes.append(f"(resized: {threshold(t):g} counts)")
        print(f"   {t.name:<26} {score:5.2f}  {mark}  {'  '.join(notes)}")
    return rows


def _mss():
    return (getattr(mss, "MSS", None) or mss.mss)()   # mss 10 renamed mss.mss to mss.MSS


class Screen:
    """What the bot looks at: the game's picture, i.e. the inside of the game window, on whichever monitor
    it is (winapi.game_area). Positions everywhere else are in that picture's pixels; to_screen() adds
    where it is on the desktop. While the game window isn't found (not running, minimised), the main
    monitor, as before."""

    def __init__(self):
        self.sct = _mss()
        self.desktop = winapi.virtual_screen()
        self.mon = {"left": 0, "top": 0, "width": 0, "height": 0}
        self.refresh()

    def _main_monitor(self):
        # The monitor whose top-left is 0,0. mss doesn't reliably list it first (monitors[1]).
        return next((m for m in self.sct.monitors[1:] if m["left"] == 0 and m["top"] == 0),
                    self.sct.monitors[1])

    def refresh(self):
        """Follow the game: re-read where its picture is and how big. It can move to another monitor, or
        change size (a game in exclusive fullscreen switches the display to its own resolution when it comes
        to the front, and Windows switches back when you alt-tab out). Cheap (a few window and
        GetSystemMetrics calls), so it's called before each screenshot -> True if the size changed."""
        desktop = winapi.virtual_screen()
        if desktop != self.desktop:        # a monitor changed: mss re-reads the layout
            self.sct.close()
            self.sct, self.desktop = _mss(), desktop
        old = self.size
        area = winapi.game_area()
        self.mon = ({"left": area[0], "top": area[1], "width": area[2], "height": area[3]} if area
                    else dict(self._main_monitor()))
        return self.size != old

    @property
    def size(self):
        return self.mon["width"], self.mon["height"]

    def grab(self):
        return cv2.cvtColor(np.array(self.sct.grab(self.mon)), cv2.COLOR_BGRA2BGR)

    def to_screen(self, pos):
        """A position in the game's picture -> desktop pixels (what inputs.click takes)."""
        return self.mon["left"] + pos[0], self.mon["top"] + pos[1]

    def from_screen(self, pos):
        """Desktop pixels -> a position in the game's picture."""
        return pos[0] - self.mon["left"], pos[1] - self.mon["top"]
