"""Profiles: everything that depends on the screen resolution, one folder per resolution.

    profiles\\<name>\\profile.json   {"screen": [1920, 1080], "click_at": {...}, "routines": {...}}
    profiles\\<name>\\templates\\     NAME.png + NAME.json (where on screen it was cropped)
    profiles\\<name>\\shots\\         screenshots from `snap`
    profiles\\<name>\\routines\\<routine>\\   the screenshots each routine step was measured on

click_at: buttons to click at a fixed spot instead of the centre of the matched image, in that
profile's screen pixels.
routines: name -> list of steps, run in order when a routine_<name>*.png template is seen. A step is
    {"name": "Smelt", "click": [x, y], "wait": 3.5, "shot": "06_selected.png"}   or
    {"name": "Dismiss rewards", "key": "space", "wait": 0.5, "shot": "07_acquired.png"}
  wait = seconds after the step; shot = the screenshot it was measured on (for `routine check`).
"""
import json
import re
import sys

from . import inputs
from .common import PROFILES, rel
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

    def __str__(self):
        return f"{self.name} ({self.screen[0]}x{self.screen[1]})"

    def routine_for(self, template_name):
        """The routine a routine_* template starts: routine_storage_full*.png -> storage_full, or None."""
        rest = template_name.lower()[len("routine"):].lstrip("_")
        found = [r for r in self.routines if rest == r or rest.startswith(r + "_")]
        return max(found, key=len) if found else None

    def routine_dir(self, routine):
        return self.dir / "routines" / routine

    def templates(self):
        return load_templates(self.templates_dir)

    def shots(self):
        """Screenshots, oldest first."""
        return sorted(self.shots_dir.glob("*.png"), key=lambda p: p.stat().st_mtime)


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
        text = str(s["type"])
        bad = sorted({ch for ch in text if not inputs.key_for(ch)})
        if not text or bad:
            raise ValueError(f"{where} can't type {text!r}" + (f": no single key for {bad}" if bad else "")
                             + " (lowercase letters, digits, space and unshifted symbols only)")
        step["type"] = text
    else:
        raise ValueError(f'{where} needs "click": [x, y], "key": "..." or "type": "..."')
    if step["wait"] < 0:
        raise ValueError(f"{where} has a negative wait")
    return step


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
        sys.exit("Profile names can only use letters, digits, - and _  (e.g. 1080p, laptop)")
    d = PROFILES / name
    (d / "templates").mkdir(parents=True, exist_ok=True)
    (d / "shots").mkdir(exist_ok=True)
    data = {"screen": [int(size[0]), int(size[1])], "click_at": {}}
    (d / "profile.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return Profile(name)


def choose(name, size):
    """--profile NAME if given, otherwise the one profile made for this screen size."""
    if name:
        return load(name)
    w, h = size
    matches = [p for p in map(Profile, names()) if p.screen == (w, h)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        sys.exit(f"No profile is set up for {w}x{h}. {listing()}\n"
                 "Start one for this size with:  python BloodHuntAFK.py snap --profile NAME")
    sys.exit(f"More than one profile is for {w}x{h}: {', '.join(p.name for p in matches)}. "
             "Pick one with --profile NAME")


def owner(path):
    """The profile whose folder the file is in, or None."""
    try:
        parts = path.resolve().relative_to(PROFILES.resolve()).parts
    except ValueError:
        return None
    return Profile(parts[0]) if parts and exists(parts[0]) else None
