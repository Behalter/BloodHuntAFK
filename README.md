# Blood Hunt AFK

An AFK farming bot for **Marvel Rivals' Blood Hunt** PvE mode, for Windows. It watches the screen with OpenCV template matching and reacts to what it sees, instead of replaying a recorded macro. That way, varying round lengths, load times and lag can't knock it out of sync.

It's built around a solo Thor build that clears runs as long as the Awakening Rune (F) is kept up.

> **Use at your own risk.** Marvel Rivals' rules ban automation scripts and macros. Using this can get your account banned. It sends ordinary Windows input (`SendInput`) and makes no attempt to hide from anti-cheat.

## What it does

| Screen | The bot |
|---|---|
| In a match (HUD visible) | Presses F 1.5 s in, then every 69 s (rune 60 s + cooldown 9 s). F is sent 3 times over 0.55 s so it reliably fires. Heals with X every 2 s during each cooldown |
| Victory / Defeat | Clicks to skip, then **One more round** |
| "Gear limit exceeded" message | Runs the **storage-full routine**: Prepare → Forge → filter to gear rated 5600 or below → Select all → Smelt → confirm → back to Play → Start |
| Anything it doesn't recognise | Waits. Every 10 minutes of that, it saves a screenshot to `debug\` |

Other things it handles:
- **Second monitor.** If you click away from the game, it skips its presses and clicks until you come back, and never steals focus. It only brings the game back itself after 2 minutes of no mouse or keyboard input.
- **Retries.** A button that's still showing 5 s after being clicked gets clicked again.
- **Dimmed buttons.** A greyed-out button (behind a translucent layer) is never clicked.
- **Failed routine.** If nothing is recognised within a minute of the storage-full routine, the bot stops and saves a screenshot.

## Setup

1. Install **Python 3** from python.org (tick "Add python.exe to PATH").
2. In this folder:
   ```powershell
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
3. Put the game in **Borderless / Windowed Fullscreen** on your **main** monitor.
4. Run the terminal **as administrator**. The game ignores input from programs with lower rights.
5. `keytest` checks that the game accepts the bot's key presses.

The included profile `profiles/1080p/` is for **1920x1080**. For another resolution, make a new profile (below).

## Commands

Run these from this folder with `.venv\Scripts\python.exe BloodHuntAFK.py <command>`. Any command takes `--profile NAME`.

| Command | What it does |
|---|---|
| `keytest` | After 5 s, presses F the way `run` does (3 times over 0.55 s) |
| `run` | The bot. **F8** = pause/resume, **F10** = quit |
| `snap` | F8 saves a screenshot to the profile's `shots\`. `snap --profile NEWNAME` starts a new profile for your screen size |
| `crop NAME [SHOT]` | Pick a screenshot, drag a box around something, and Enter saves it as a template |
| `check [SHOT]` | Scores every template against the screen (or a screenshot) and saves `debug\check.png` |
| `routine check` | Draws every routine click spot on its screenshot (`debug\routine_*.png`) |
| `routine run` | Runs the storage-full routine once, starting from the Victory/Defeat screen |

## Templates and profiles

Everything that depends on screen resolution lives in `profiles/<name>/`:

- `templates/`: cropped images. The file-name prefix says what the bot does when it sees one:
  - `click_*`: click it.
  - `ingame*`: we're in a match.
  - `stop_*`: stop the bot.
  - `routine_<name>*`: run that routine.

  Each has a `.json` beside it recording where it was cropped, so it's only looked for around that spot.
- `profile.json`: screen size, buttons clicked at a fixed spot, and the routine steps. A step is `"click": [x, y]`, `"key": "space"` or `"type": "5600"`, plus how long to wait after it.
- `shots/`: screenshots from `snap` (not committed).

The profile matching your main screen's size is picked automatically.

### Routine screenshots (for `routine check`)

`routine check` draws each routine step's click spot on a screenshot of the screen that step happens on, so you can check the spots by eye. Those screenshots live in `profiles/<name>/routines/<routine>/`, and each step in `profile.json` names its own in `"shot"` (e.g. `"04_filter.png"`).

**They aren't in this repo** because they show the in-game UID. On a fresh clone, `routine check` still works, but it draws the crosses on a plain grey background labelled `(no screenshot: ...)`. Running the routine doesn't need them.

To check the spots against your own screen:

1. Run `snap`. Then do the routine by hand in the game, pressing **F8** on each screen to save it to the profile's `shots\` folder. Take one screenshot per distinct screen; several steps can share one (for example, all the Gear Filter steps use `04_filter.png`).
2. Copy each screenshot into `profiles\<name>\routines\storage_full\` and rename it to the `"shot"` name its steps use in `profile.json`:

   | File | Screen |
   |---|---|
   | `01_results.png` | Victory or Defeat, with PREPARE showing |
   | `02_hero.png` | Hero tab, after clicking PREPARE |
   | `03_forge.png` | Forge tab (Scrap) |
   | `04_filter.png` | Gear Filter open |
   | `05_forge_filtered.png` | Forge after CONFIRM in the filter |
   | `06_selected.png` | After SELECT ALL |
   | `06b_smelt_confirm.png` | The "Currently contains Legendary quality gear" popup after SMELT |
   | `07_acquired.png` | "Acquired" rewards |
   | `08_forge_smelted.png` | Forge after the rewards are dismissed |
   | `09_overview.png` | Overview tab |
   | `10_play.png` | Play screen with START |

3. Run `routine check` again and open `debug\routine_storage_full_NN.png`. Each magenta cross should sit in the middle of the button that step clicks. If one is off, change that step's `"click": [x, y]` in `profile.json`. Screenshots from `snap` use real screen pixels, so you can read the x, y straight off them in any image viewer.

The coordinates in `profiles/1080p/profile.json` only fit a 1920x1080 screen. For another resolution, make a new profile and measure every step this way.

## Settings

Timings and keys are in [`bloodhunt/settings.py`](bloodhunt/settings.py), each with a comment explaining it: rune duration and cooldown, heal interval, scan rate, match threshold, retry and focus timings, and a run-time limit (10 h by default).

## Code layout

```
BloodHuntAFK.py        entry point and usage text
bloodhunt/
  bot.py               the main loop
  routines.py          running and drawing routines
  vision.py            screen capture and template matching
  profiles.py          loading profiles
  inputs.py            key presses, clicks, typing
  winapi.py            window focus, hotkeys, idle time
  commands.py          the command-line commands
  settings.py          settings
  common.py            logging and file helpers
```

`BOT_NOTES.md` explains the loop step by step and the reasons behind each behaviour. `CLAUDE.md` is the project memory used with Claude Code.
