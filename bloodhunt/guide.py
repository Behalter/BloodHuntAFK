"""Guided setup for a new screen size: the images the bot needs, cropping them one screenshot at a
time (`crop` with no name), and recording a routine's clicks (`routine record`)."""
import json
import sys
import time
from collections import namedtuple

import cv2
import numpy as np

from . import profiles, routines, vision, winapi
from . import settings as cfg
from .common import beep, imread, imwrite, rel

# Every image the bot needs, in the order they're usually met. fixed_click: the centre of the box
# becomes the profile's fixed click spot for it (click_at).
Item = namedtuple("Item", "name what where optional fixed_click")
ITEMS = [
    Item("click_skip", "the SPACE box next to HOLD TO SKIP", "Victory/Defeat screen, bottom right",
         False, True),
    Item("click_one_more_round", "the ONE MORE ROUND button", "after skipping the results",
         False, False),
    Item("ingame_lshift", "the LSHIFT key label on the HUD", "in a match", False, False),
    Item("ingame_portrait", "your hero's portrait on the HUD", "in a match, bottom left", False, False),
    Item("routine_storage_full", "the gear-limit message (both lines, inside the yellow stripes)",
         "after One more round, only when gear storage is full", True, False),
]

GREEN, GREY, WHITE, YELLOW, BLACK = (80, 220, 80), (170, 170, 170), (255, 255, 255), (0, 220, 255), (0, 0, 0)
KEY_ENTER, KEY_ESC = (13, 10), 27


def checklist(p):
    """The screens snap should capture, each with what's already made for this profile."""
    have = p.template_names()
    lines = ["Screens to capture (F8 on each). One screenshot can hold several of these:"]
    for it in ITEMS:
        mark = "done" if it.name in have else ("optional" if it.optional else "needed")
        lines.append(f"  [{mark:^8}]  {it.where}: {it.what}")
    return "\n".join(lines)


def not_cropped_here(p, w, h):
    """Why a w x h screenshot can't be cropped into profile p: it has to be p's own size."""
    msg = (f"Profile {p} is cropped at {p.screen[0]}x{p.screen[1]}, and its images and click spots are in "
           "that size's pixels.")
    if profiles.same_shape(p.screen, (w, h)):
        return (msg + f" At {w}x{h} they're resized to fit, so this size doesn't need cropping.\n"
                f"If an image scores too low at {w}x{h} (see `check`), make a profile cropped at this size: "
                f"`snap --profile {w}x{h}`, then `crop --profile {w}x{h}` and `routine record --profile "
                f"{w}x{h}`. It's used instead for that size.")
    return msg + f" {w}x{h} is a different shape: run snap at that size to start its own profile."


# ── Boxing an area and saving it as a template ──────────────────────────────
def select_box(img, title, example=None):
    """Let the user drag a box on img -> (x, y, w, h) snapped to even pixels, or None if cancelled.
    example (an image) is shown in its own window meanwhile, as a picture of what to box."""
    h, w = img.shape[:2]
    sw, sh = winapi.screen_metrics()
    scale = min(1.0, 0.85 * sw / w, 0.85 * sh / h)
    if example is not None:
        cv2.imshow("Example: box this", example)
        cv2.moveWindow("Example: box this", 20, 20)
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(title, int(w * scale), int(h * scale))
    x, y, bw, bh = cv2.selectROI(title, img, showCrosshair=False)
    cv2.destroyWindow(title)
    if example is not None:
        cv2.destroyWindow("Example: box this")
    if bw < 16 or bh < 16:
        print("Cancelled (or the box was under 16 px - grab a bigger area).")
        return None
    # Snap the box to the grid matching uses (every 2nd pixel at MATCH_SCALE 0.5). A box starting on an
    # odd pixel is shrunk half a pixel out of step with the screen and scores noticeably lower.
    step = max(1, round(1 / cfg.MATCH_SCALE))
    x1, y1 = min(w, -(-(x + bw) // step) * step), min(h, -(-(y + bh) // step) * step)
    x, y = x - x % step, y - y % step
    return int(x), int(y), int(x1 - x), int(y1 - y)


def save_template(p, name, img, box):
    x, y, bw, bh = box
    h, w = img.shape[:2]
    out = p.templates_dir / f"{name}.png"
    imwrite(out, img[y:y + bh, x:x + bw])
    spot = {"x": x, "y": y, "w": bw, "h": bh, "screen_w": w, "screen_h": h}
    out.with_suffix(".json").write_text(json.dumps(spot), encoding="utf-8")
    return out


def score_on(p, name, img):
    """How well the profile's template `name` matches img, or None if it isn't made yet."""
    t = next((t for t in p.templates() if t.name == name), None)
    return None if t is None else vision.find(vision.shrink(img), t)[0]


def example_for(item, p):
    """A picture of what to box for item: the same template from a cropped profile, sized for p's
    screen and blown up so it's easy to see. None if no profile has one."""
    found = [q for q in map(profiles.Profile, profiles.names()) if item.name in q.template_names()]
    if not found:
        return None
    q = min(found, key=lambda q: (q.name == p.name, q.name))   # another profile's, if there is one
    img = imread(q.templates_dir / f"{item.name}.png")
    if img is None:
        return None
    s = p.screen[1] / q.screen[1]
    img = cv2.resize(img, (max(1, round(img.shape[1] * s)), max(1, round(img.shape[0] * s))))
    zoom = min(max(1.0, 360 / img.shape[1]), 600 / img.shape[1], 300 / img.shape[0])
    img = cv2.resize(img, None, fx=max(zoom, 1.0), fy=max(zoom, 1.0), interpolation=cv2.INTER_NEAREST)
    canvas = np.full((img.shape[0] + 70, max(img.shape[1], 420) + 20, 3), 30, np.uint8)
    canvas[10:10 + img.shape[0], 10:10 + img.shape[1]] = img
    _put(canvas, item.what, (10, img.shape[0] + 35), 0.5, WHITE, False)
    _put(canvas, f"(example from {q.name}, enlarged)", (10, img.shape[0] + 58), 0.45, GREY, False)
    return canvas


# ── crop with no name: go through the screenshots ───────────────────────────
def _put(img, text, org, scale, color, outline=True):
    if outline:                            # readable on top of a busy screenshot
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, BLACK, 4, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def _menu_lines(p, img, status, prompt):
    small = vision.shrink(img)
    made = {t.name: t for t in p.templates()}
    lines = [(status, YELLOW), (prompt, WHITE)]
    for i, it in enumerate(ITEMS, 1):
        if it.name in made:
            here = vision.find(small, made[it.name])[0] >= vision.threshold(made[it.name])
            mark, color = ("done, on this screenshot", GREEN) if here else ("done", GREY)
        else:
            mark, color = ("optional" if it.optional else "not made yet"), WHITE
        lines.append((f"{i}  {it.what}  [{mark}]", color))
    lines.append(("D  already done? check one     N / Enter  next screenshot     Q  quit", WHITE))
    return lines


def _render(img, header, lines):
    """The screenshot shrunk to fit the screen, with the menu drawn on a darkened band at the top."""
    h, w = img.shape[:2]
    sw, sh = winapi.screen_metrics()
    scale = min(1.0, 0.85 * sw / w, 0.85 * sh / h)
    view = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    fs = max(0.45, view.shape[1] / 2400)
    lh = int(34 * fs / 0.6)
    rows = [(header, WHITE)] + lines
    panel_h = lh * len(rows) + lh // 2
    view[:panel_h] = (view[:panel_h] * 0.25).astype(np.uint8)
    for i, (text, color) in enumerate(rows):
        _put(view, text, (12, lh * (i + 1)), fs, color)
    return view


def _show(win, img, header, lines):
    """Show the screenshot with the menu on it; wait for a key -> lowercase char, 'enter', or 'q' if
    the window was closed."""
    cv2.imshow(win, _render(img, header, lines))
    while True:
        k = cv2.waitKey(100)
        if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
            return "q"
        if k == -1:
            continue
        k &= 0xFF
        if k in KEY_ENTER or k == 32:
            return "enter"
        if k == KEY_ESC:
            return "q"
        return chr(k).lower()


def _status(p, img):
    small = vision.shrink(img)
    hits = [f"{t.name} ({s:.2f})" for t in p.templates()
            for s in [vision.find(small, t)[0]] if s >= vision.threshold(t)]
    return ("Already recognised here: " + ", ".join(hits)) if hits else \
        "Nothing made so far is on this screenshot."


def guided_crop(p):
    shots = p.shots()
    if not shots:
        sys.exit(f"No screenshots in {rel(p.shots_dir)} yet. Run snap first.\n\n{checklist(p)}")
    print(f"Profile {p}: {len(shots)} screenshot(s). Each opens in a window with a menu on it.\n"
          "Press the number of something that's on the screenshot, then drag a box around it\n"
          "(an example of what to box opens alongside) and press Enter. C cancels a box.\n"
          "N or Enter goes to the next screenshot, Q quits.")
    win = "Setup: press a number (see the menu on the picture)"
    wrong = None                           # the size of a screenshot that couldn't be used
    for n, shot in enumerate(shots, 1):
        img = imread(shot)
        if img is None:
            print(f"Can't read {shot.name}, skipping it.")
            continue
        if (img.shape[1], img.shape[0]) != p.screen:
            wrong = (img.shape[1], img.shape[0])
            print(f"{shot.name} is {img.shape[1]}x{img.shape[0]}, not {p.screen[0]}x{p.screen[1]}: skipping it.")
            continue
        header = f"Screenshot {n} of {len(shots)}: {shot.name}"
        status, prompt = _status(p, img), "Press the number of what's on this screenshot to box it:"
        print(f"\n{header}\n  {status}")
        while True:
            key = _show(win, img, header, _menu_lines(p, img, status, prompt))
            prompt = "Press the number of what's on this screenshot to box it:"
            if key in ("enter", "n"):
                break
            if key == "q":
                cv2.destroyAllWindows()
                return _summary(p)
            if key == "d":
                key = _show(win, img, header, _menu_lines(p, img, status, "Which one is already done? Press its number:"))
                if key.isdigit() and 1 <= int(key) <= len(ITEMS):
                    status = _done_check(p, img, ITEMS[int(key) - 1])
                    print(f"  {status}")
                continue
            if not (key.isdigit() and 1 <= int(key) <= len(ITEMS)):
                continue
            it = ITEMS[int(key) - 1]
            cv2.destroyWindow(win)
            box = select_box(img, f"Box {it.what} - Enter saves, C cancels", example_for(it, p))
            if box:
                out = save_template(p, it.name, img, box)
                if it.fixed_click:
                    p.click_at[it.name] = (box[0] + box[2] // 2, box[1] + box[3] // 2)
                    p.save()
                score = score_on(p, it.name, img)
                status = f"Saved {it.name} ({box[2]}x{box[3]}), scores {score:.2f} here." + \
                    (f" It's clicked at {p.click_at[it.name][0]},{p.click_at[it.name][1]}." if it.fixed_click else "")
                print(f"  saved {rel(out)}" + (f", fixed click spot {p.click_at[it.name]}" if it.fixed_click else ""))
    cv2.destroyAllWindows()
    if wrong:
        print("\n" + not_cropped_here(p, *wrong))
    _summary(p)


def _done_check(p, img, it):
    score = score_on(p, it.name, img)
    if score is None:
        return f"{it.name} isn't made yet. Press {ITEMS.index(it) + 1} to box it."
    if score >= cfg.MATCH_THRESHOLD:
        return f"Done: {it.name} matches this screenshot ({score:.2f})."
    return (f"{it.name} exists but doesn't match this screenshot ({score:.2f}). If it's on here, "
            f"press {ITEMS.index(it) + 1} to box it again.")


def _summary(p):
    have = p.template_names()
    missing = [it for it in ITEMS if it.name not in have and not it.optional]
    print(f"\n{checklist(p)}")
    if missing:
        print("\nStill needed: " + ", ".join(it.name for it in missing) +
              ". Take screenshots of those screens with snap, then run crop again.")
    else:
        print("\nAll the needed images are made. Next: `check` (on a screenshot or live) to see them score, "
              "and `routine record` to record the storage-full routine's clicks.")


# ── routine record ──────────────────────────────────────────────────────────
def record(p, rname, screen, keys):
    """The user does the routine by hand; every click is recorded (keys aren't). The steps, waits and
    typing come from an existing profile's routine; only the click spots are new. p is the profile itself
    (not fitted): on a screen of another size of its shape, the clicks and screenshots are converted to
    the profile's size before saving, so the routine stays right for every size."""
    src = profiles.with_routine(rname, prefer=p)
    if src is None:
        sys.exit(f"No profile has a {rname!r} routine to follow.")
    recipe = src.routines[rname]
    clicks = [s for s in recipe if "click" in s]
    routines.check_typing(rname, recipe)   # the rating has to be typeable: you type it by hand now
    typed = next((routines.typed(s["type"]) for s in recipe if "type" in s), None)
    print(f"Recording the {rname} routine for profile {p}. Steps from profile {src.name}.\n\n"
          "Before you start:\n"
          "  - Be on the VICTORY / DEFEAT screen, with PREPARE showing. The routine ends by clicking START,\n"
          "    which from anywhere else could start a different mode (like Quick Match).\n"
          + (f"  - Have at least one Legendary item rated {typed} or below in your storage, so the\n"
             "    'Currently contains Legendary quality gear' popup appears after SMELT: its CONFIRM is one\n"
             "    of the clicks.\n" if typed and any("legendary" in s.get("hint", "").lower() for s in clicks) else "")
          + "  - Make exactly these clicks, in this order, and no others (clicking empty space counts too).\n"
          "    Each one beeps. Key presses aren't recorded, but do them where it says.\n")
    k = 0
    for s in recipe:
        if "click" in s:
            k += 1
            print(f"  {k:>2}. click {s.get('hint') or s['name']}")
        elif "type" in s:
            print(f"      then type {routines.describe_type(s['type'])}  (not recorded)")
        else:
            print(f"      then press {s['key'].upper()}  (not recorded)")
    print(f"\n{len(clicks)} clicks. F9 = undo the last click, F10 = cancel. Clicks only count once the game\n"
          "has been the front window for half a second, so the click that brings it to the front doesn't.")
    input("\nPress Enter here, then switch to the game and start. ")

    got = []                               # (x, y, screenshot) at each click, in the profile's pixels
    converted = False
    front_since, was_down = None, winapi.mouse_down()
    keys.tapped(cfg.QUIT_KEY)              # start from the keys' current state
    keys.tapped(cfg.UNDO_KEY)
    while len(got) < len(clicks):
        if keys.tapped(cfg.QUIT_KEY):
            print("Cancelled: nothing saved.")
            return False
        if keys.tapped(cfg.UNDO_KEY) and got:
            got.pop()
            beep(500, 200)
            print(f"  undone: next is {len(got) + 1}. {clicks[len(got)]['name']}")
        now = time.monotonic()
        if winapi.game_in_front():
            front_since = front_since or now
        else:
            front_since = None
        down = winapi.mouse_down()
        if down and not was_down:
            screen.refresh()               # the game can move, or change resolution when it's in front
            x, y = screen.from_screen(winapi.cursor_pos())
            w, h = screen.size
            if not (front_since and now - front_since >= 0.5):
                print("  (click not counted: the game wasn't the front window yet)")
            elif not (0 <= x < w and 0 <= y < h):
                print("  (click not counted: it was outside the game's picture)")
            elif not profiles.same_shape((w, h), p.screen):
                print(f"  (click not counted: the screen is {w}x{h}, a different shape from profile {p}. "
                      "Record with a profile for this shape: --profile NAME)")
            else:
                frame = screen.grab()
                if (w, h) != p.screen:     # store it in the profile's pixels
                    x, y = round(x * p.screen[0] / w), round(y * p.screen[1] / h)
                    frame = cv2.resize(frame, p.screen, interpolation=cv2.INTER_AREA)
                    converted = True
                got.append((x, y, frame))
                beep(1600 if len(got) == len(clicks) else 1200, 60)
                print(f"  {len(got):>2}/{len(clicks)} {clicks[len(got) - 1]['name']}: {x},{y}")
        was_down = down
        time.sleep(0.005)

    steps, it, saved = [], iter(got), set()
    for s in recipe:
        s = dict(s)
        if "click" in s:
            x, y, frame = next(it)
            s["click"] = (x, y)
            shot = s.get("shot") or f"{len(steps) + 1:02d}.png"
            s["shot"] = shot
            if shot not in saved:          # the screen as it was when this step clicked
                imwrite(p.routine_dir(rname) / shot, frame)
                saved.add(shot)
        steps.append(s)
    p.routines[rname] = steps
    p.save()
    for f, d in ((1000, 90), (1300, 90), (1600, 160)):
        beep(f, d)
    drawn = routines.draw(p, rname)
    if converted:
        print(f"\nProfile {p} is cropped at {p.screen[0]}x{p.screen[1]}, so your clicks were converted to that size "
              "(the bot converts them back for each screen it runs on).")
    print(f"\nSaved the {len(clicks)} click spots to {rel(p.dir / 'profile.json')}, and the screen at each click to "
          f"{rel(p.routine_dir(rname))}.\nTo check them by eye: {rel(drawn[0].parent)}\\routine_{rname}_NN.png "
          "(each magenta cross should be on its button).\n\n"
          "You clicked START, so a round should be starting now. If it isn't, a click was missed or an\n"
          "extra one was made: run `routine record` again.")
    return True
