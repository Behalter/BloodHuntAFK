"""The commands: run, snap, crop, check, keytest. `main()` reads the command line."""
import datetime
import json
import sys
import time
from pathlib import Path

import cv2

from . import bot, inputs, profiles, routines, vision, winapi
from . import settings as cfg
from .common import DEBUG, PROFILES, beep, countdown, imread, imwrite, log, rel, stamp


# ── Picking the profile ─────────────────────────────────────────────────────
def live_profile(name, create=False):
    """The profile for the main screen as it is now. With create, --profile NAME that doesn't exist
    yet is made for this screen size."""
    size = vision.Screen().size
    if create and name and not profiles.exists(name):
        p = profiles.create(name, size)
        print(f"Created profile {p} in {rel(p.dir)}")
        return p
    p = profiles.choose(name, size)
    if p.screen != size:
        sys.exit(f"Profile {p} doesn't fit your main screen, which is {size[0]}x{size[1]}. "
                 "Set the game and screen back to that size, or pick another profile.")
    return p


def find_shot(shot):
    """A screenshot given as a path, or as just a file name in any profile's shots folder."""
    p = Path(shot)
    if p.is_file():
        return p
    hits = sorted(PROFILES.glob(f"*/shots/{p.name}"))
    if not hits:
        sys.exit(f"Can't find {shot}")
    return hits[0]


def shot_profile(name, shot, img):
    """The profile for working on a saved screenshot: --profile, else the profile folder it's in,
    else the profile for its size."""
    if name:
        return profiles.load(name)
    p = profiles.owner(shot)
    if p:
        return p
    h, w = img.shape[:2]
    return profiles.choose(None, (w, h))


def read_shot(shot):
    shot = find_shot(shot)
    img = imread(shot)
    if img is None:
        sys.exit(f"Can't read {shot}")
    return shot, img


# ── Commands ────────────────────────────────────────────────────────────────
def run(name):
    bot.run(live_profile(name))


def snap(name):
    p = live_profile(name, create=True)
    templates = p.templates()
    screen, keys = vision.Screen(), winapi.Hotkeys()
    print(f"Snap mode, profile {p}: F8 = save a screenshot, F10 = quit.\n"
          "Keep the mouse off any button you want to crop.")
    while not keys.tapped(cfg.QUIT_KEY):
        if keys.tapped(cfg.PAUSE_KEY):
            frame = screen.grab()
            path = p.shots_dir / f"shot_{stamp()}.png"
            imwrite(path, frame)
            beep(1200, 80)
            print(f"saved {rel(path)}")
            if templates:
                vision.report(frame, templates, p.click_at)
        time.sleep(0.03)


def pick_shot(p):
    """List the profile's screenshots oldest-first and let the user choose one by number."""
    shots = p.shots()
    if not shots:
        sys.exit(f"No screenshots in {rel(p.shots_dir)} yet - run snap first.")
    print(f"Screenshots in profile {p} (oldest first):")
    for i, s in enumerate(shots, 1):
        when = datetime.datetime.fromtimestamp(s.stat().st_mtime)
        print(f"  {i:>2}. {s.name}   taken {when:%b %d %H:%M:%S}")
    while True:
        choice = input(f"Which one? (1-{len(shots)}, Enter = {len(shots)}, the newest): ").strip()
        if not choice:
            return shots[-1]
        if choice.isdigit() and 1 <= int(choice) <= len(shots):
            return shots[int(choice) - 1]
        print("Type one of the numbers above.")


def crop(template_name, shot, name):
    if not vision.kind_of(template_name):
        sys.exit(f"Template names must start with {vision.PREFIXES}  (e.g. click_one_more_round)")
    if shot:
        shot, img = read_shot(shot)
        p = shot_profile(name, shot, img)
    else:
        p = profiles.choose(name, vision.Screen().size)
        shot, img = read_shot(pick_shot(p))
    h, w = img.shape[:2]
    if (w, h) != p.screen:
        sys.exit(f"{shot.name} is {w}x{h}, but profile {p.name} is for {p.screen[0]}x{p.screen[1]}. "
                 "Crop from a screenshot taken at the profile's size.")
    sw, sh = winapi.screen_metrics()
    scale = min(1.0, 0.85 * sw / w, 0.85 * sh / h)
    win = f"{shot.name}: drag a box, Enter = save, C = cancel"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, int(w * scale), int(h * scale))
    x, y, bw, bh = cv2.selectROI(win, img, showCrosshair=False)
    cv2.destroyAllWindows()
    if bw < 16 or bh < 16:
        print("Cancelled (or the box was under 16 px - grab a bigger area).")
        return
    # Snap the box to the grid matching uses (every 2nd pixel at MATCH_SCALE 0.5). A box starting on an
    # odd pixel is shrunk half a pixel out of step with the screen and scores noticeably lower.
    step = max(1, round(1 / cfg.MATCH_SCALE))
    x1, y1 = min(w, -(-(x + bw) // step) * step), min(h, -(-(y + bh) // step) * step)
    x, y = x - x % step, y - y % step
    bw, bh = x1 - x, y1 - y
    out = p.templates_dir / f"{template_name}.png"
    imwrite(out, img[y:y + bh, x:x + bw])
    spot = {"x": int(x), "y": int(y), "w": int(bw), "h": int(bh), "screen_w": int(w), "screen_h": int(h)}
    out.with_suffix(".json").write_text(json.dumps(spot), encoding="utf-8")
    print(f"Saved {rel(out)} ({bw}x{bh}) and {out.stem}.json (where it was, so it's only looked "
          f"for around there).\nRun `check {shot.name}` to see how it scores.")


def check(shot, name):
    if shot:
        shot, frame = read_shot(shot)
        p = shot_profile(name, shot, frame)
        print(f"Checking {shot.name} with profile {p}")
    else:
        p = live_profile(name)
        countdown(5)
        frame = vision.Screen().grab()
        title, cls = winapi.foreground_info()
        verdict = "recognised as the game" if winapi.game_in_front() else \
            "NOT recognised as the game - set GAME_TITLE / GAME_CLASS in bloodhunt\\settings.py to these"
        print(f"Profile {p}. Foreground window: title={title!r} class={cls!r} -> {verdict}")
    templates = p.templates()
    if not templates:
        print(f"No templates in {rel(p.templates_dir)} yet - use snap and crop first.")
        return
    vision.warn_size(templates, frame)
    print(f"Scores ({cfg.MATCH_THRESHOLD} or higher counts as a match):")
    out = frame.copy()
    for t, score, pos, counts in vision.report(frame, templates, p.click_at):
        if t.locked:                       # thin yellow box = the area it's searched in
            sx, sy, sw, sh = t.spot
            m = cfg.SEARCH_MARGIN
            cv2.rectangle(out, (sx - m, sy - m), (sx + sw + m, sy + sh + m), (0, 220, 255), 1)
        if not pos:
            continue
        color = (0, 200, 0) if counts else (0, 0, 255)
        x0, y0 = pos[0] - t.w // 2, pos[1] - t.h // 2
        cv2.rectangle(out, (x0, y0), (x0 + t.w, y0 + t.h), color, 3)
        cv2.putText(out, f"{t.name} {score:.2f}", (x0, max(24, y0 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        if counts and t.kind == "click":   # magenta cross = where it would click
            cx, cy = vision.click_point(t, pos, p.click_at)
            cv2.drawMarker(out, (cx, cy), (255, 0, 255), cv2.MARKER_CROSS, 28, 3)
    imwrite(DEBUG / "check.png", out)
    print(f"Saved {rel(DEBUG / 'check.png')}: green = match, red = no match, thin yellow = search area, "
          "magenta cross = where it would click.")


def routine(args, name):
    """routine check [ROUTINE]: draw the steps on their screenshots.
    routine run [ROUTINE]: do the routine once now (start it from the screen its first step is on)."""
    action = args[0].lower() if args else ""
    if action not in ("check", "run"):
        sys.exit("Use:  routine check  (draws every step's click spot)   or   routine run  (does it once now)")
    p = live_profile(name) if action == "run" else profiles.choose(name, vision.Screen().size)
    if not p.routines:
        sys.exit(f"Profile {p} has no routines in {rel(p.dir / 'profile.json')}.")
    rname = (args[1] if len(args) > 1 else next(iter(p.routines)) if len(p.routines) == 1 else None)
    if not rname or rname.lower() not in p.routines:
        sys.exit(f"Which routine? Profile {p} has: {', '.join(p.routines)}")
    rname = rname.lower()
    steps = p.routines[rname]
    if action == "check":
        for i, s in enumerate(steps, 1):
            what = (f"click {s['click'][0]},{s['click'][1]}" if "click" in s else
                    f"type {s['type']}" if "type" in s else f"press {s['key']}")
            print(f"  {i:>2}. {s['name']:<18} {what:<16} then wait {s['wait']:g}s   ({s['shot']})")
        for path in routines.draw(p, rname):
            print(f"Saved {rel(path)}")
        print("Each magenta cross is where that step clicks, numbered in order.")
        return
    first = steps[0]
    countdown(5, f"Switch to the game, on the screen for step 1 ({first['name']})")
    routines.run(rname, steps, vision.Screen(), winapi.Hotkeys())


def keytest():
    countdown(5, "Switch to the game (in a match, somewhere safe)")
    title, cls = winapi.foreground_info()
    inputs.press_repeated(cfg.ABILITY_KEY, cfg.ABILITY_PRESSES, cfg.ABILITY_SPAN)
    print(f"Sent '{cfg.ABILITY_KEY}' x{cfg.ABILITY_PRESSES} over {cfg.ABILITY_SPAN:g}s to window {title!r} (class {cls!r}).")
    print("Did the ability fire? If not, open the terminal as administrator and try again.\n"
          "If it still doesn't, the game is ignoring simulated input and this approach won't work.")


# ── Command line ────────────────────────────────────────────────────────────
def take_profile_arg(args):
    """Pull `--profile NAME` (or --profile=NAME) out of args -> (NAME or None, remaining args)."""
    rest, name = [], None
    it = iter(args)
    for a in it:
        if a.lower() == "--profile":
            name = next(it, None)
            if not name:
                sys.exit("--profile needs a name, e.g. --profile 1080p")
        elif a.lower().startswith("--profile="):
            name = a.split("=", 1)[1]
        else:
            rest.append(a)
    return name, rest


def main(help_text):
    name, args = take_profile_arg(sys.argv[1:])
    cmd = args[0].lower() if args else ""
    try:
        if cmd == "run":
            run(name)
        elif cmd == "snap":
            snap(name)
        elif cmd == "crop" and len(args) > 1:
            crop(args[1], args[2] if len(args) > 2 else None, name)
        elif cmd == "check":
            check(args[1] if len(args) > 1 else None, name)
        elif cmd == "keytest":
            keytest()
        elif cmd == "routine":
            routine(args[1:], name)
        else:
            print(help_text)
    except KeyboardInterrupt:
        log("stopped (Ctrl+C)")
    except inputs.FailSafeException:
        log("stopped: mouse was pushed into the top-left corner (failsafe)")
