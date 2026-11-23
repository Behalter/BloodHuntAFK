"""Paths, logging and image-file helpers shared by every module."""
import datetime
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import winsound

# FROZEN: running as the exe (PyInstaller). Then the bot's folder is the exe's folder (profiles\, debug\,
# bot.log and settings.py sit next to it), and BUNDLE is where PyInstaller unpacked the code and the
# built-in copy of settings.py. From source, both are the project folder, where BloodHuntAFK.py is.
FROZEN = bool(getattr(sys, "frozen", False))
HERE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent
BUNDLE = Path(getattr(sys, "_MEIPASS", HERE))
CLI = "BloodHuntAFK-console.exe" if FROZEN else "python BloodHuntAFK.py"   # how to run a command, for messages
PROFILES = HERE / "profiles"
DEBUG = HERE / "debug"
LOGFILE = HERE / "bot.log"


def rel(path):
    """A path as shown to the user: relative to the project folder."""
    try:
        return str(Path(path).resolve().relative_to(HERE))
    except ValueError:
        return str(path)


def stamp():
    now = datetime.datetime.now()
    return f"{now:%Y%m%d_%H%M%S}_{now.microsecond // 1000:03d}"


def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def beep(freq=1000, ms=120):
    try:
        winsound.Beep(freq, ms)
    except RuntimeError:
        pass


def countdown(seconds=5, what="Switch to the game"):
    print(f"{what} - starting in", end=" ", flush=True)
    for i in range(seconds, 0, -1):
        print(i, end=" ", flush=True)
        time.sleep(1)
    print()


def imread(path):
    """cv2.imread that also copes with non-English characters in the path."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def imwrite(path, img):
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", img)[1].tofile(str(path))
