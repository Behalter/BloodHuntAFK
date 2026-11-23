# Blood Hunt AFK

An AFK farming bot for **Marvel Rivals' Blood Hunt** mode, for Windows specifically. It watches the screen with OpenCV template matching and reacts to what it sees, instead of replaying a recorded macro. That way, varying round lengths, load times and lag can't knock it out of sync.

It's built around a solo Thor build that clears runs as long as the Awakening Rune (F) is kept up. If you don't have a build that can AFK-clear the round, then this won't work for you.

> **Use at your own risk.** Marvel Rivals' rules ban automation scripts and macros. Using this can get your account banned. It sends ordinary Windows input (`SendInput`) and makes no attempt to hide from anti-cheat.

## What it does

| Screen | The bot |
|---|---|
| In a match (HUD visible) | Presses F as the match starts, then again each time the rune's duration and cooldown have passed (set them for your gear in the window). Each F is sent as a quick burst so it reliably fires. Heals with X during each cooldown |
| Victory / Defeat | Clicks to skip, then **One more round** |
| "Gear limit exceeded" message, or One more round that doesn't start a round after a few clicks | Runs the **storage-full routine**: Prepare → Forge → filter to gear at or below the smelt rating (see [Settings](#settings)) → Select all → Smelt → confirm → back to Play → Start |
| Anything it doesn't recognise | Waits. If that goes on for a while, it saves a screenshot to `debug\` |

Other things it handles:
- **Second monitor.** If you click away from the game, it skips its presses and clicks until you come back, and never steals focus. It only brings the game back itself after a while with no mouse or keyboard input.
- **Retries.** A button that's still showing a few seconds after being clicked gets clicked again.
- **Dimmed buttons.** A greyed-out button (behind a translucent layer) is never clicked.
- **Failed routine.** If nothing is recognised soon after the storage-full routine, the bot stops and saves a screenshot.

## Download and run

1. Download `BloodHuntAFK-<version>.zip` from the [Releases](../../releases) page and unzip it to a folder of your own (not Program Files: the bot writes its log and screenshots next to itself).
2. Start **`BloodHuntAFK.exe`**. It asks for administrator rights, because the game ignores input from programs with lower rights.
   - Windows may say "Windows protected your PC", because the exe isn't signed: **More info → Run anyway**. Some antivirus programs flag it too, since a packed program that reads the screen and sends input looks like what they look for. The source is all here, and you can [build the exe yourself](#building-the-exe) or [run it from source](#running-from-source).
3. Put the game in **Borderless / Windowed Fullscreen**, on any monitor. The bot finds the game window and follows it, so you can keep using your other monitor.
4. **Play solo:** in Blood Hunt, untick **AUTO-FILL TEAMMATES**. It lowers the risk of a ban, and the bot never affects other players.
5. On the **Settings** tab, set the ability's duration and cooldown, and the heal timings, for your gear. Check the smelt rating: everything unlocked at or below it gets destroyed when storage is full.
6. **Key test**, then switch to the game in a match within 5 s: the ability should fire.
7. **Start**, then switch to the game. **F8** pauses and resumes, **F10** stops (from any window; you can change both).

The included profile, `profiles\16x9\`, works on any **16:9** screen (1920x1080, 2560x1440, 1280x720, …). For other shapes, see [Other screen sizes](#other-screen-sizes).

## The window

- **Status:** the profile in use (and the size it's fitted to), whether the game window is found and in front, what the bot is doing, when the next F comes, and counts for the run.
- **Start / Pause / Stop.** Pause and Stop do the same as the hotkeys. Start saves your changes first. Nothing is pressed or clicked while another window is in front.
- **Key test** and **Check screen** (scores every image on the screen 5 s later and saves `debug\check.png`).
- **Setup tools:** snap, crop, routine record and routine check, each in its own console window (see [Other screen sizes](#other-screen-sizes)), and a link to the bot's folder.
- **Log:** everything the bot does. It's also written to `bot.log`.
- **Settings tab:** what every player sets: the ability and heal keys and timings, what happens when gear storage is full (smelt or not, the rating, the backup), how long to run, the hotkeys. Keys are set by clicking the field and pressing the key.
- **Advanced tab:** every other setting, under the same sections as in the file.

Point at a setting to see what it does. Fields lock while the bot runs; changes apply on the next Start.

All settings live in one file, **`settings.py`** (next to the exe; `bloodhunt\settings.py` from source). The window reads it and changes just the values in it, keeping the comments. You can also edit it in a text editor: the window reads it again when it changes, and a mistake is reported with its line number.

## Commands

The setup tools are commands, also usable on their own: `BloodHuntAFK-console.exe <command>` next to the exe, or `.venv\Scripts\python.exe BloodHuntAFK.py <command>` from source. Any command takes `--profile NAME`. With no command, both open the window.

| Command | What it does |
|---|---|
| `keytest` | After 5 s, presses F the way `run` does |
| `run` | The bot, without the window. **F8** = pause/resume, **F10** = quit |
| `snap` | F8 saves a screenshot to the profile's `shots\`. Makes a profile for your screen's shape if there isn't one, and lists the screens to capture |
| `crop` | Guided: goes through your screenshots, you say what's on each one and box it |
| `crop NAME [SHOT]` | Boxes one template by name, from a screenshot you pick |
| `check [SHOT]` | Scores every template against the screen (or a screenshot) and saves `debug\check.png` |
| `routine check` | Draws every routine click spot on its screenshot (`debug\routine_*.png`) |
| `routine run` | Runs the storage-full routine once, starting from the Victory/Defeat screen |
| `routine record` | You do the storage-full routine by hand; your clicks become its click spots |
| `help` | The usage text |

## Other screen sizes

Everything that depends on the screen lives in a profile, one per screen shape: `profiles\16x9\`, `profiles\16x10\`, and so on. The one for the game's screen is picked automatically.

### 16:9 screens (1280x720, 1600x900, 2560x1440, 3840x2160, …)

Nothing to set up. The game's menus scale with the screen, so on every 16:9 screen each button is in the same place relative to the screen, just bigger or smaller. `profiles\16x9\` was cropped at 1920x1080. On another 16:9 size, the bot resizes its images and moves its click spots to match each time it starts. Nothing is saved, so the profile stays the same for every size.

That includes the game set to **Fullscreen** at a lower 16:9 resolution than your desktop. The display switches to the game's resolution when the game comes to the front, and the bot follows the switch.

Resized images need a lower score to count as a match (`MATCH_THRESHOLD_SCALED`, on the Advanced tab), because the game draws text at whole font sizes, so a shrunk copy of a button never matches the real one exactly. `check` shows each image's score and the score it needs.

The resized images aren't exactly what the game draws at your size, so check them before leaving it overnight:

1. `snap`, and press F8 on a match, the Victory/Defeat screen and the One more round screen.
2. `check <screenshot>` on each of them (Setup tools, Score the images on a screenshot): the image for that screen should show `MATCH`.

The storage-full routine's clicks are scaled the same way. Watch the first time it runs (F10 stops the bot), or measure it on your screen with `routine record` (below).

If an image doesn't match at your size, make a profile cropped at exactly that size, which is then used instead of `16x9`. Run `snap --profile 1280x720` (with your size), then follow the steps below from `crop` on. It starts empty, so every image has to be cropped.

### Any other shape (16:10 laptops, ultrawide, …)

The game lays its menus out differently on a different shape, so it needs its own profile. Once it's made, it works for every size of that shape. The steps are in the window's **Setup tools** menu, in this order:

1. **`snap`.** It makes an empty profile named after your screen's shape (`16x10`, or the size itself for an ultrawide, like `3440x1440`), then lists the screens to capture. Press **F8** on each, then F10 to quit:
   - in a match (HUD showing)
   - the Victory/Defeat screen, with HOLD TO SKIP
   - the One more round screen
   - the gear-limit message after One more round. This only appears when your gear storage is full, so skip it until then.
2. **`crop`.** Use screenshots taken at the size the profile was started at. Each screenshot opens with a menu drawn on it. Press the number of what's on that screenshot, then drag a box around it. An example of what to box opens alongside, so you can see what's meant. **Enter** saves the box, **C** cancels it. One screenshot can hold several things (a match shows both LSHIFT and the portrait). **D** checks whether something already made matches this screenshot. **N** goes to the next screenshot, **Q** quits.
3. **`routine record`.** It lists the clicks of the storage-full routine and where to type and press SPACE, then records your clicks while you do the routine by hand:
   - Start on the **VICTORY / DEFEAT screen with PREPARE showing**. The routine ends with START, which from anywhere else could start a different mode.
   - Have at least one **Legendary item at or below the smelt rating** in your storage, so the smelt warning popup appears: its CONFIRM is one of the clicks.
   - Make exactly those clicks, in order, and no others. Each one beeps. **F9** undoes the last one, **F10** cancels.
   - When you click START, a round should start. If it doesn't, a click was missed or extra: record again.

   It also saves the screen at each click, so `routine check` shows its crosses on your own screen.

Until the routine is recorded, the bot farms normally, but full gear storage isn't handled: One more round just keeps being clicked. The window says so under "When gear storage is full".

The gear-limit message and the One more round button are matched as text, so a game set to another language needs its own crops of both.

## Profiles

- `profiles\<name>\templates\`: cropped images. The file-name prefix says what the bot does when it sees one:
  - `click_*`: click it.
  - `ingame*`: we're in a match.
  - `stop_*`: stop the bot.
  - `routine_<name>*`: run that routine.

  Each has a `.json` beside it recording where it was cropped, so it's only looked for around that spot.
- `profile.json`: the screen size it was cropped at (its click spots are in that size's pixels), buttons clicked at a fixed spot, and the routine steps. A step is `"click": [x, y]`, `"key": "space"` or `"type": "..."`, plus how long to wait after it and a `"hint"` saying what to click (shown by `routine record`). In `"type"`, `{SMELT_RATING}` (any setting's name in braces) is typed as that setting's value, so every profile smelts at the same rating.
- `shots\` (screenshots from `snap`) and `routines\` (the screen at each routine step) aren't committed: they show your in-game UID.

## Settings

Timings and keys are in the window, and in `settings.py`, each with a comment explaining it: rune duration and cooldown, heal timing, keys and hotkeys, scan rate, match thresholds, retry and focus timings, whether to smelt when storage is full and at what rating, and a run-time limit.

**The smelt rating** (`SMELT_RATING`, on the window's Settings tab) is **5600** as shipped, so the storage-full routine smelts all unlocked gear rated 5600 or below, Legendary included. Lock any gear you want to keep.

## Running from source

1. Install **Python 3** from python.org (tick "Add python.exe to PATH").
2. In this folder:
   ```powershell
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
3. Run the terminal **as administrator**, then `.venv\Scripts\python.exe BloodHuntAFK.py` opens the window. Settings are in `bloodhunt\settings.py`.

## Building the exe

`build.ps1` builds the release with PyInstaller: `dist\BloodHuntAFK\` (the two exes, `settings.py`, this README and each profile's `profile.json` and `templates\`) and `dist\BloodHuntAFK-<version>.zip`. Screenshots, `routines\`, `debug\` and `bot.log` are never copied in.

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

It installs the requirements and PyInstaller into `.venv` first. `-NoAdmin` makes a test build whose exes don't ask for administrator rights.

**Releases** are built on GitHub: pushing a version tag (`git tag v1.0`, then `git push origin v1.0`) runs the same script in GitHub Actions (`.github\workflows\release.yml`) on a clean checkout and attaches the zip to a **draft** release. Download it, test it, then press Publish.

## Code layout

```
BloodHuntAFK.py        entry point and usage text
bloodhunt/
  gui.py               the window
  bot.py               the main loop
  routines.py          running and drawing routines
  guide.py             guided setup: the guided crop and routine record
  vision.py            screen capture and template matching
  profiles.py          picking profiles, and fitting them to your screen size
  inputs.py            key presses, clicks, typing
  winapi.py            window focus, hotkeys, key names, mouse, idle time
  commands.py          the command-line commands
  settings.py          settings
  settings_file.py     reading settings.py without running it, and changing a value in place
  common.py            paths, logging and file helpers
BloodHuntAFK.spec      PyInstaller build (two exes, one folder)
build.ps1              builds the release zip
.github/workflows/     the release build on GitHub
```

`BOT_NOTES.md` explains the loop step by step and the reasons behind each behaviour. `CLAUDE.md` is the project memory used with Claude Code.
