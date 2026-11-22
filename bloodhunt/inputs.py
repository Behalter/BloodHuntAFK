"""Sending input: SendInput with scan codes (via pydirectinput), which DirectX games accept."""
import time

import pydirectinput

pydirectinput.PAUSE = 0.05
FailSafeException = pydirectinput.FailSafeException   # mouse pushed into the top-left corner


def press(key):
    pydirectinput.keyDown(key)
    time.sleep(0.08)            # games often miss key taps shorter than a frame or two
    pydirectinput.keyUp(key)


def press_repeated(key, times, span):
    """Press key `times` times, the presses starting evenly spread over `span` seconds (3 over 0.55 s
    -> at 0, 0.275, 0.55). Timed by the clock, since each press itself takes ~0.18 s."""
    start = time.monotonic()
    for i in range(times):
        if i:
            time.sleep(max(0.0, start + span * i / (times - 1) - time.monotonic()))
        press(key)


def key_for(ch):
    """The key name that types character ch, or None if it can't be typed with one key (capitals and
    symbols that need Shift aren't supported)."""
    name = "space" if ch == " " else ch
    return name if name in pydirectinput.KEYBOARD_MAPPING else None


def type_text(text, gap=0.0):
    """Type text one key at a time. Each press already takes ~0.18 s; gap adds this much more."""
    for i, ch in enumerate(text):
        if i and gap:
            time.sleep(gap)
        press(key_for(ch))


def click(x, y, park=None):
    pydirectinput.moveTo(x, y)
    time.sleep(0.15)            # let the button register the hover first
    pydirectinput.mouseDown()
    time.sleep(0.07)
    pydirectinput.mouseUp()
    if park:                    # put the mouse back in the middle, where the game itself leaves it,
        time.sleep(0.1)         # so it never sits on (and highlights) the next button
        pydirectinput.moveTo(*park)
