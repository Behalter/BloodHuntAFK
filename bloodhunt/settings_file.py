"""settings.py as a file: reading its values without running it, and changing a value in place.

Every setting lives in one file: bloodhunt\\settings.py from source, settings.py next to the exe in the
release. The exe can't import a file from its folder (PyInstaller bakes the bundled copy in), and the window
must change a value without touching the comments around it. So the file is read with Python's parser,
never run: every line is NAME = value with a plain value (a number, "text", True/False/None or {...}),
read with ast.literal_eval. save() replaces only the text of the values it changes.

Each setting's comment (on its line, the indented comment lines under it, and inside its {...}) is its
help text in the window. A comment starting with "..." continues the one of the setting above. A
`# ── Name ──` line starts a section, and comment lines at column 0 right under it describe the section.
"""
import ast
import io
import json
import os
import re
import shutil
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

from . import settings as cfg
from .common import BUNDLE, FROZEN, HERE

PATH = HERE / "settings.py" if FROZEN else Path(cfg.__file__).resolve()
BUILT_IN = BUNDLE / "defaults" / "settings.py"      # the exe's own copy, put back if settings.py is deleted
DEFAULTS = {k: getattr(cfg, k) for k in dir(cfg) if k.isupper()}   # the built-in values (before load())
NONE_OK = {"SEARCH_MARGIN"}                         # settings that may also be None
_SECTION = re.compile(r"#\s*─+\s*(.*?)\s*─*\s*$")


class SettingsError(Exception):
    """settings.py can't be read or changed. The message names the line."""


@dataclass
class Setting:
    name: str
    value: object
    line: int                  # where it starts, 1-based
    section: str
    help: str                  # its own comment
    span: tuple                # (line, col, end_line, end_col) of the value's text; columns in characters
    entries: dict = field(default_factory=dict)    # a {...}: key -> (value, span)
    group: list = field(default_factory=list)      # it and the settings its comment runs on with ("...")


@dataclass
class Section:
    name: str
    about: str
    settings: list             # setting names, in file order


def _col(text, byte_col):
    """ast gives columns in UTF-8 bytes; the line is a str."""
    return len(text.encode("utf-8")[:byte_col].decode("utf-8", errors="ignore"))


def _span(lines, node):
    return (node.lineno, _col(lines[node.lineno - 1], node.col_offset),
            node.end_lineno, _col(lines[node.end_lineno - 1], node.end_col_offset))


def parse(text):
    """-> (sections, {name: Setting}), both in file order. Raises SettingsError naming the line."""
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        raise SettingsError(f"line {e.lineno}: {e.msg}") from None
    lines = text.split("\n")
    comments = {}                                  # line -> (column, text after the #)
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            comments[tok.start[0]] = (tok.start[1], tok.string[1:].strip())

    def comment_only(n):
        return n in comments and not lines[n - 1][:comments[n][0]].strip()

    headers = {}                                   # line -> (section name, about)
    for n in sorted(comments):
        col, body = comments[n]
        m = _SECTION.match(lines[n - 1].strip())
        if col == 0 and comment_only(n) and "─" in body and m:
            name, _, rest = m.group(1).partition(" (")
            about = [rest.rstrip(")")] if rest else []
            k = n + 1
            while comment_only(k) and comments[k][0] == 0 and not _SECTION.match(lines[k - 1].strip()):
                about.append(comments[k][1])
                k += 1
            headers[n] = (name.strip(), " ".join(about))

    sections, settings = [], {}
    current = Section("Other", "", [])
    header_lines = sorted(headers)
    for i, node in enumerate(tree.body):
        if i == 0 and isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant):
            continue                               # the docstring
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            raise SettingsError(f"line {node.lineno}: only NAME = value lines can be in this file")
        name = node.targets[0].id
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            raise SettingsError(f"line {node.lineno}: {name}'s value must be plain: a number, \"text\", "
                                "True/False/None or {...}") from None
        above = [h for h in header_lines if h < node.lineno]
        sec_name, about = headers[above[-1]] if above else ("Other", "")
        if sec_name != current.name or not sections:
            current = next((s for s in sections if s.name == sec_name), None) or Section(sec_name, about, [])
            if current not in sections:
                sections.append(current)
        help_parts = [comments[n][1] for n in range(node.lineno, node.end_lineno + 1) if n in comments]
        k = node.end_lineno + 1
        while comment_only(k) and comments[k][0] > 0:       # indented comment lines under it
            help_parts.append(comments[k][1])
            k += 1
        s = Setting(name, value, node.lineno, sec_name, " ".join(help_parts), _span(lines, node.value))
        if isinstance(node.value, ast.Dict):
            for kn, vn in zip(node.value.keys, node.value.values):
                if isinstance(kn, ast.Constant):
                    s.entries[kn.value] = (ast.literal_eval(vn), _span(lines, vn))
        settings[name] = s
        current.settings.append(name)

    group = []
    for s in settings.values():                    # "..." joins a setting's help to the one above
        if group and s.help.startswith("...") and s.section == group[-1].section:
            group.append(s)
        else:
            group = [s]
        s.group = group
    return sections, settings


def _kind(v):
    if isinstance(v, bool):
        return "True or False"
    if isinstance(v, (int, float)):
        return "a number"
    if isinstance(v, str):
        return "text in quotes"
    if isinstance(v, dict):
        return "a {...} list"
    return "None" if v is None else type(v).__name__


def check_kinds(settings):
    """A setting the bot knows must hold the same kind of value as its built-in one (a number stays a
    number), so a slip in a hand edit is reported here, not as a crash in the middle of a run."""
    for s in settings.values():
        if s.name in DEFAULTS:
            want, got = _kind(DEFAULTS[s.name]), _kind(s.value)
            if got != want and not (got == "None" and s.name in NONE_OK):
                raise SettingsError(f"line {s.line}: {s.name} should be {want}, not {s.value!r}")


def ensure_file():
    """The release ships settings.py next to the exe. If it's gone, put the built-in copy back -> True."""
    if FROZEN and not PATH.exists() and BUILT_IN.exists():
        shutil.copyfile(BUILT_IN, PATH)
        return True
    return False


def read(path=None):
    """-> (sections, {name: Setting}) from settings.py. Raises SettingsError."""
    path = Path(path or PATH)
    try:   # utf-8-sig: Notepad's "UTF-8 with BOM" puts a mark first, which Python's parser rejects
        text = path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError) as e:
        raise SettingsError(f"can't read {path}: {e}") from None
    sections, settings = parse(text)
    check_kinds(settings)
    return sections, settings


def load(path=None):
    """Read settings.py and put its values into the settings module, which every other module reads
    (cfg.NAME, at the moment it's needed). A setting missing from the file gets its built-in value.
    -> (sections, {name: Setting}). Raises SettingsError, and then changes nothing."""
    sections, settings = read(path)
    for name, value in DEFAULTS.items():
        setattr(cfg, name, settings[name].value if name in settings else value)
    for s in settings.values():
        if s.name not in DEFAULTS:
            setattr(cfg, s.name, s.value)
    return sections, settings


def mtime(path=None):
    try:
        return Path(path or PATH).stat().st_mtime_ns
    except OSError:
        return None


def format_value(value, old_text=""):
    """A value as it's written in the file. Keeps the hex style of key codes (0x77)."""
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, int):
        return f"0x{value:02X}" if old_text.lower().startswith("0x") else str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise SettingsError(f"can't write {value!r} into the file")


def _replace(text, col, end_col, new):
    """Put `new` in place of text[col:end_col], keeping a comment after it where it was if there's room."""
    before, after = text[:col], text[end_col:]
    m = re.match(r"(,?)(\s+)(#.*)$", after)          # the comma: an entry of a {...}
    if m:
        gap = len(m.group(2))
        after = m.group(1) + " " * max(min(gap, 2), gap - (len(new) - (end_col - col))) + m.group(3)
    return before + new + after


def save(changes, path=None):
    """Write new values into settings.py. changes: {NAME: value}, or {(NAME, key): value} for one entry of
    a {...}. Only the text of each value changes: comments, spacing and everything else stay. Checked by
    reading the result back before it replaces the file. Raises SettingsError."""
    path = Path(path or PATH)
    try:
        raw = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise SettingsError(f"can't read {path}: {e}") from None
    bom = "﻿" if raw.startswith("﻿") else ""     # kept as the file had it (see read())
    newline = "\r\n" if "\r\n" in raw else "\n"
    text = raw[len(bom):].replace("\r\n", "\n")
    _, settings = parse(text)
    lines = text.split("\n")
    edits = []
    for target, value in changes.items():
        name, key = target if isinstance(target, tuple) else (target, None)
        s = settings.get(name)
        if s is None:
            raise SettingsError(f"{name} isn't in {path.name}")
        if key is None and isinstance(s.value, dict):
            raise SettingsError(f"{name} is a {{...}} list: change one entry of it")
        if key is not None and key not in s.entries:
            raise SettingsError(f"{name} has no entry {key!r}")
        current = s.value if key is None else s.entries[key][0]
        if current == value and (type(current) is bool) == (type(value) is bool):
            continue                       # unchanged: leave its text alone (0.80 stays 0.80)
        line, col, end_line, end_col = s.span if key is None else s.entries[key][1]
        if line != end_line:
            raise SettingsError(f"line {line}: {name}'s value is on several lines: change it in the file")
        edits.append((line, col, end_col, format_value(value, lines[line - 1][col:end_col])))
    if not edits:
        return                             # every value was already that: leave the file alone
    for line, col, end_col, new in sorted(edits, reverse=True):   # right to left, so columns stay right
        lines[line - 1] = _replace(lines[line - 1], col, end_col, new)
    out = "\n".join(lines)
    _, after = parse(out)
    for target, value in changes.items():
        name, key = target if isinstance(target, tuple) else (target, None)
        got = after[name].value if key is None else after[name].entries[key][0]
        if got != value or (type(got) is bool) != (type(value) is bool):
            raise SettingsError(f"writing {name} didn't work (read back {got!r}, wanted {value!r})")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes((bom + out.replace("\n", newline)).encode("utf-8"))
    os.replace(tmp, path)
