"""Routines: a fixed sequence of clicks, key presses and typing from the profile (the storage-full smelt),
and drawing the steps on their screenshots so the click spots can be checked by eye."""
import time

import cv2
import numpy as np

from . import inputs, winapi
from . import settings as cfg
from .common import DEBUG, imread, imwrite, log

MAGENTA, BLACK, WHITE = (255, 0, 255), (0, 0, 0), (255, 255, 255)


def wait_for_game(keys):
    """Return once the game is the front window, after FOCUS_SETTLE if it had to be waited for.
    Same rules as the main loop: never steals focus, except after IDLE_BEFORE_REFOCUS of you not
    touching mouse/keyboard. False if F10 was pressed meanwhile."""
    waited, last_refocus = False, None
    while not keys.quit:
        if winapi.game_in_front():
            if not waited:
                return True
            log(f"routine: the game is back in front - waiting {cfg.FOCUS_SETTLE:g}s before the next step")
            keys.sleep(cfg.FOCUS_SETTLE)
            waited = False                 # look again: it could have lost focus during the wait
            continue
        if not waited:
            log("routine: the game isn't the front window - waiting for it before the next step")
            waited = True
        now = time.monotonic()
        if (last_refocus is None or now - last_refocus >= cfg.REFOCUS_EVERY) \
                and winapi.user_idle_seconds() >= cfg.IDLE_BEFORE_REFOCUS:
            last_refocus = now
            if winapi.ensure_focus():
                log(f"routine: no mouse/keyboard input for {cfg.IDLE_BEFORE_REFOCUS}s - brought the game back")
                continue
        keys.sleep(0.5)
    return False


def run(name, steps, screen, keys):
    """Do every step in order. A routine is a sequence, so a step is never skipped: before each one it
    waits for the game to be in front. True when finished, False if F10 was pressed."""
    log(f"routine {name}: {len(steps)} steps")
    for i, step in enumerate(steps, 1):
        if not wait_for_game(keys):
            return False
        if "click" in step:
            x, y = screen.to_screen(step["click"])
            inputs.click(x, y)
            log(f"  {i}/{len(steps)} {step['name']}: clicked {x},{y}")
        elif "type" in step:
            inputs.type_text(step["type"], cfg.TYPE_GAP)
            log(f"  {i}/{len(steps)} {step['name']}: typed {step['type']}")
        else:
            inputs.press(step["key"])
            log(f"  {i}/{len(steps)} {step['name']}: pressed {step['key']}")
        keys.sleep(step["wait"])
        if keys.quit:
            return False
    log(f"routine {name} done")
    return True


def _text(img, text, org, scale=0.8, color=MAGENTA):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, BLACK, 5, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)


def draw(profile, name):
    """Draw each step on the screenshot it was measured on -> list of saved debug images."""
    steps = profile.routines[name]
    by_shot = {}
    for i, s in enumerate(steps, 1):
        by_shot.setdefault(s["shot"], []).append((i, s))
    saved = []
    for shot, items in by_shot.items():
        img = imread(profile.routine_dir(name) / shot) if shot else None
        if img is None:
            w, h = profile.screen
            img = np.full((h, w, 3), 40, np.uint8)
            _text(img, f"(no screenshot: {shot or 'none given'})", (40, 120), 1.0, WHITE)
        keyed = 0
        for i, s in items:
            label = f"{i}. {s['name']}, then {s['wait']:g}s"
            if "click" in s:
                x, y = s["click"]
                cv2.drawMarker(img, (x, y), BLACK, cv2.MARKER_CROSS, 40, 6)
                cv2.drawMarker(img, (x, y), MAGENTA, cv2.MARKER_CROSS, 40, 3)
                right = x < img.shape[1] - 420
                _text(img, label, (x + 16 if right else x - 16 - 12 * len(label), y - 14))
            else:                          # key presses and typing have no spot: listed top left
                what = f"type {s['type']}" if "type" in s else f"press {s['key'].upper()}"
                _text(img, f"{label}  ({what})", (40, 70 + 45 * keyed), 1.2)
                keyed += 1
        out = DEBUG / f"routine_{name}_{items[0][0]:02d}.png"
        imwrite(out, img)
        saved.append(out)
    return saved
