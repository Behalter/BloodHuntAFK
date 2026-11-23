"""Windows plumbing: finding and focusing the game window, idle time, the F8/F10 hotkeys and key names."""
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
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetAsyncKeyState.restype = ctypes.c_short
ctypes.windll.kernel32.GetTickCount.restype = wintypes.DWORD


# Windows virtual-key codes -> key names, the same names pydirectinput takes (so the window can turn a key
# press into ABILITY_KEY / HEAL_KEY, and show PAUSE_KEY etc. by name). Tk's event.keycode is this code.
VK_NAMES = {0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x10: "shift", 0x11: "ctrl", 0x12: "alt",
            0x13: "pause", 0x14: "capslock", 0x1B: "esc", 0x20: "space", 0x21: "pageup", 0x22: "pagedown",
            0x23: "end", 0x24: "home", 0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down", 0x2D: "insert",
            0x2E: "delete", 0x6A: "multiply", 0x6B: "add", 0x6D: "subtract", 0x6E: "decimal", 0x6F: "divide",
            0x90: "numlock", 0x91: "scrolllock", 0xA0: "shiftleft", 0xA1: "shiftright", 0xA2: "ctrlleft",
            0xA3: "ctrlright", 0xA4: "altleft", 0xA5: "altright", 0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-",
            0xBE: ".", 0xBF: "/", 0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'"}
VK_NAMES.update({0x30 + i: str(i) for i in range(10)})
VK_NAMES.update({0x41 + i: chr(ord("a") + i) for i in range(26)})
VK_NAMES.update({0x70 + i: f"f{i + 1}" for i in range(12)})
NAME_VKS = {v: k for k, v in VK_NAMES.items()}


def pretty_key(name):
    """A key name for people: F, F8, Space, Shift."""
    if len(name) == 1 or (name[0] == "f" and name[1:].isdigit()):
        return name.upper()
    return name.capitalize()


def key_name(vk):
    """A virtual-key code for people: 0x77 -> F8."""
    return pretty_key(VK_NAMES[vk]) if vk in VK_NAMES else f"key 0x{vk:02X}"


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


def mouse_down():
    """Is the primary mouse button held right now (the right one if the buttons are swapped)."""
    vk = 0x02 if user32.GetSystemMetrics(23) else 0x01     # SM_SWAPBUTTON; VK_RBUTTON / VK_LBUTTON
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def cursor_pos():
    """Mouse position in desktop pixels (the main monitor's top-left is 0,0; others can be negative)."""
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def is_admin():
    """Running as administrator? The game ignores input from programs with lower rights."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def screen_metrics():
    """Primary screen size in pixels."""
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def virtual_screen():
    """The whole desktop across every monitor -> (left, top, width, height). Left/top are negative when a
    monitor sits left of or above the main one."""
    return tuple(user32.GetSystemMetrics(i) for i in (76, 77, 78, 79))   # SM_X/YVIRTUALSCREEN, SM_CX/CYVIRTUALSCREEN


_game_hwnd = None


def game_area():
    """Where the game's picture is on the desktop -> (left, top, width, height) of the inside of its window
    (no title bar or borders), on whichever monitor it's on. None if the game window isn't found or is
    minimised. Cheap: the window is looked up again only when the one found before is gone."""
    global _game_hwnd
    if not (cfg.GAME_TITLE or cfg.GAME_CLASS):
        return None
    if not (_game_hwnd and user32.IsWindow(_game_hwnd) and is_game(_game_hwnd)):
        _game_hwnd = find_game_window()
    hwnd = _game_hwnd
    if not hwnd or user32.IsIconic(hwnd):
        return None
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)) or r.right <= 0 or r.bottom <= 0:
        return None
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, r.right, r.bottom


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
            self.toggle_pause()

    def toggle_pause(self):
        """The pause key, or the window's Pause button (which shares this object with the loop)."""
        self.paused = not self.paused
        log(f"paused - {key_name(cfg.PAUSE_KEY)} to resume" if self.paused else "resumed")
        beep(600 if self.paused else 1000)

    def sleep(self, seconds):
        """Sleep, polling the hotkeys. Doesn't return while paused (on purpose)."""
        end = time.monotonic() + seconds
        while not self.quit and (self.paused or time.monotonic() < end):
            self.poll()
            time.sleep(0.05)
