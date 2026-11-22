"""Windows plumbing: finding and focusing the game window, idle time, and the F8/F10 hotkeys."""
import ctypes
import time
from ctypes import wintypes

from . import settings as cfg
from .common import beep, log

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
# Declared explicitly so 64-bit window handles aren't cut down to 32 bits.
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.GetAsyncKeyState.restype = ctypes.c_short
ctypes.windll.kernel32.GetTickCount.restype = wintypes.DWORD


def _text(fn, hwnd):
    buf = ctypes.create_unicode_buffer(512)
    fn(hwnd, buf, 512)
    return buf.value


def window_info(hwnd):
    if not hwnd:
        return "", ""
    return _text(user32.GetWindowTextW, hwnd), _text(user32.GetClassNameW, hwnd)


def foreground_info():
    return window_info(user32.GetForegroundWindow())


def is_game(hwnd):
    if not hwnd:
        return False
    title, cls = window_info(hwnd)
    return cfg.GAME_TITLE.lower() in title.lower() and (not cfg.GAME_CLASS or cls == cfg.GAME_CLASS)


def find_game_window():
    found = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and is_game(hwnd):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found[0] if found else None


def game_in_front():
    return not (cfg.GAME_TITLE or cfg.GAME_CLASS) or is_game(user32.GetForegroundWindow())


def ensure_focus():
    """Bring the game to the front. Only used after you've been idle for IDLE_BEFORE_REFOCUS."""
    if game_in_front():
        return True
    hwnd = find_game_window()
    if not hwnd:
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)              # SW_RESTORE
    user32.keybd_event(0x12, 0, 0, 0)           # Windows only lets a background app take focus
    user32.SetForegroundWindow(hwnd)            # right after a key event, so tap Alt around it
    user32.keybd_event(0x12, 0, 2, 0)
    time.sleep(0.5)
    return game_in_front()


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def user_idle_seconds():
    """Seconds since the last mouse/keyboard input on this PC. While the game isn't in front the bot
    sends nothing, so this is how long *you* have been idle."""
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0


def screen_metrics():
    """Primary screen size in pixels."""
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


class Hotkeys:
    """F8 / F10 polling that works while the game has focus (no keyboard hook needed)."""

    def __init__(self):
        self._held = {}
        self.paused = False
        self.quit = False

    def tapped(self, vk):
        down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
        was = self._held.get(vk, False)
        self._held[vk] = down
        return down and not was

    def poll(self):
        if self.tapped(cfg.QUIT_KEY):
            self.quit = True
        if self.tapped(cfg.PAUSE_KEY):
            self.paused = not self.paused
            log("paused - F8 to resume" if self.paused else "resumed")
            beep(600 if self.paused else 1000)

    def sleep(self, seconds):
        """Sleep, polling the hotkeys. Doesn't return while paused (on purpose)."""
        end = time.monotonic() + seconds
        while not self.quit and (self.paused or time.monotonic() < end):
            self.poll()
            time.sleep(0.05)
