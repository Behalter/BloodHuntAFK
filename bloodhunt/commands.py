"""The commands: run, snap, crop, check, routine, keytest. `main()` reads the command line (no command
opens the window, gui.py)."""
import datetime
import sys
import time
from pathlib import Path

import cv2

from . import bot, guide, inputs, profiles, routines, settings_file, vision, winapi
from . import settings as cfg
from .common import CLI, DEBUG, PROFILES, beep, countdown, imread, imwrite, log, rel, stamp


# ── Picking the profile ─────────────────────────────────────────────────────
def live_profile(name, create_new=False):
    """The profile for the main screen as it is now, fitted to its size (images resized and click spots
    scaled if it was cropped at another size of the same shape). create_new: with no profile for this
    screen shape, make an empty one instead of stopping."""
    return profiles.fitted(name, vision.Screen().size, create_new)



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


def fitted_to_shot(p, img):
    """p fitted to the screenshot's size, or the reason it can't be."""
    h, w = img.shape[:2]
    if not profiles.same_shape(p.screen, (w, h)):
        sys.exit(f"The screenshot is {w}x{h}, a different shape from profile {p}.")
    return p.fit((w, h))


def read_shot(shot):
    shot = find_shot(shot)
    img = imread(shot)
    if img is None:
        sys.exit(f"Can't read {shot}")
    return shot, img


# ── Commands ────────────────────────────────────────────────────────────────
def run(name, **kw):
    # The size read now is the terminal's. If the game runs at another resolution (exclusive
    # fullscreen), the bot re-picks the profile for that size once the game is in front.
    # kw: bot.run's keys / status / start_delay, from the window.
    bot.run(live_profile(name), refit=lambda size: profiles.fitted(name, size), **kw)


def snap(name):
    p = live_profile(name, create_new=True)
    templates = p.templates()
    screen, keys = vision.Screen(), winapi.Hotkeys()
    print(f"Snap mode, profile {p}: F8 = save a screenshot to {rel(p.shots_dir)}, F10 = quit.\n"
          "Each screenshot is scored with the profile's images, so you can see what's recognised.")
    if p.scale:
        print(f"\nThe profile's images are resized for your {p.screen[0]}x{p.screen[1]} screen. Screenshots taken "
              f"now are for `check` (to see the scores); `crop` only takes {p.base[0]}x{p.base[1]} ones.")
    else:
        print(f"Keep the mouse off any button you want to crop.\n\n{guide.checklist(p)}\n\n"
              "Then run `crop` (no name) to box them, one screenshot at a time.")
    while not keys.tapped(cfg.QUIT_KEY):
        if keys.tapped(cfg.PAUSE_KEY):
            if screen.refresh() or screen.size != p.screen:     # a fullscreen game changed the resolution
                p = live_profile(name, create_new=True)
                templates = p.templates()
                print(f"The screen is now {screen.size[0]}x{screen.size[1]}: profile {p}")
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


def guided_crop(name):
    guide.guided_crop(profiles.choose(name, vision.Screen().size))


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
        sys.exit(f"{shot.name} is {w}x{h}. " + guide.not_cropped_here(p, w, h))
    box = guide.select_box(img, f"{shot.name}: drag a box, Enter = save, C = cancel")
    if not box:
        return
    out = guide.save_template(p, template_name, img, box)
    print(f"Saved {rel(out)} ({box[2]}x{box[3]}) and {out.stem}.json (where it was, so it's only looked "
          f"for around there).\nRun `check {shot.name}` to see how it scores.")


def check(shot, name):
    if shot:
        shot, frame = read_shot(shot)
        p = fitted_to_shot(shot_profile(name, shot, frame), frame)
        print(f"Checking {shot.name} with profile {p}")
    else:
        countdown(5)                       # read the size after it: a fullscreen game can change it
        screen = vision.Screen()
        p = profiles.fitted(name, screen.size)
        frame = screen.grab()
        title, cls = winapi.foreground_info()
        verdict = "recognised as the game" if winapi.game_in_front() else \
            (f"NOT recognised as the game - set GAME_TITLE / GAME_CLASS to these (in {rel(settings_file.PATH)}, "
             "or the window's Advanced tab)")
        print(f"Profile {p}. Foreground window: title={title!r} class={cls!r} -> {verdict}")
    templates = p.templates()
    if not templates:
        print(f"No templates in {rel(p.templates_dir)} yet - use snap and crop first.")
        return
    vision.warn_size(templates, frame)
    print(f"Scores ({cfg.MATCH_THRESHOLD:g} or higher counts as a match"
          + (f"; {cfg.MATCH_THRESHOLD_SCALED:g} for images resized to this screen" if any(t.resized for t in templates)
             else "") + "):")
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
    routine run [ROUTINE]: do the routine once now (start it from the screen its first step is on).
    routine record [ROUTINE]: the user does it by hand, and their clicks become its click spots."""
    action = args[0].lower() if args else ""
    if action not in ("check", "run", "record"):
        sys.exit("Use:  routine check   (draws every step's click spot)\n"
                 "      routine run     (does it once now)\n"
                 "      routine record  (you do it by hand; your clicks become its click spots)")
    if action == "record":
        screen = vision.Screen()
        p = profiles.choose(name, screen.size, create_new=True)
        guide.record(p, args[1].lower() if len(args) > 1 else "storage_full", screen, winapi.Hotkeys())
        return
    # check draws on the profile's own step screenshots, so it uses the profile's own coordinates.
    # run fits the profile to the screen after the countdown, when the game is in front.
    p = profiles.choose(name, vision.Screen().size)
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
                    f"type {routines.describe_type(s['type'])}" if "type" in s else f"press {s['key']}")
            print(f"  {i:>2}. {s['name']:<18} {what:<16} then wait {s['wait']:g}s   ({s['shot']})")
        for path in routines.draw(p, rname):
            print(f"Saved {rel(path)}")
        print("Each magenta cross is where that step clicks, numbered in order.")
        size = vision.Screen().size
        if size != p.screen:
            sx, sy = size[0] / p.screen[0], size[1] / p.screen[1]
            print(f"These are {p.screen[0]}x{p.screen[1]} coordinates, as the profile was cropped. On your "
                  f"{size[0]}x{size[1]} screen each one is multiplied by {sx:.3g}"
                  + ("" if abs(sx - sy) < 1e-3 else f" across and {sy:.3g} down")
                  + ", which keeps it on the same button.")
        return
    first = steps[0]
    countdown(5, f"Switch to the game, on the screen for step 1 ({first['name']})")
    screen = vision.Screen()               # read the size now: a fullscreen game can change it
    p = profiles.fitted(name, screen.size)
    if rname not in p.routines:
        sys.exit(f"Profile {p} (for this {screen.size[0]}x{screen.size[1]} screen) has no {rname} routine.")
    log(f"routine {rname} with profile {p}")
    routines.run(rname, p.routines[rname], screen, winapi.Hotkeys())


def keytest():
    countdown(5, "Switch to the game (in a match, somewhere safe)")
    title, cls = winapi.foreground_info()
    inputs.press_repeated(cfg.ABILITY_KEY, cfg.ABILITY_PRESSES, cfg.ABILITY_SPAN)
    print(f"Sent '{cfg.ABILITY_KEY}' x{cfg.ABILITY_PRESSES} over {cfg.ABILITY_SPAN:g}s to window {title!r} (class {cls!r}).")
    print("Did the ability fire? If not, open the terminal as administrator and try again.\n"
          "If it still doesn't, the game is ignoring simulated input and this approach won't work.")


def wave_check():
    """Offline packaging check: imports and recognition data, no capture or input."""
    from .common import HERE, FROZEN
    from .wave_runtime import run as wave_run
    from .wave_state import Phase, Rune
    from scripts.analyze_video import detect, normalize
    from scripts.wave_templates import BUNDLE_RELATIVE, load_bundle, hero_crop, arrays
    from scripts.lifecycle_timeline import TimelineRow, combine
    from scripts.shadow_monitor import ShadowMonitor
    from scripts.wave_action_preview import WaveActionPreview
    from scripts.pause_recovery import ResumeGate, pending_reconciled

    bundle = HERE / BUNDLE_RELATIVE
    wave, post, hero = load_bundle(bundle)
    count = len(arrays(wave, post, hero)) - 1
    print(f"PASS: {'Frozen executable' if FROZEN else 'Source'} wave runtime imports and {count} recognition templates.")
    print(f"Bundle: {bundle}")
    from scripts.chrono_detector import ChronoDetector
    from scripts.chrono_flow import ChronoFlow, RewardLatch
    chrono_bundle = HERE / "profiles" / "16x9" / "chrono_templates.npz"
    chrono = ChronoDetector.load(chrono_bundle)
    print(f"PASS: Chrono Rush runtime imports and {len(chrono.templates)} recognition templates.")
    print(f"Bundle: {chrono_bundle}")


# ── Command line ────────────────────────────────────────────────────────────
def take_profile_arg(args):
    """Pull `--profile NAME` (or --profile=NAME) out of args -> (NAME or None, remaining args)."""
    rest, name = [], None
    it = iter(args)
    for a in it:
        if a.lower() == "--profile":
            name = next(it, None)
            if not name:
                sys.exit("--profile needs a name, e.g. --profile 16x9")
        elif a.lower().startswith("--profile="):
            name = a.split("=", 1)[1]
        else:
            rest.append(a)
    return name, rest


def load_settings():
    """Read settings.py (next to the exe in the release, which can't import it) into the settings module.
    It's read as plain values, never run, and a wrong value is reported with its line."""
    try:
        if settings_file.ensure_file():
            print(f"{rel(settings_file.PATH)} was missing, so the built-in one was put back.")
        if settings_file.migrate_chrono_setting():
            print("Added the optional Chrono Rush setting; existing settings preserved.")
        settings_file.load()
    except settings_file.SettingsError as e:
        sys.exit(f"Can't use {rel(settings_file.PATH)}: {e}")


def main(help_text):
    """No command: the window. --hold (added by the window's Setup tools, which open a command in its own
    console window): wait for Enter at the end, so the window doesn't vanish with the last message."""
    name, args = take_profile_arg(sys.argv[1:])
    hold = any(a.lower() == "--hold" for a in args)
    args = [a for a in args if a.lower() != "--hold"]
    cmd = args[0].lower() if args else ""
    if not cmd:
        from . import gui
        gui.main(name)
        return
    try:
        load_settings()
        if cmd == "run":
            run(name)
        elif cmd == "snap":
            snap(name)
        elif cmd == "crop" and len(args) > 1:
            crop(args[1], args[2] if len(args) > 2 else None, name)
        elif cmd == "crop":
            guided_crop(name)
        elif cmd == "check":
            check(args[1] if len(args) > 1 else None, name)
        elif cmd == "wave-check":
            wave_check()
        elif cmd == "keytest":
            keytest()
        elif cmd == "routine":
            routine(args[1:], name)
        else:
            print(help_text.replace("python BloodHuntAFK.py", CLI))
    except KeyboardInterrupt:
        log("stopped (Ctrl+C)")
    except inputs.FailSafeException:
        log("stopped: mouse was pushed into the top-left corner (failsafe)")
    except SystemExit as e:
        if not hold:
            raise
        if e.code not in (None, 0):
            print(e.code)
    finally:
        if hold:
            try:
                input("\nPress Enter to close this window.")
            except (EOFError, KeyboardInterrupt):
                pass
