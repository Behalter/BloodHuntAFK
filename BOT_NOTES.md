# Blood Hunt AFK bot: how the code works

Notes for whoever (human or agent) edits the code. `CLAUDE.md` has the project history, the user's decisions and the pending work; this file describes the code as it is.

## What it does

It farms Marvel Rivals' **Blood Hunt** PvE mode solo, on Windows, overnight. The user's Thor build clears runs as long as **F (Awakening Rune)** is pressed on a timer, with **X (heal)** pressed during the rune's cooldown. One round:

1. **Match:** first F 1.5 s after the HUD shows, then F every 69 s, with X every 2 s through each cooldown (62–68 s after each F).
2. **MVP animation:** wait.
3. **Victory/Defeat screen:** click the SPACE box next to "HOLD TO SKIP" (a fixed spot).
4. **"One more round":** click it. It comes back **dimmed** just before character select, and the bot doesn't click it then.
5. **Character select:** nothing. The game picks Thor.

When loot storage is full, "One more round" doesn't start a round, and a message shows briefly. When the bot sees that message (a `routine_storage_full` template), it runs the **storage-full routine** from the profile: Prepare → Forge → Filter → click the rating box and type 5600 → Confirm → Select All → Smelt → Confirm (the Legendary warning) → Space → Overview → Play Now → Start. Then it carries on.

It reads the screen instead of replaying recorded inputs. Every ~1.5 s it takes a screenshot and looks for small images ("templates") the user cropped from their own screenshots. A template's **filename prefix** decides what happens when it's seen.

## Requirements and running

- Windows only. Python 3 with `pip install mss opencv-python numpy pydirectinput` (a `.venv` in the project folder).
- `python BloodHuntAFK.py <command> [--profile NAME]`. Simulated input has been confirmed to work at normal privilege on the user's machine.

```
keytest            5 s countdown, presses F the way `run` does (3 times over 0.55 s), prints the foreground window title/class
snap               F8 = save a screenshot to the profile's shots\ (and print every template's score), F10 = quit
                   snap --profile NEWNAME creates a profile for the current screen size
crop NAME [SHOT]   pick one of the profile's screenshots (or give one), drag a box -> templates\NAME.png + NAME.json
check [SHOT]       score every template vs the live screen (5 s countdown) or a screenshot;
                   writes debug\check.png (green match, red no match, yellow search area, magenta click spot)
run                the farming loop. F8 = pause/resume, F10 = quit
routine check      draw each routine step's click (numbered magenta cross) on its screenshot -> debug\routine_<name>_NN.png
routine run        do the routine once now (5 s countdown; start on the Victory/Defeat screen), then exit
```

## Files

| Path | What it is |
|---|---|
| `BloodHuntAFK.py` | Entry point: the usage text (`__doc__`) and a call to `commands.main()` |
| `bloodhunt/__init__.py` | Windows check and DPI awareness. Runs before any other module, so before `mss`/`pydirectinput` are imported |
| `bloodhunt/settings.py` | Every tunable setting (timings, keys, thresholds, window title) |
| `bloodhunt/common.py` | Paths (`HERE`, `PROFILES`, `DEBUG`, `LOGFILE`), `log`, `rel`, `stamp`, `beep`, `countdown`, `imread`/`imwrite` |
| `bloodhunt/winapi.py` | `user32` prototypes, game window detection and focus, user idle time, `Hotkeys` (F8/F10) |
| `bloodhunt/vision.py` | `Screen` (capture), `Template`, `find`/`best`/`report`, `click_point`, `warn_size` |
| `bloodhunt/profiles.py` | `Profile`, choosing and creating profiles |
| `bloodhunt/inputs.py` | `press`, `click` (pydirectinput) |
| `bloodhunt/bot.py` | The loop (`run`) and the F/X timing (`Presses`) |
| `bloodhunt/routines.py` | Running a routine's steps (`run`, `wait_for_game`) and drawing them (`draw`) |
| `bloodhunt/commands.py` | `run`, `snap`, `crop`, `check`, `keytest`, `routine`, the `--profile` argument |
| `profiles/<name>/` | One folder per screen resolution (below) |
| `debug/` | `check.png`, `stuck_*`, `noeffect_*`, `stop_*`, `routine_<name>_*` (trigger seen), `routine_failed_*`, `routine_<name>_NN.png` (from `routine check`) |
| `bot.log` | Timestamped log, appended on every run |

All paths are relative to the project folder, not the current working directory.

## Profiles (one per resolution)

```
profiles/<name>/profile.json   {"screen": [1920, 1080], "click_at": {...}, "routines": {"storage_full": [steps]}}
profiles/<name>/templates/     NAME.png + NAME.json  {"x","y","w","h","screen_w","screen_h"}: where it was cropped
profiles/<name>/shots/         screenshots from snap
profiles/<name>/routines/<routine>/   the screenshots each routine step was measured on
```

- `click_at`: buttons clicked at a fixed spot (that profile's screen pixels) instead of the centre of the match. `click_skip` needs it because matching finds both SPACE boxes (the NEXT one scores 0.895).
- `routines`: name → steps, in order. A step is `{"name", "click": [x, y] | "key": "space" | "type": "5600", "wait": seconds after it, "shot": file in routines/<routine>/}`. Validated on load (`profiles._step`).
- The 1080p step screenshots came from the user in chat. They're **1919x1079, missing the leftmost column**, so screen x = screenshot x + 1, and the stored clicks already include the +1. They also went through a different capture path: the real One more round template scores only 0.84 on them. Use them for click positions only, never for cropping templates.
- **Choosing:** `--profile NAME` if given. Otherwise the one profile whose `screen` equals the main screen's size (for `run`, `snap`, live `check`, and `crop` without a screenshot). With a screenshot (`check SHOT`, `crop NAME SHOT`), the profile folder it's in, else the profile for its size. No match or several matches: exit with a message listing the profiles.
- `run`, `snap` and live `check` refuse a profile whose size differs from the main screen. `crop` refuses a screenshot whose size differs from the profile.
- A screenshot can be named by file name alone. It's looked up in every profile's `shots/`.
- A different aspect ratio (e.g. a 16:10 laptop) changes the game's UI layout, so each profile has its own crops and click spots.
- Only `1080p` (1920x1080) exists so far. It holds `click_one_more_round`, `click_skip`, `ingame_lshift`, `ingame_portrait`, and the `storage_full` routine. Its trigger template (`routine_storage_full`) doesn't exist yet: the user has to crop it from the first real storage-full screen.

### Template naming = behaviour

The prefix match is case-insensitive. Other names are ignored, with a log line.

| Prefix | Meaning |
|---|---|
| `click…` | Click it when it's visible and not dimmed (at its `click_at` spot, else its centre) |
| `ingame…` | While any is visible we're in a match: the F/X timer runs. With **no** `ingame` templates, every screen counts as a match |
| `stop…` | Save a screenshot and stop the bot |
| `routine_<routine>…` | Run that routine from `profile.json` (e.g. `routine_storage_full.png` → `storage_full`; the longest matching routine name wins). One that matches no routine is ignored, with a log line |

## The loop (`bot.run`)

Each iteration, in order:

1. **Hotkeys and limits.** Poll F8/F10. Stop after `MAX_HOURS`.
2. **Focus.** If the game isn't the front window, the bot skips all input and **never steals focus**. Exception: after `IDLE_BEFORE_REFOCUS` (120 s) with no mouse/keyboard input, it brings the game back with `ensure_focus()`, at most every `REFOCUS_EVERY`. **When the game is back in front** (you clicked back in, or `ensure_focus` succeeded), it sleeps `FOCUS_SETTLE` (1.5 s) and starts the iteration over, so the first input comes after the wait, based on a fresh screenshot. Reason: games often swallow input right after regaining focus; that's how a skip click was lost on the real game. `act()` refuses input while `away_since` is set, so nothing slips through between noticing the return and the wait.
3. **Capture.** `mss` grabs the primary monitor, converted BGRA → BGR, shrunk by `MATCH_SCALE`. On the first frame, `warn_size` logs templates cropped at a different size. If a screenshot was requested for "the next frame" (`save_next`, see the streak below), it's saved now.
4. **After a routine:** if nothing has been recognised `ROUTINE_RECOVER` (60 s) after the routine finished, save `debug/routine_failed_*.png` and stop.
5. **Stop signs.** Any `stop` match: save `debug/stop_*.png`, stop.
6. **Routine triggers** (before buttons). A `routine_*` match: save `debug/routine_<name>_*.png`, run the routine (below), then `presses = None`, clear the button state, and start the 60 s recovery clock. If a trigger is seen again **before any match has started** since the last routine (smelting freed nothing), stop instead of looping.
7. **Buttons.** The best-scoring armed, not-dimmed `click` template is clicked, then the mouse goes back to the screen centre (where the game leaves it). After a click: `presses = None`, wait `AFTER_CLICK_WAIT` (4 s), `continue`. Buttons in `AFTER_CLICK_WAIT_FOR` wait less: "One more round" waits 1.5 s, because the storage-full message only shows briefly. While the clicked button is still visible, the bot keeps scanning every 1.5 s, so it looks for the message at about 1.5, 3 and 4.5 s after the click.
   - **Retry:** a clicked button is disarmed for `REPEAT_CLICK_AFTER` (5 s). If it's still on screen after that, it's clicked again, so a retry lands about 5–6 s after the previous click. While disarmed and still visible, the bot just waits.
   - **Streak:** clicking the same button again without it ever leaving the screen counts as a retry (logged as "try N"). On the `NO_EFFECT_AFTER`th (3rd) click it saves one `debug/noeffect_<button>_*.png` of the **next** frame, i.e. what the screen shows the after-click wait later (1.5 s for One more round, so with full storage it shows the message). Then it keeps retrying. The streak resets on any scan where no button is visible.
   - **Dimmed:** `TM_CCOEFF_NORMED` ignores brightness, so a dimmed button still scores about 1.0. `find()` also returns its contrast (std dev of the matched area / the template's). Under `CLICK_MIN_CONTRAST` (0.8), it's never clicked. Clicking it would be harmless (the user confirmed), but it's skipped anyway.
8. **In a match?** Any `ingame` template matches. Also clears "a routine ran and no match has started since".
9. **F and X** (`Presses`): only when in a match **and** the game is in front (and settled), the same rules for both keys.
   - First F `FIRST_PRESS_DELAY` (1.5 s) after the HUD is first seen. It's timed from that sighting, and the bot wakes up exactly when F is due, so it doesn't need to line up with `SCAN_EVERY`. 0 = press on the same scan that first sees the HUD. After each F at time *t*: X every `HEAL_EVERY` (2 s) from *t* + `F_DURATION` + `HEAL_EVERY` until the next F (62, 64, 66, 68 s; the user found two heals at 63 s and 66 s weren't enough), and the next F at *t* + `F_DURATION` + `F_COOLDOWN` (69 s). Each is timed from the **actual** F press, so a late F moves everything after it.
   - **No backlog:** a press that couldn't be made stays due and is made late, but only while it's the latest one due. When a later one is due too, only the latest is pressed and the earlier ones are dropped. There's at most one press per scan, so it never bursts. Consequence: an X made late shortly before the next X is due is followed by that X a moment later. Both were on the schedule.
   - HUD hidden (cutscene, death): nothing is pressed. If it's gone longer than `MATCH_LOST_GRACE` (30 s), the match counts as over (`presses = None`), and the next HUD starts over with the `FIRST_PRESS_DELAY`.
10. **Stuck watchdog.** Nothing recognised (button, HUD or stop sign) for `STUCK_AFTER` (10 min) → `debug/stuck_*.png`, at most `STUCK_SHOTS_MAX` (6) in a row until something is recognised again.
11. **Sleep** `min(SCAN_EVERY, time until the next press that isn't due yet)`. Overdue presses are retried at the normal scan rate. The old code slept 0.05 s and re-scanned constantly while a press was overdue. `Hotkeys.sleep()` polls hotkeys every 50 ms and doesn't return while paused (on purpose).

On exit it logs the runtime and counts (clicks per button, F presses, X presses, routines).

## Routines (`routines.run`)

- Steps run strictly in order. Before **each** step, `wait_for_game()` waits until the game is the front window. It never steals focus, except after `IDLE_BEFORE_REFOCUS` of user idleness, the same as the main loop. If it had to wait, it sleeps `FOCUS_SETTLE` first. A step is never skipped, because the steps are a sequence.
- Click: `inputs.click(x, y)` with no mouse parking (nothing is matched during a routine, so hover doesn't matter). Key: `inputs.press(key)`. Type: `inputs.type_text(text, TYPE_GAP)`, one key press per character (~0.18 s each; `inputs.key_for` maps characters to keys, and `_step` rejects text with capitals or Shift symbols). Then sleep the step's `wait`. Waits are fixed: there are no per-step image checks yet (deferred by the user).
- F8 pauses mid-routine; F10 aborts it (and the bot).
- `storage_full` on 1080p: Prepare 1391,949 (wait 7) · Forge tab 571,38 (2) · Filter 197,172 (2) · Rating box 1177,537 / type 5600 / Confirm 794,882 (0.5 each; clicking the box selects the old value, so typing replaces it. This replaced ticking Normal/Advanced/Rare/Epic, at the user's request) · Select all 231,922 (0.5) · Smelt 1305,864 (3.5) · Confirm smelt 794,829 (5; the "Currently contains Legendary quality gear" popup, which the rating filter brings up. When there's no popup, that spot is empty background on both the Forge and Acquired screens, so the click does nothing) · Space (0.5) · Overview tab 350,38 (1.5) · Play now 1377,970 (3) · Start 1689,893 (0). About 27 s in all. Run on the real game by the user (2026-11-21), both the rarity version and the rating version: works. LEGENDARY's checkbox is 800,378 and must never be clicked.
- `routine check` draws every step for eyeballing. `routine run` runs it once by hand.

## Image matching

- `cv2.matchTemplate(..., TM_CCOEFF_NORMED)` on colour images, frame and template both shrunk by `MATCH_SCALE` (0.5). NaN/inf (flat areas) → 0.
- **Location lock:** a template with a `.json` is only searched for within `SEARCH_MARGIN` (80 px) of where it was cropped, so the same picture elsewhere (Thor's portrait on character select) can't fool it.
- `crop` snaps boxes to even pixels. Matching runs at half scale, and an odd offset costs about 0.12 of score.
- `find()` returns `(score, centre in full-size screen pixels, contrast)`. `best()` returns the highest-scoring template at or above `MATCH_THRESHOLD` (0.80), optionally skipping dimmed ones.
- Single scale only: templates work at the resolution they were cropped at. That's why there are profiles.
- Crop from `snap` screenshots (same capture pipeline as the live matcher), not the Snipping Tool.
- Real scores on the user's screenshots: matches 1.00, non-matches 0.06–0.42.
- Images are read and written with `np.fromfile`/`imdecode` and `imencode`/`tofile`, because plain `cv2.imread` breaks on non-ASCII Windows paths.

## Input and Windows plumbing

- `pydirectinput` sends `SendInput` with scan codes. Key: down, 80 ms, up. Click: move, 150 ms (hover), down, 70 ms, up, then 100 ms and move to the screen centre. `PAUSE = 0.05`.
- pydirectinput's absolute coordinates only reach the **primary monitor**, so `Screen` always captures the primary: the monitor whose top-left is (0, 0). Don't use a fixed `mss` index. `monitors[1]` was the laptop screen on the user's machine.
- Failsafe stays on: mouse into the top-left corner raises `FailSafeException`, which `main()` logs as a clean stop.
- DPI awareness (`SetProcessDpiAwareness(2)`, falling back to `SetProcessDPIAware`) is set in `bloodhunt/__init__.py`, before `mss` and `pydirectinput` are imported, so captures and clicks are in physical pixels on scaled displays.
- `is_game()`: the title contains `GAME_TITLE` ("Marvel Rivals"; the real title is "Marvel Rivals  ") **and** the class is `GAME_CLASS` ("UnrealWindow"). Both have been confirmed on the real game.
- `ensure_focus()` restores the game if minimised, taps Alt around `SetForegroundWindow` (Windows only lets a background process take focus right after a key event), waits 0.5 s and re-checks.
- Hotkeys use `GetAsyncKeyState` polling, so they work while the game has focus.

## Settings (`bloodhunt/settings.py`)

| Setting | Default | Meaning |
|---|---|---|
| `ABILITY_KEY` / `HEAL_KEY` | `"f"` / `"x"` | Keys pressed in a match |
| `ABILITY_PRESSES` / `ABILITY_SPAN` | `3` / `0.55` | Each F is sent 3 times, starting at 0, 0.275 and 0.55 s (`inputs.press_repeated`, timed by the clock). A single F sometimes didn't fire; once it does, the animation stops the later presses from cancelling it (the user tested this). X is still one press |
| `F_DURATION` / `F_COOLDOWN` | `60` / `9` | Rune duration and cooldown. F every 69 s. The user is still tuning these |
| `HEAL_EVERY` | `2` | X every this many seconds through the cooldown, first one this long after F ends (0 = none) |
| `FIRST_PRESS_DELAY` | `1.5` | First F after the HUD is first seen (prep is ~15 s, F works in it). Was 10; the user lowered it because the X heals during each cooldown make the exact F timing unimportant |
| `MATCH_LOST_GRACE` | `30` | HUD can vanish this long before the match counts as over |
| `AFTER_CLICK_WAIT` | `4` | Pause after a click |
| `AFTER_CLICK_WAIT_FOR` | `{"click_one_more_round": 1.5}` | Per-button exceptions to `AFTER_CLICK_WAIT` |
| `TYPE_GAP` | `0` | Extra seconds between characters in a `type` step |
| `ROUTINE_RECOVER` | `60` | After a routine, something must be recognised within this long, or stop |
| `REPEAT_CLICK_AFTER` | `5` | A button still on screen this long after its click is clicked again |
| `NO_EFFECT_AFTER` | `3` | Clicks without the button leaving before a `noeffect_` screenshot |
| `CLICK_MIN_CONTRAST` | `0.80` | Below this a button counts as dimmed |
| `MATCH_THRESHOLD` | `0.80` | Minimum score for a match |
| `SCAN_EVERY` | `1.5` | Seconds between screen checks |
| `MATCH_SCALE` / `SEARCH_MARGIN` | `0.5` / `80` | Downscale before matching; search area around a template's spot (`None` = whole screen) |
| `GAME_TITLE` / `GAME_CLASS` | `"Marvel Rivals"` / `"UnrealWindow"` | Window identification |
| `FOCUS_SETTLE` | `1.5` | Wait after the game is back in front before any input |
| `IDLE_BEFORE_REFOCUS` / `REFOCUS_EVERY` | `120` / `30` | When the bot may bring the game back itself, and how often it tries |
| `STUCK_AFTER` / `STUCK_SHOTS_MAX` | `600` / `6` | Stuck-screenshot timing and cap |
| `MAX_HOURS` | `10` | Auto-stop (0 = never) |
| `PAUSE_KEY` / `QUIT_KEY` | F8 / F10 | Virtual-key codes |

## Testing

- **Never drive the real game from an agent.** The user runs `run` themselves.
- `check` against the screenshots in `profiles/1080p/shots/` is safe and quick.
- The loop has been tested in a simulation: `time.monotonic`/`time.sleep` replaced by a fake clock; `vision.Screen`, `winapi.game_in_front`/`ensure_focus`/`user_idle_seconds`, `Hotkeys.poll`, `inputs.press`/`click` and `bot.log`/`countdown`/`imwrite` replaced by a scripted fake game built from the user's real screenshots (the dimmed button made by darkening the Victory screenshot). Cases covered: normal rounds (first F at `FIRST_PRESS_DELAY`, then X+63, X+66, F+69 exactly, with the old `HEALS_PER_COOLDOWN` = 2; run with the old 10 s delay); tabbed out on the skip screen with the game swallowing clicks for 1 s after focus (the click lands 1.7 s after returning, first try); the same with the settle wait off (the 5 s retry rescues it); a button ignoring 4 clicks (retries 5.6 s apart, one `noeffect` screenshot at the 3rd); tabbed out across the cooldown (only the latest due press fires, never a burst); HUD hidden across due presses; focus stolen while idle; the dimmed button on screen for 20 s (never clicked); profile choosing and `crop`.
- Routine cases, with a made-up "STORAGE FULL" message drawn on the One more round screenshot as the trigger, and a fake game that walks the menus. The fake game fails the test on a click outside the expected button, before a menu has loaded, on LEGENDARY, or Confirm with the wrong boxes ticked. (This ran with the old rarity steps, before the `type` step.) Covered: message shown 2 s and 1.6 s (caught 1.6 s after the click); all 14 steps (now 13) in order; tabbed out 25 s mid-routine (waits, settles, skips nothing); smelting frees nothing (stops instead of looping); Start does nothing (stops 60 s later with `routine_failed`); no trigger template (the `noeffect` screenshot shows the message).
- Because everything goes through module attributes (`inputs.click`, `winapi.game_in_front`, `cfg.X`), these can be patched for tests. Keep calls in that form, not `from .inputs import click`.

## Things to be careful with when editing

- Keep the DPI setup in `bloodhunt/__init__.py`, ahead of any `mss`/`pydirectinput` import.
- `find()` expects an already **shrunk** frame. Don't shrink twice, and scale coordinates back up.
- Clicks go through `screen.to_screen(pos)` (monitor offset) and through `act()` (focus and settle).
- `presses = None` means "no match in progress". Reset it after clicking a button and after `MATCH_LOST_GRACE`.
- Settings are read as `cfg.NAME` at call time, so changing `settings.py` (or patching it in a test) takes effect everywhere.
