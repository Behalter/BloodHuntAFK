"""The window: start, pause and stop the bot, see what it's doing, and change every setting.

Start, Key test and Check screen run the same code as the commands, in a worker thread. Start is bot.run
with the window's Hotkeys (so the Pause/Stop buttons and F8/F10 flip the same switches) and a bot.Status
that the window shows. The setup tools (snap, crop, routine record/check, check SHOT) open as the command
in their own console window, because they're driven from the keyboard and OpenCV windows. Everything the
code prints (log lines, check's scores) lands in the log box through a stdout stand-in. Tk is only touched
from the main thread: the worker reaches it through a queue and the Status object, read every POLL_MS.

Settings come from settings.py (settings_file). The Settings tab holds the ones every player sets, laid out
in MAIN; every other setting is on the Advanced tab, under the file's sections, so a setting added to the
file shows up there by itself. A setting's help is its comment in the file. Fields lock while the bot runs
and apply on the next Start (Start saves first).
"""
import io
import math
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from pathlib import Path
from typing import Any
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from tkinter.scrolledtext import ScrolledText

import pydirectinput

from . import bot, commands, inputs, profiles, settings_file, winapi
from . import settings as cfg
from .common import FROZEN, HERE, log

POLL_MS = 200
TITLE = "Blood Hunt AFK"            # must not contain GAME_TITLE, or the window would count as the game
ROUTINE = "storage_full"
RED, GREY = "#c42b1c", "#5f5f5f"
LOG_LINES = 4000                    # the log box keeps this many lines (bot.log keeps everything)

# The Settings tab: (box title, [(setting, label, unit)]). Everything else goes on the Advanced tab.
MAIN = [
    ("Ability (Thor's Awakening Rune)", [
        ("ABILITY_KEY", "Key", ""),
        ("F_DURATION", "Lasts", "seconds"),
        ("F_COOLDOWN", "Cooldown", "seconds"),
        ("FIRST_PRESS_DELAY", "First press after the HUD shows", "seconds"),
        ("ABILITY_PRESSES", "Presses each time", "presses"),
    ]),
    ("Heal", [
        ("HEAL_KEY", "Key", ""),
        ("HEAL_DELAY_POST_F", "First heal into the cooldown", "seconds"),
        ("HEAL_EVERY", "Then heal every", "seconds (0 = never)"),
    ]),
    ("When gear storage is full", [
        ("RUN_ROUTINES", "Smelt, then play on", ""),
        ("SMELT_RATING", "Smelt unlocked gear rated at or below", ""),
        ("BACKUP_ROUTINE_AFTER", "Smelt anyway after One more round", "clicks in a row (0 = never)"),
    ]),
    ("Run", [
        ("MAX_HOURS", "Stop after", "hours (0 = never)"),
    ]),
    ("Hotkeys (they work in any window)", [
        ("PAUSE_KEY", "Pause / resume", ""),
        ("QUIT_KEY", "Stop", ""),
        ("UNDO_KEY", "Undo a click (routine record)", ""),
    ]),
]
HIDDEN = {"MATCH_SCALE"}                      # the crops are aligned to it: changing it lowers every score
GAME_KEYS = {"ABILITY_KEY", "HEAL_KEY"}       # keys the bot presses in the game (pydirectinput names)
RULES = {                                     # numbers are "0 or more" unless listed here
    "ABILITY_PRESSES": {"whole": True, "low": 1},
    "NO_EFFECT_AFTER": {"whole": True},
    "STUCK_SHOTS_MAX": {"whole": True},
    "BACKUP_ROUTINE_AFTER": {"whole": True},
    "MATCH_THRESHOLD": {"high": 1},
    "MATCH_THRESHOLD_SCALED": {"high": 1},
    "CLICK_MIN_CONTRAST": {"high": 1},
    "SCAN_EVERY": {"above": 0},
    "SEARCH_MARGIN": {"whole": True},
    "SMELT_RATING": {"whole": True},
}
SMELT_FIELDS = {"RUN_ROUTINES", "SMELT_RATING", "BACKUP_ROUTINE_AFTER"}   # greyed out without a routine
UNITS = {"SEARCH_MARGIN": "pixels (empty = all)"}   # notes beside Advanced fields (the help says more)
WARNING = ("Automation is against Marvel Rivals' rules: using this bot can get your account banned. "
           "It makes no attempt to hide from anti-cheat.")


def pretty(name):
    return name.replace("_", " ").capitalize()


def _kind(v):
    """What kind of field a value gets (1 -> 1.5 or 80 -> None is still the same field)."""
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)) or v is None:
        return "number"
    return type(v).__name__


def number_text(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


class Field:
    """One setting in the window: its label, widget and unit/error note, and the value as loaded."""

    def __init__(self, app, parent, row, target, label, kind, unit="", rules=None):
        self.app, self.target, self.kind, self.unit = app, target, kind, unit
        self.rules = rules or {}
        self.loaded = None
        self.value = None                  # key fields keep their value here
        self.tab: Any = None               # the Scrolled tab it's on
        self.label = ttk.Label(parent, text=label)
        self.label.grid(row=row, column=0, sticky="w", padx=(0, app.pad), pady=2)
        self.var: Any = None               # BooleanVar or StringVar; key fields use self.value instead
        self.widget: Any = None            # Checkbutton, Button (key fields) or Entry
        if kind == "bool":
            self.var = tk.BooleanVar()
            self.widget = ttk.Checkbutton(parent, variable=self.var, command=app.on_edit)
        elif kind in ("gamekey", "hotkey"):
            self.widget = ttk.Button(parent, width=14, command=self.capture)
        else:
            self.var = tk.StringVar()
            self.widget = ttk.Entry(parent, textvariable=self.var, width=26 if kind == "text" else 9)
            self.var.trace_add("write", lambda *_: app.on_edit())
        self.widget.grid(row=row, column=1, sticky="w", pady=2)
        self.note = ttk.Label(parent, text=unit, foreground=GREY)
        self.note.grid(row=row, column=2, sticky="w", padx=(app.pad // 2, 0))
        for w in (self.label, self.widget, self.note):
            w.bind("<Enter>", lambda _e: app.show_help(self), add="+")
        self.widget.bind("<FocusIn>", lambda _e: app.show_help(self), add="+")

    @property
    def name(self):
        return self.target[0] if isinstance(self.target, tuple) else self.target

    def set(self, value):
        self.loaded = value
        if self.kind == "bool":
            self.var.set(bool(value))
        elif self.kind in ("gamekey", "hotkey"):
            self.value = value
            self.widget.configure(text=self.shown())
        else:
            self.var.set(value if self.kind == "text" else number_text(value))
        self.clear_error()

    def shown(self):
        if self.value is None:
            return "-"
        return winapi.pretty_key(self.value) if self.kind == "gamekey" else winapi.key_name(self.value)

    def get(self):
        """The value in the widget, checked -> value, or ValueError with what's wrong."""
        if self.kind == "bool":
            return bool(self.var.get())
        if self.kind in ("gamekey", "hotkey"):
            return self.value
        text = self.var.get().strip()
        if self.kind == "text":
            return text
        if not text and (self.rules.get("none_ok") or self.loaded is None):
            return None
        try:
            v = float(text.replace(",", "."))
        except ValueError:
            raise ValueError("type a number") from None
        if not math.isfinite(v):
            raise ValueError("type a number")
        r = self.rules
        if r.get("whole") and not v.is_integer():
            raise ValueError("a whole number")
        if v < r.get("low", 0):
            raise ValueError(f"{r.get('low', 0)} or more")
        if "above" in r and v <= r["above"]:
            raise ValueError(f"more than {r['above']}")
        if "high" in r and v > r["high"]:
            raise ValueError(f"{r['high']} at most")
        return int(v) if v.is_integer() else v

    def changed(self):
        try:
            return self.get() != self.loaded
        except ValueError:
            return True

    def show_error(self, text):
        self.note.configure(text=text, foreground=RED)

    def clear_error(self):
        self.note.configure(text=self.unit, foreground=GREY)

    def enable(self, on):
        self.widget.state(["!disabled"] if on else ["disabled"])

    # ── key fields: click, then press the key ──
    def capture(self):
        self.app.cancel_capture()
        self.app.capturing = self
        self.widget.configure(text="press a key...")
        self.widget.focus_set()
        self.widget.bind("<KeyPress>", self._key)
        self.widget.bind("<FocusOut>", lambda _e: self.stop_capture())

    def _key(self, event):
        vk = event.keycode                 # on Windows, Tk's keycode is the virtual-key code
        if vk == 0x1B:                     # Esc: keep the old key
            self.stop_capture()
            return "break"
        name = winapi.VK_NAMES.get(vk)
        if self.kind == "gamekey" and name not in pydirectinput.KEYBOARD_MAPPING:
            self.stop_capture()
            self.show_error("the bot can't press that key")
            return "break"
        self.value = name if self.kind == "gamekey" else vk
        self.stop_capture()
        self.app.on_edit()
        return "break"

    def stop_capture(self):
        self.widget.unbind("<KeyPress>")
        self.widget.unbind("<FocusOut>")
        self.widget.configure(text=self.shown())
        if self.app.capturing is self:
            self.app.capturing = None


class Scrolled(ttk.Frame):
    """A frame whose contents scroll up and down (the settings tabs)."""

    def __init__(self, parent):
        super().__init__(parent)
        bg = ttk.Style().lookup("TFrame", "background") or "SystemButtonFace"
        self.canvas = tk.Canvas(self, width=1, height=1, highlightthickness=0, borderwidth=0, background=bg)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        item = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(item, width=e.width))
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

    def wheel(self, event):
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.canvas.yview_moveto(0)


class _Output(io.TextIOBase):
    """Stands in for stdout/stderr: everything printed also goes to the log box (through the queue)."""

    def __init__(self, events, original):
        self.events, self.original = events, original

    def writable(self):
        return True

    def write(self, s):
        if s:
            self.events.put(("text", s))
            if self.original:
                try:
                    self.original.write(s)
                except (OSError, ValueError):
                    pass
        return len(s)

    def flush(self):
        if self.original:
            try:
                self.original.flush()
            except (OSError, ValueError):
                pass


class App:
    def __init__(self, root, profile_name=None):
        self.root, self.profile_name = root, profile_name
        self.events = queue.Queue()
        self.job = None                    # "run", "keytest" or "check" while one is going
        self.keys = self.status = None
        self.child = None                  # a setup tool's console process
        self.child_what = ""
        self.capturing = None
        self.fields, self.labels, self._boxes = {}, {}, {}
        self.settings, self.sections = {}, []
        self.settings_error = None
        self.loaded_mtime = None
        self.layout_key = None
        self.profile = None
        self.profile_size = None
        self.profile_text = ""
        self.has_routine = False
        self.disk_warned = False
        self.last_slow = 0.0
        self.closing = False
        self._polling = False
        self._quiet = False
        self._last_error = None            # the last error poll() logged, so a repeating one isn't logged 5x a second
        self._shown = {}                 # widget -> text last set, so poll() only changes what changed
        self._build()
        sys.stdout = _Output(self.events, sys.stdout)
        sys.stderr = _Output(self.events, sys.stderr)
        self._say(f"{TITLE}. Settings are in {settings_file.PATH}.\n"
                  "Set the ability and heal timings for your gear on the Settings tab, then Start. "
                  "Point at a setting to see what it does.\n")
        self.reload_settings()
        self._refresh_profile(force=True)
        self._game_line()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(POLL_MS, self.poll)

    # ── building the window ─────────────────────────────────────────────────
    def _build(self):
        root = self.root
        root.title(TITLE)
        self.px = root.winfo_fpixels("1i") / 96            # Windows' display scale (1.0 at 100%)
        self.pad = pad = max(4, round(8 * self.px))
        try:
            ttk.Style().theme_use("vista")
        except tk.TclError:
            pass
        self.bold = tkfont.nametofont("TkDefaultFont").copy()
        self.bold.configure(weight="bold")
        sw, sh = root.winfo_screenwidth() - 40, root.winfo_screenheight() - 80
        root.geometry(f"{min(round(1180 * self.px), sw)}x{min(round(800 * self.px), sh)}")
        root.minsize(min(round(1000 * self.px), sw), min(round(600 * self.px), sh))

        # Layout rule: no widget's size may depend on its text. Grid sizes a column by what its widgets ask
        # for, so a label asking for the width of its current text made the columns jump whenever the text
        # changed (the help box, while pointing at fields), and a label wrapping at its box's width fed back
        # into that width on every step of a window resize. So the two columns share the width in a fixed
        # proportion (uniform), and text widgets ask for no width of their own (width=1) and fill what
        # they're given; wrapped ones wrap at their own width (_wrap).
        outer = ttk.Frame(root, padding=pad)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=5, uniform="side")
        outer.columnconfigure(1, weight=4, uniform="side")
        outer.rowconfigure(0, weight=1)
        left = ttk.Frame(outer)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, pad))
        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="nsew")

        box = ttk.LabelFrame(left, text="Status", padding=pad)
        box.pack(fill="x")
        self.lbl_bot = ttk.Label(box, font=self.bold, width=1)
        self.lbl_profile = ttk.Label(box, width=1)
        self.lbl_game = ttk.Label(box, width=1)
        self.lbl_counts = ttk.Label(box, foreground=GREY, width=1)
        for lbl in (self.lbl_bot, self.lbl_profile, self.lbl_game, self.lbl_counts):
            lbl.pack(fill="x")
        if not winapi.is_admin():
            self._wrap(ttk.Label(box, foreground=RED, justify="left", width=1,
                                 text="Not running as administrator: the game ignores key presses and clicks from "
                                      "programs with lower rights. Close this and start it again as administrator.")
                       ).pack(fill="x")

        row = ttk.Frame(left)
        row.pack(fill="x", pady=(pad, 0))
        self.btn_start = ttk.Button(row, text="Start", command=self.start)
        self.btn_pause = ttk.Button(row, text="Pause", command=self.pause, width=16)
        self.btn_stop = ttk.Button(row, text="Stop", command=self.stop, width=14)
        for b in (self.btn_start, self.btn_pause, self.btn_stop):
            b.pack(side="left", padx=(0, pad // 2))
        row = ttk.Frame(left)
        row.pack(fill="x", pady=(pad // 2, 0))
        self.btn_keytest = ttk.Button(row, text="Key test", command=self.keytest)
        self.btn_check = ttk.Button(row, text="Check screen", command=self.check)
        self.btn_setup = ttk.Menubutton(row, text="Setup tools")
        menu = tk.Menu(self.btn_setup, tearoff=False)
        menu.add_command(label="Snap screenshots (snap)", command=lambda: self.launch("snap"))
        menu.add_command(label="Crop images from them (crop)", command=lambda: self.launch("crop"))
        menu.add_command(label="Score the images on a screenshot (check)", command=self.check_shot)
        menu.add_separator()
        menu.add_command(label="Record the storage-full routine (routine record)",
                         command=lambda: self.launch("routine", "record"))
        menu.add_command(label="Draw the routine's clicks (routine check)",
                         command=lambda: self.launch("routine", "check"))
        menu.add_separator()
        menu.add_command(label="Open the bot's folder", command=lambda: os.startfile(HERE))
        self.btn_setup["menu"] = menu
        for b in (self.btn_keytest, self.btn_check, self.btn_setup):
            b.pack(side="left", padx=(0, pad // 2))
        for widget, text in ((self.btn_keytest, "Presses the ability key 5 s from now: switch to the game (in a "
                                                "match, somewhere safe) and see that it fires."),
                             (self.btn_check, "Scores every image on the screen 5 s from now (switch to the game "
                                              "first) and saves debug\\check.png."),
                             (self.btn_setup, "For a screen shape that has no profile yet, or to record the "
                                              "storage-full routine. Each opens in its own console window. "
                                              "README.md, Other screen sizes, has the steps.")):
            widget.bind("<Enter>", lambda _e, t=text: self._help(t), add="+")

        ttk.Label(left, text="Log").pack(anchor="w", pady=(pad, 0))
        self.logbox = ScrolledText(left, width=1, height=1, wrap="word", font=("Consolas", 9), state="disabled",
                                   relief="solid", borderwidth=1)
        self.logbox.pack(fill="both", expand=True)
        self._wrap(ttk.Label(left, text=WARNING, foreground=GREY, justify="left", width=1)).pack(
            fill="x", pady=(pad // 2, 0))

        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill="both", expand=True)
        self.main_tab, self.adv_tab = Scrolled(self.tabs), Scrolled(self.tabs)
        self.tabs.add(self.main_tab, text="Settings")
        self.tabs.add(self.adv_tab, text="Advanced")
        helpbox = ttk.LabelFrame(right, text="What it does", padding=pad)
        helpbox.pack(fill="x", pady=(pad, 0))
        self.help_default = "Point at a setting to see what it does."
        self.lbl_help = self._wrap(tk.Label(helpbox, text=self.help_default, justify="left", anchor="nw",
                                            width=1, height=7,       # 7 lines tall, whatever the text
                                            background=ttk.Style().lookup("TFrame", "background") or "SystemButtonFace"))
        self.lbl_help.pack(fill="x")
        row = ttk.Frame(right)
        row.pack(fill="x", pady=(pad // 2, 0))
        self.btn_save = ttk.Button(row, text="Save", command=self.save)
        self.btn_undo = ttk.Button(row, text="Undo changes", command=self.undo)
        self.lbl_saved = ttk.Label(row, foreground=GREY, width=1)
        self.btn_save.pack(side="left", padx=(0, pad // 2))
        self.btn_undo.pack(side="left", padx=(0, pad))
        self.lbl_saved.pack(side="left", fill="x", expand=True)
        root.bind_all("<MouseWheel>", self._wheel, add="+")

    @staticmethod
    def _wrap(label):
        """A label (made with width=1) whose text wraps at the width it's given, so its text never changes
        the layout. Only its height follows the text (or not even that, with a fixed height)."""
        last = [0]

        def fit(event):
            w = max(40, event.width - 6)
            if abs(w - last[0]) > 2:       # only when it really changed: each change re-lays the label out
                last[0] = w
                label.configure(wraplength=w)

        label.bind("<Configure>", fit, add="+")
        return label

    def _wheel(self, event):
        """The mouse wheel scrolls the settings tab it's over, wherever in it the pointer is."""
        w = self.root.winfo_containing(event.x_root, event.y_root)
        while w is not None:
            if isinstance(w, Scrolled):
                w.wheel(event)
                return
            w = w.master

    def _box(self, tab, title):
        box = ttk.LabelFrame(tab.inner, text=title, padding=self.pad)
        box.pack(fill="x", padx=(0, self.pad), pady=(0, self.pad))
        box.columnconfigure(2, weight=1)
        self._boxes.setdefault(tab, []).append(box)
        return box

    def _line_up(self):
        """The same label column width in every box of a tab, so the fields line up down the tab."""
        self.root.update_idletasks()
        for tab, boxes in self._boxes.items():
            width = max((f.label.winfo_reqwidth() for f in self.fields.values() if f.tab is tab), default=0)
            for box in boxes:
                box.columnconfigure(0, minsize=width + self.pad)

    def _field(self, tab, box, row, s, label, unit=""):
        name = s.name
        if name in GAME_KEYS:
            kind = "gamekey"
        elif name.endswith("_KEY") and isinstance(s.value, int) and not isinstance(s.value, bool):
            kind = "hotkey"
        elif isinstance(s.value, bool):
            kind = "bool"
        elif isinstance(s.value, str):
            kind = "text"
        elif isinstance(s.value, (int, float)) or s.value is None:
            kind = "number"
        else:
            return None
        rules = dict(RULES.get(name, {}))
        if name in settings_file.NONE_OK:
            rules["none_ok"] = True
        f = Field(self, box, row, name, label, kind, unit, rules)
        f.tab = tab
        f.set(s.value)
        self.fields[name] = f
        self.labels.setdefault(name, label)
        return f

    def _build_settings(self):
        """Lay out both tabs for the settings in the file (again when the file gains or loses one)."""
        self.fields, self.labels, self._boxes = {}, {}, {}
        self.main_tab.clear()
        self.adv_tab.clear()
        if self.settings_error:
            self._wrap(ttk.Label(self.main_tab.inner, foreground=RED, justify="left", width=1,
                                 text=f"{settings_file.PATH.name} can't be read: {self.settings_error}\n\nFix it in a "
                                      f"text editor ({settings_file.PATH}). This window reads it again as soon as "
                                      "it changes.")).pack(fill="x", padx=(0, self.pad), pady=self.pad)
            return
        used = set()
        for title, items in MAIN:
            box = self._box(self.main_tab, title)
            row = 0
            for name, label, unit in items:
                if name in self.settings and self._field(self.main_tab, box, row, self.settings[name], label, unit):
                    used.add(name)
                    row += 1
            if title.startswith("When gear storage"):
                self.lbl_smelt = self._wrap(ttk.Label(box, foreground=GREY, justify="left", width=1))
                self.lbl_smelt.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(self.pad // 2, 0))
        self._wrap(ttk.Label(self.adv_tab.inner, justify="left", foreground=GREY, width=1,
                             text=f"Every other setting. All of them live in {settings_file.PATH}: Save changes just "
                                  "the value on each line. You can also edit that file in a text editor; this window "
                                  "reads it again when it changes.")).pack(fill="x", padx=(0, self.pad),
                                                                           pady=(0, self.pad))
        for sec in self.sections:
            names = [n for n in sec.settings if n not in used and n not in HIDDEN]
            if not names:
                continue
            box = self._box(self.adv_tab, sec.name)
            row = 0
            if sec.about:
                self._wrap(ttk.Label(box, text=sec.about[:1].upper() + sec.about[1:], foreground=GREY, width=1,
                                     justify="left")).grid(row=row, column=0, columnspan=3, sticky="ew",
                                                           pady=(0, self.pad // 2))
                row += 1
            for n in names:
                s = self.settings[n]
                if isinstance(s.value, dict):
                    for key, (v, _) in s.entries.items():
                        if isinstance(v, (int, float)) and not isinstance(v, bool):
                            f = Field(self, box, row, (n, key), f"{pretty(n)}: {key}", "number")
                            f.tab = self.adv_tab
                            f.set(v)
                            self.fields[(n, key)] = f
                            row += 1
                    self.labels.setdefault(n, pretty(n))
                elif self._field(self.adv_tab, box, row, s, pretty(n), UNITS.get(n, "")):
                    row += 1
        self._line_up()

    # ── settings: loading, help, saving ─────────────────────────────────────
    def reload_settings(self):
        """Read settings.py again and show it (into the settings module too: the bot isn't running when this
        is called, and the window's own key names and game detection read it)."""
        try:
            if settings_file.ensure_file():
                self._say(f"{settings_file.PATH.name} was missing, so the built-in one was put back.\n")
            self.sections, self.settings = settings_file.load()
            self.settings_error = None
        except settings_file.SettingsError as e:
            self.settings_error, self.settings, self.sections = str(e), {}, []
        self.loaded_mtime = settings_file.mtime()
        self.disk_warned = False
        self._quiet = True                 # setting each field would otherwise re-check every field (on_edit)
        try:
            layout = (self.settings_error,
                      tuple((n, _kind(s.value), tuple(s.entries)) for n, s in self.settings.items()))
            if layout != self.layout_key:
                self.layout_key = layout
                self._build_settings()
            else:
                for target, f in self.fields.items():
                    name, key = target if isinstance(target, tuple) else (target, None)
                    s = self.settings[name]
                    f.set(s.value if key is None else s.entries[key][0])
            self._refresh_smelt()
        finally:
            self._quiet = False
        self.on_edit()
        self._controls(force=True)

    def show_help(self, f):
        s = self.settings.get(f.name)
        if s is None:
            return
        group = s.group if len(s.group) > 1 else [s]
        text = "\n".join(f"{self.labels.get(m.name, pretty(m.name))}: {m.help}" if len(group) > 1 else m.help
                         for m in group)
        self._help(f"{text}\n\n({f.name} in {settings_file.PATH.name})")

    def _help(self, text):
        self.lbl_help.configure(text=text)

    def on_edit(self):
        if self._quiet:
            return
        unsaved = not self.settings_error and any(f.changed() for f in self.fields.values())
        self.lbl_saved.configure(text="Unsaved changes (Start saves them too)" if unsaved else "", foreground=GREY)

    def cancel_capture(self):
        if self.capturing:
            self.capturing.stop_capture()

    def _check_fields(self):
        """Every field's value -> {target: value}, or None after marking what's wrong in red."""
        values, bad = {}, []
        for target, f in self.fields.items():
            f.clear_error()
            try:
                values[target] = f.get()
            except ValueError as e:
                f.show_error(str(e))
                bad.append(f)

        def wrong(target, text):
            if target in self.fields and target in values:
                self.fields[target].show_error(text)
                bad.append(self.fields[target])

        if "F_DURATION" in values and "F_COOLDOWN" in values and values["F_DURATION"] + values["F_COOLDOWN"] <= 0:
            wrong("F_COOLDOWN", "lasts + cooldown must be more than 0")
        if values.get("ABILITY_KEY") and values.get("ABILITY_KEY") == values.get("HEAL_KEY"):
            wrong("HEAL_KEY", "the same key as the ability")
        pressed = {winapi.NAME_VKS.get(values.get(k) or "") for k in GAME_KEYS} | {0x20} | set(range(0x30, 0x3A))
        seen = {}
        for k in ("PAUSE_KEY", "QUIT_KEY", "UNDO_KEY"):
            vk = values.get(k)
            if vk is None:
                continue
            if vk in pressed:
                wrong(k, "the bot presses this key itself")
            elif vk in seen:
                wrong(k, f"already used for {self.labels.get(seen[vk], seen[vk]).lower()}")
            seen.setdefault(vk, k)
        if bad:
            self.tabs.select(bad[0].tab)
            self.lbl_saved.configure(text="Fix the fields marked in red", foreground=RED)
            return None
        return values

    def save(self):
        """Write the changed fields to settings.py -> True if all is saved."""
        self.cancel_capture()
        if self.settings_error:
            messagebox.showerror(TITLE, f"{settings_file.PATH.name} can't be read, so nothing can be saved:\n\n"
                                        f"{self.settings_error}")
            return False
        values = self._check_fields()
        if values is None:
            return False
        changes = {t: v for t, v in values.items() if v != self.fields[t].loaded}
        try:
            if changes:
                if settings_file.mtime() != self.loaded_mtime:
                    self._say(f"{settings_file.PATH.name} had been changed outside the window: those changes "
                              "are kept too.\n")
                settings_file.save(changes)
                log("settings saved: " + ", ".join(
                    f"{t[0]}[{t[1]!r}]" if isinstance(t, tuple) else t for t in changes) + " changed")
        except (settings_file.SettingsError, OSError) as e:
            messagebox.showerror(TITLE, f"Couldn't save: {e}")
            return False
        self.reload_settings()
        if changes:
            self.lbl_saved.configure(text="Saved", foreground=GREY)
        return not self.settings_error

    def undo(self):
        self.cancel_capture()
        self.layout_key = None             # rebuild from the file as it is
        self.reload_settings()

    # ── profile, game and the smelt group ───────────────────────────────────
    def _refresh_profile(self, force=False, area=None):
        """The profile the bot would use now (by the game window's size, else the main monitor's). area: the
        game window's, if just looked up (looking it up walks every window while the game isn't running)."""
        area = area if area is not None else winapi.game_area()
        size = tuple(area[2:]) if area else winapi.screen_metrics()
        if not force and size == self.profile_size:
            return
        self.profile_size = size
        try:
            self.profile = profiles.choose(self.profile_name, size).fit(size)
            self.profile_text = f"Profile: {self.profile}"
        except SystemExit as e:
            self.profile = None
            first = str(e.code).split("\n")[0]
            self.profile_text = f"Profile: none for this {size[0]}x{size[1]} screen. {first}"
        self._refresh_smelt()

    def _refresh_smelt(self):
        """The smelt group: greyed out, with a note saying why, when the profile in use has no storage-full
        routine (read from its profile.json as it is now: a routine may have just been recorded). A routine
        that types a rating of its own instead of {SMELT_RATING} (an older profile) gets a note too."""
        p = None
        if self.profile:
            try:
                p = profiles.Profile(self.profile.name)
            except SystemExit:             # profile.json can't be read right now: keep what was read before
                p = self.profile.original
        steps = p.routines.get(ROUTINE) if p else None
        self.has_routine = bool(steps)
        own = next((s["type"] for s in steps or [] if "type" in s and "{SMELT_RATING}" not in s["type"]), None)
        lbl = getattr(self, "lbl_smelt", None)
        if lbl is not None and lbl.winfo_exists():
            if not p:
                text = "There's no profile for this screen yet, so nothing is smelted."
            elif not steps:
                text = (f"Profile {p.name} has no storage-full routine yet, so full gear storage isn't handled on "
                        "this screen: One more round just keeps being clicked. Record it with Setup tools, "
                        "Record the storage-full routine.")
            elif own:
                text = (f"Profile {p.name}'s routine types {own} itself, so the rating above isn't used on this "
                        "screen. To use it, put {SMELT_RATING} in that step of its profile.json.")
            else:
                text = ""
            lbl.configure(text=text)
            if text:
                lbl.grid()
            else:
                lbl.grid_remove()          # no empty row under the fields
        self._controls(force=True)

    def _game_line(self, area=None):
        if not (cfg.GAME_TITLE or cfg.GAME_CLASS):
            text = "Game: not looked for (GAME_TITLE and GAME_CLASS are empty), so the main monitor is watched"
        else:
            area = area if area is not None else winapi.game_area()
            if area:
                text = f"Game: found, {area[2]}x{area[3]}, " + (
                    "the front window" if winapi.game_in_front() else "not the front window")
            else:
                text = "Game: not found (not running, or minimised)"
        self._set(self.lbl_game, text)

    # ── jobs: run, key test, check ──────────────────────────────────────────
    def busy(self):
        return self.job is not None or self.child_open()

    def child_open(self):
        return self.child is not None and self.child.poll() is None

    def _apply(self):
        """Save, and make sure the settings module holds the file's values -> True to go ahead."""
        if self.busy():
            return False
        return self.save()

    def _work(self, job, fn):
        self.job = job
        self._controls(force=True)

        def go():
            try:
                fn()
            except SystemExit as e:
                if e.code not in (None, 0):
                    log(str(e.code))
                    self.events.put(("error", str(e.code)))
            except inputs.FailSafeException:
                log("stopped: the mouse was pushed into the top-left corner (failsafe)")
            except Exception:
                log("something went wrong:\n" + traceback.format_exc())
                self.events.put(("error", "Something went wrong: " + traceback.format_exc().strip().splitlines()[-1]
                                 + "\n\nThe details are in the log and bot.log."))
            finally:
                self.events.put(("done", job))

        threading.Thread(target=go, name=job, daemon=True).start()

    def start(self):
        if not self._apply():
            return
        self.keys, self.status = winapi.Hotkeys(), bot.Status()
        self._say("Starting. Switch to the game: nothing is pressed or clicked while another window is in front.\n")
        self._work("run", lambda: commands.run(self.profile_name, keys=self.keys, status=self.status,
                                               start_delay=0))

    def pause(self):
        if self.job == "run" and self.keys:
            self.keys.toggle_pause()

    def stop(self):
        if self.job == "run" and self.keys and not self.keys.quit:
            self.keys.quit = True
            log("stopping (Stop pressed)")

    def keytest(self):
        if self._apply():
            self._work("keytest", commands.keytest)

    def check(self):
        if self._apply():
            self._work("check", lambda: commands.check(None, self.profile_name))

    def check_shot(self):
        start = self.profile.original.shots_dir if self.profile else HERE
        path = filedialog.askopenfilename(title="A screenshot to score the images on", parent=self.root,
                                          initialdir=str(start if start.exists() else HERE),
                                          filetypes=[("Screenshots", "*.png"), ("All files", "*.*")])
        if path:
            self.launch("check", path)

    def launch(self, *args):
        """A setup tool: the command in its own console window, which waits for Enter at the end (--hold)."""
        if not self._apply():
            if self.child_open():
                messagebox.showinfo(TITLE, "A setup tool is already open. Close its window first.")
            return
        if FROZEN:
            cmd = [str(HERE / "BloodHuntAFK-console.exe")]
        else:
            py = Path(sys.executable)
            if py.name.lower() == "pythonw.exe":
                py = py.with_name("python.exe")
            cmd = [str(py), str(HERE / "BloodHuntAFK.py")]
        cmd += list(args) + (["--profile", self.profile_name] if self.profile_name else []) + ["--hold"]
        try:
            self.child = subprocess.Popen(cmd, cwd=str(HERE), creationflags=subprocess.CREATE_NEW_CONSOLE)
        except OSError as e:
            messagebox.showerror(TITLE, f"Couldn't open it: {e}")
            return
        self.child_what = " ".join(args[:2]) if args[0] == "routine" else args[0]
        self._say(f"Opened {self.child_what} in its own window. The bot's buttons wait until it's closed.\n")
        self._controls(force=True)

    # ── the regular update ──────────────────────────────────────────────────
    def poll(self):
        if self._polling:                  # called again from inside an error box's own loop: the outer
            return                         # call carries on (and schedules the next one) when it closes
        self._polling = True
        try:
            self._drain()
            if self.closing and not self.job:
                self.root.destroy()        # the run has stopped: now the window can close
                return
            now = time.monotonic()
            if now - self.last_slow >= 1.0:
                self.last_slow = now
                self._slow()
            self._status_lines()
            self._controls()
            self.root.after(POLL_MS, self.poll)
        except Exception:
            error = traceback.format_exc()
            if error != self._last_error:  # log it once, not on every poll while it keeps happening
                self._last_error = error
                log("window error:\n" + error)
            self.root.after(POLL_MS, self.poll)
        finally:
            self._polling = False

    def _drain(self):
        text, errors = [], []
        while True:
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "text":
                text.append(data)
            elif kind == "error":
                errors.append(data)
            elif kind == "done":
                self.job = None
                if not self.closing:
                    self._refresh_profile(force=True)
                    self._controls(force=True)
        if text:
            self._say("".join(text))
        for e in errors:
            if not self.closing:
                messagebox.showerror(TITLE, e)

    def _slow(self):
        """Once a second: the game, the profile, a child window closing, settings.py changed by hand."""
        area = winapi.game_area() or ()    # () = looked, not found (None would mean "look it up")
        self._game_line(area)
        if self.child is not None and not self.child_open():
            self.child = None
            self._say(f"The {self.child_what} window is closed.\n")
            self._refresh_profile(force=True, area=area)
            self._controls(force=True)
        if self.busy():
            return
        self._refresh_profile(area=area)
        if settings_file.mtime() != self.loaded_mtime:
            if any(f.changed() for f in self.fields.values()):
                if not self.disk_warned:
                    self.disk_warned = True
                    self.lbl_saved.configure(text=f"{settings_file.PATH.name} was changed outside the window. "
                                                  "Save keeps those changes and yours.", foreground=RED)
            else:
                self.reload_settings()
                self._say(f"{settings_file.PATH.name} was changed outside the window, so it was read again.\n")

    def _set(self, widget, text, **kw):
        if self._shown.get(widget) != (text, kw):
            self._shown[widget] = (text, kw)
            widget.configure(text=text, **kw)

    def _status_lines(self):
        if self.job == "run" and self.status and self.keys:
            st, keys = self.status, self.keys
            if keys.paused:
                text = f"Paused. {winapi.key_name(cfg.PAUSE_KEY)} or Resume carries on."
            else:
                text = f"Running: {st.state}"
                if st.next_f is not None:
                    text += f". Next {winapi.pretty_key(cfg.ABILITY_KEY)} in {max(0, st.next_f - time.monotonic()):.0f} s"
            self._set(self.lbl_bot, text, foreground="")
            self._set(self.lbl_profile, f"Profile: {st.profile}" if st.profile else self.profile_text)
            s = dict(st.stats)             # a copy: the bot's thread may add a key meanwhile
            clicks = sum(v for k, v in s.items() if k.startswith("click"))
            routines = sum(v for k, v in s.items() if k.endswith(" routines"))
            mins = int((time.monotonic() - st.started) // 60) if st.started else 0
            self._set(self.lbl_counts, f"Matches {s.get('matches', 0)}   "
                                       f"{winapi.pretty_key(cfg.ABILITY_KEY)} {s.get('F presses', 0)}   "
                                       f"{winapi.pretty_key(cfg.HEAL_KEY)} {s.get('X presses', 0)}   Clicks {clicks}   "
                                       f"Smelts {routines}   Running for {mins // 60} h {mins % 60:02d} min")
            return
        if self.job == "keytest":
            text = "Key test: switch to the game now (in a match, somewhere safe)."
        elif self.job == "check":
            text = "Checking the screen: switch to the game now."
        elif self.child_open():
            text = f"Setup tool open ({self.child_what}). Close its window to use the bot again."
        elif self.settings_error:
            text = f"Can't start: {settings_file.PATH.name} can't be read."
        else:
            text = "Stopped"
        self._set(self.lbl_bot, text, foreground=RED if self.settings_error else "")
        self._set(self.lbl_profile, self.profile_text)
        if not self.job:
            self._set(self.lbl_counts, "")

    def _controls(self, force=False):
        running = self.job == "run"
        busy = self.busy()
        paused = bool(running and self.keys and self.keys.paused)
        sig = (running, busy, paused, bool(self.settings_error), self.has_routine, len(self.fields),
               cfg.PAUSE_KEY, cfg.QUIT_KEY)
        if not force and sig == getattr(self, "_ctl_sig", None):
            return
        self._ctl_sig = sig

        def on(widget, ok):
            widget.state(["!disabled"] if ok else ["disabled"])

        on(self.btn_start, not busy and not self.settings_error)
        on(self.btn_pause, running)
        on(self.btn_stop, running)
        self.btn_pause.configure(text=f"{'Resume' if paused else 'Pause'} ({winapi.key_name(cfg.PAUSE_KEY)})")
        self.btn_stop.configure(text=f"Stop ({winapi.key_name(cfg.QUIT_KEY)})")
        for b in (self.btn_keytest, self.btn_check, self.btn_setup):
            on(b, not busy and not self.settings_error)
        on(self.btn_save, not busy)
        on(self.btn_undo, not busy)
        for target, f in self.fields.items():
            f.enable(not busy and (self.has_routine or target not in SMELT_FIELDS))

    def _say(self, text):
        """Add text to the log box (not to bot.log: log() does both)."""
        box = self.logbox
        at_end = box.yview()[1] >= 0.999
        box.configure(state="normal")
        box.insert("end", text)
        lines = int(box.index("end-1c").split(".")[0])
        if lines > LOG_LINES:
            box.delete("1.0", f"{lines - LOG_LINES}.0")
        box.configure(state="disabled")
        if at_end:
            box.see("end")

    def on_close(self):
        self.cancel_capture()
        if self.job == "run":
            if not messagebox.askyesno(TITLE, "The bot is running. Stop it and close the window?"):
                return
            self.stop()
        elif self.job:
            self._say("Closing when the key test / check is done.\n")   # it takes a few seconds
        elif any(f.changed() for f in self.fields.values()):
            answer = messagebox.askyesnocancel(TITLE, "Save your changes to the settings first?")
            if answer is None or (answer and not self.save()):
                return
        self.closing = True
        if not self.job:
            self.root.destroy()
        # else: poll() closes the window once the run has stopped

    def selftest(self):
        """For build checks (BLOODHUNT_GUI_SELFTEST): what the window built -> a line of text."""
        return (f"OK: {len(self.fields)} fields, settings from {settings_file.PATH}, "
                f"{self.profile_text}; {self._shown.get(self.lbl_game, ('', {}))[0]}")


def main(profile_name=None):
    """Open the window. --profile NAME from the command line picks the profile, as for the commands.
    BLOODHUNT_GUI_SELFTEST=<file>: build the window hidden, write what it built (or the error) to the file,
    and close. Used to check a built exe, which has no console to print to."""
    selftest = os.environ.get("BLOODHUNT_GUI_SELFTEST")
    try:
        root = tk.Tk()
        if selftest:
            root.withdraw()
        root.report_callback_exception = lambda *exc: log(
            "window error:\n" + "".join(traceback.format_exception(*exc)))
        app = App(root, profile_name)
    except Exception:
        if selftest:
            Path(selftest).write_text("FAIL\n" + traceback.format_exc(), encoding="utf-8")
            sys.exit(1)
        raise
    if selftest:
        def finish():
            try:
                app.poll()
                Path(selftest).write_text(app.selftest(), encoding="utf-8")
            except Exception:
                Path(selftest).write_text("FAIL\n" + traceback.format_exc(), encoding="utf-8")
            root.destroy()
        root.after(1500, finish)
    root.mainloop()
