"""Profiles: everything that depends on the screen, one folder per screen shape (aspect ratio), named
after it (16x9, 16x10, or WxH for an unusual shape). The game's UI scales with the screen, so one profile
fits every size of its shape: `fit()` resizes its images and scales its coordinates when it's loaded.

    profiles\\<name>\\profile.json   {"screen": [1920, 1080], "click_at": {...}, "routines": {...}}
    profiles\\<name>\\templates\\     NAME.png + NAME.json (where on screen it was cropped)
    profiles\\<name>\\shots\\         screenshots from `snap`
    profiles\\<name>\\routines\\<routine>\\   the screenshots each routine step was measured on

screen: the size it was cropped at. click_at and the routines' clicks are in pixels of that size.
click_at: buttons to click at a fixed spot instead of the centre of the matched image.
routines: name -> list of steps, run in order when a routine_<name>*.png template is seen. A step is
    {"name": "Smelt", "click": [x, y], "wait": 3.5, "shot": "06_selected.png", "hint": "..."}   or
    {"name": "Dismiss rewards", "key": "space", ...}   or   {"name": "Type rating", "type": "{SMELT_RATING}", ...}
  wait = seconds after the step; shot = the screenshot it was measured on (for `routine check`);
  hint = what to click, in words (shown by `routine record`). In "type", {SETTING} is typed as that
  setting's value from settings.py (the smelt rating is a setting, the same for every screen shape).
"""
import copy
import json
import math
import re
import sys

from . import inputs, routines
from . import settings as cfg
from .common import CLI, PROFILES, rel
from .vision import load_templates


class Profile:
    def __init__(self, name):
        self.name = name
        self.dir = PROFILES / name
        self.templates_dir = self.dir / "templates"
        self.shots_dir = self.dir / "shots"
        path = self.dir / "profile.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            w, h = data["screen"]
            self.screen = (int(w), int(h))
            self.click_at = {str(k).lower(): (int(v[0]), int(v[1]))
                             for k, v in data.get("click_at", {}).items()}
            self.routines = {str(r).lower(): [_step(r, i, s) for i, s in enumerate(steps, 1)]
                             for r, steps in data.get("routines", {}).items()}
        except (OSError, ValueError, KeyError, TypeError, IndexError) as e:
            sys.exit(f"Can't read {rel(path)}: {e}")
        self.base = self.screen    # the size it was cropped at; fit() changes screen, not base
        self.scale = None          # (sx, sy) once fitted to another size
        self.original = self       # the profile as saved (a fitted copy keeps pointing at it)

    def __str__(self):
        if self.scale:
            return f"{self.name} (cropped at {size_name(self.base)}, scaled to {size_name(self.screen)})"
        size = size_name(self.screen)
        return self.name if self.name == size else f"{self.name} ({size})"

    def fit(self, size):
        """This profile for a screen of `size` (same shape): click spots and routine clicks scaled, and
        templates() resizes the images as it loads them. Nothing on disk changes; the fitted copy can't
        be saved. The profile itself if it's already that size. Called on a fitted copy, it fits the saved
        profile again (no rounding piles up)."""
        src = self.original
        size = (int(size[0]), int(size[1]))
        if size == src.screen:
            return src
        if not same_shape(src.screen, size):
            sys.exit(f"Profile {src} is for {shape_label(src.screen)} screens, but yours is "
                     f"{size_name(size)} ({shape_label(size)}). The game lays its menus out differently "
                     "on another shape, so it needs its own profile: run snap (see README.md).")
        q = copy.copy(src)
        sx, sy = size[0] / src.screen[0], size[1] / src.screen[1]
        q.screen, q.scale = size, (sx, sy)
        q.click_at = {k: (round(x * sx), round(y * sy)) for k, (x, y) in src.click_at.items()}
        q.routines = {r: [dict(s, click=(round(s["click"][0] * sx), round(s["click"][1] * sy)))
                          if "click" in s else dict(s) for s in steps]
                      for r, steps in src.routines.items()}
        return q

    def routine_for(self, template_name):
        """The routine a routine_* template starts: routine_storage_full*.png -> storage_full, or None."""
        rest = template_name.lower()[len("routine"):].lstrip("_")
        found = [r for r in self.routines if rest == r or rest.startswith(r + "_")]
        return max(found, key=len) if found else None

    def routine_dir(self, routine):
        return self.dir / "routines" / routine

    def templates(self):
        """The templates, resized for this screen if the profile was fitted to another size."""
        return load_templates(self.templates_dir, self.screen if self.scale else None, self.base)

    def template_names(self):
        return {p.stem for p in self.templates_dir.glob("*.png")}

    def shots(self):
        """Screenshots, oldest first."""
        return sorted(self.shots_dir.glob("*.png"), key=lambda p: p.stat().st_mtime)

    def save(self):
        """Write profile.json, one routine step per line."""
        if self.scale:
            raise RuntimeError("a fitted profile's coordinates are scaled: save the profile itself")
        out = ["{", f'  "screen": [{self.screen[0]}, {self.screen[1]}],']
        spots = [f"    {json.dumps(k)}: [{x}, {y}]" for k, (x, y) in self.click_at.items()]
        out.append('  "click_at": {' + ("\n" + ",\n".join(spots) + "\n  " if spots else "") + "},")
        blocks = [f"    {json.dumps(r)}: [\n" + ",\n".join(f"      {_step_line(s)}" for s in steps) + "\n    ]"
                  for r, steps in self.routines.items()]
        out.append('  "routines": {' + ("\n" + ",\n".join(blocks) + "\n  " if blocks else "") + "}")
        out.append("}")
        (self.dir / "profile.json").write_text("\n".join(out) + "\n", encoding="utf-8")


def _step(routine, i, s):
    where = f"routine {routine!r}, step {i}"
    if not isinstance(s, dict):
        raise ValueError(f"{where} isn't a {{...}} entry")
    step = {"name": str(s.get("name", f"step {i}")), "wait": float(s.get("wait", 0)), "shot": s.get("shot")}
    if "click" in s:
        x, y = s["click"]
        step["click"] = (int(x), int(y))
    elif "key" in s:
        step["key"] = str(s["key"]).lower()
    elif "type" in s:
        # {SETTING} is typed as that setting's value (routines.typed), checked before each run; the rest of
        # the text is checked here.
        text = str(s["type"])
        unknown = [n for n in routines.SETTING_IN_TEXT.findall(text) if not hasattr(cfg, n)]
        bad = sorted({ch for ch in routines.SETTING_IN_TEXT.sub("", text) if not inputs.key_for(ch)})
        if not text or bad or unknown:
            raise ValueError(f"{where} can't type {text!r}" + (f": no setting {unknown[0]}" if unknown else "")
                             + (f": no single key for {bad}" if bad else "")
                             + " (lowercase letters, digits, space, unshifted symbols and {SETTING} only)")
        step["type"] = text
    else:
        raise ValueError(f'{where} needs "click": [x, y], "key": "..." or "type": "..."')
    if step["wait"] < 0:
        raise ValueError(f"{where} has a negative wait")
    if s.get("hint"):
        step["hint"] = str(s["hint"])
    return step


def _step_line(s):
    """One step as a line of profile.json, in a fixed key order, padded into columns."""
    if "click" in s:
        action = f'"click": [{s["click"][0]}, {s["click"][1]}]'
    elif "key" in s:
        action = f'"key": {json.dumps(s["key"])}'
    else:
        action = f'"type": {json.dumps(s["type"])}'
    parts = [(f'"name": {json.dumps(s["name"])}', 27), (action, 21), (f'"wait": {s["wait"]:g}', 12)]
    if s.get("shot"):
        parts.append((f'"shot": {json.dumps(s["shot"])}', 31 if s.get("hint") else 0))
    if s.get("hint"):
        parts.append((f'"hint": {json.dumps(s["hint"])}', 0))
    last = len(parts) - 1
    return "{" + " ".join(text if i == last else (text + ",").ljust(width)
                          for i, (text, width) in enumerate(parts)) + "}"


def size_name(size):
    return f"{size[0]}x{size[1]}"


# Common screen shapes, named the usual way (2560x1600 reduces to 8:5 but is called 16:10).
SHAPES = [(16, 9), (16, 10), (4, 3), (5, 4), (3, 2), (32, 9)]


def same_shape(a, b):
    return abs(a[0] / a[1] - b[0] / b[1]) < 0.01


def _shape(size):
    return next((s for s in SHAPES if same_shape(s, size)), None)


def shape_name(size):
    """The folder name for a new profile: 16x9, 16x10, ... or WxH for a shape that isn't a common one
    (ultrawides vary: 2560x1080 and 3440x1440 aren't quite the same shape)."""
    s = _shape(size)
    return f"{s[0]}x{s[1]}" if s else size_name(size)


def shape_label(size):
    s = _shape(size)
    if s:
        return f"{s[0]}:{s[1]}"
    g = math.gcd(int(size[0]), int(size[1]))
    return f"{size[0] // g}:{size[1] // g}"


def names():
    return sorted(p.parent.name for p in PROFILES.glob("*/profile.json"))


def exists(name):
    return (PROFILES / name / "profile.json").is_file()


def listing():
    found = [str(Profile(n)) for n in names()]
    return f"Profiles: {', '.join(found)}." if found else "There are no profiles yet."


def load(name):
    if not exists(name):
        sys.exit(f"There's no profile called {name!r}. {listing()}")
    return Profile(name)


def create(name, size):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        sys.exit("Profile names can only use letters, digits, - and _  (e.g. 2560x1440, laptop)")
    d = PROFILES / name
    (d / "templates").mkdir(parents=True, exist_ok=True)
    (d / "shots").mkdir(exist_ok=True)
    (d / "profile.json").write_text(json.dumps({"screen": [int(size[0]), int(size[1])]}) + "\n",
                                    encoding="utf-8")
    p = Profile(name)
    p.save()
    return p


def choose(name, size, create_new=False):
    """The profile to use on a screen of `size`, not yet fitted to it (see fit()).
    --profile NAME if given. Otherwise: a profile cropped at exactly this size, else the one for this
    screen shape (if there are several, the one with the most images, then the biggest). With none,
    create_new makes an empty one named after the shape, else it exits with what to do."""
    if name:
        if exists(name):
            return Profile(name)
        if create_new:
            return create(name, size)
        sys.exit(f"There's no profile called {name!r}. {listing()}")
    size = (int(size[0]), int(size[1]))
    found = list(map(Profile, names()))
    exact = [p for p in found if p.screen == size]
    if len(exact) > 1:
        sys.exit(f"More than one profile is for {size_name(size)}: {', '.join(p.name for p in exact)}. "
                 "Pick one with --profile NAME")
    if exact:
        return exact[0]
    shaped = [p for p in found if same_shape(p.screen, size)]
    if shaped:
        return max(shaped, key=lambda p: (len(p.template_names()), p.screen[0]))
    if create_new:
        new = shape_name(size)
        if exists(new):
            sys.exit(f"Profile {new} exists but is for {size_name(Profile(new).screen)}. "
                     f"Name a new one for {size_name(size)} with --profile NAME")
        p = create(new, size)
        print(f"Created profile {p} in {rel(p.dir)}, for {shape_label(size)} screens")
        return p
    sys.exit(f"No profile is set up for {size_name(size)} ({shape_label(size)}) screens. {listing()}\n"
             f"Start one with snap:  {CLI} snap   (or in the window: Setup tools, Snap screenshots)")


def fitted(name, size, create_new=False):
    """choose(), then fit() to the screen size."""
    return choose(name, size, create_new).fit(size)


def owner(path):
    """The profile whose folder the file is in, or None."""
    try:
        parts = path.resolve().relative_to(PROFILES.resolve()).parts
    except ValueError:
        return None
    return Profile(parts[0]) if parts and exists(parts[0]) else None


def with_routine(routine, prefer=None):
    """A profile that has this routine, to copy its steps from: prefer first, else a cropped one."""
    if prefer is not None and routine in prefer.routines:
        return prefer
    found = [p for p in map(Profile, names()) if routine in p.routines]
    return min(found, key=lambda p: p.name, default=None)
