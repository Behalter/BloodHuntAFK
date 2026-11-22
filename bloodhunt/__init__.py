"""Blood Hunt AFK bot. Run it through BloodHuntAFK.py.

Importing this package sets Windows up first. Every module in it is imported after this file runs,
so the DPI setting below is always in place before mss and pydirectinput are imported.
"""
import ctypes
import sys

if sys.platform != "win32":
    sys.exit("This script only runs on Windows.")

# Work in real pixels on scaled (125% / 150%) displays so screenshots and clicks line up.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
