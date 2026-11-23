# Blood Hunt AFK bot: project memory

This file hands the project over from a claude.ai chat to Claude Code. Read it fully before changing anything, then read `BOT_NOTES.md` for how the current code works.

## What this is

`BloodHuntAFK.py` is a Windows Python script that farms gear overnight in Marvel Rivals' **Blood Hunt** PvE mode. The user plays solo as a Thor build that clears runs as long as **F (Awakening Rune)** is pressed on a timer. The script watches the screen with OpenCV template matching. It presses F during matches and clicks through the end-of-match screens, looping indefinitely.

**The local files are the source of truth.** The user edits them directly, especially the timings in `bloodhunt/settings.py`, which change with their gear.

Files in the project folder: `BloodHuntAFK.py` (entry point and usage text; no command opens the window), `bloodhunt/` (the code, split into modules; settings in `bloodhunt/settings.py`, the window in `bloodhunt/gui.py`), `profiles/<shape>/` (one per screen shape, e.g. `16x9`, fitted to any size of that shape: `profile.json`, `templates/` with `NAME.png` + `NAME.json`, `shots/`, `routines/`), `README.md` (for GitHub readers), `requirements.txt`, `requirements-build.txt`, `BloodHuntAFK.spec` + `build.ps1` (the exe build), `.github/workflows/release.yml` (release builds on GitHub), `.gitignore`, `BOT_NOTES.md` (architecture reference, written for agents), `CLAUDE.md` (this file), `debug/`, `bot.log`, `.venv/`, `build/` + `dist/` (build output).

The project is on GitHub (public), pushed by the user. `shots/`, `routines/`, `debug/`, `bot.log`, `build/` and `dist/` are git-ignored: screenshots show the user's in-game UID. The user commits and pushes themselves.

`BOT_NOTES.md` describes the code as it is now. Update it whenever the code changes, and update this file's pending-work list as items get done.

**Docs name settings, they don't copy values** (the user, 2026-11-22: the copies were bookkeeping that kept going stale). In these notes, `BOT_NOTES.md`, the README and the usage text, refer to a setting by its name (`F_COOLDOWN`) and say what it does and why; its value lives only in `settings.py`, with its comment. The same goes for profile data (click spots, waits): it lives in `profile.json`. Numbers in the docs are only facts the code doesn't hold: measured scores, test results, screenshot quirks, and past values where they explain a decision. One exception: the README states the shipped smelt rating once, next to how to change it, because it decides what gets destroyed.

## How the user works

- The user understands the game flow very well and plans steps carefully. Their game-flow descriptions have been accurate every time; the storage-full popup was the first thing missed. **Treat the steps they give as correct and final.** Don't second-guess the sequence, and don't add confirmation questions about it.
- When asked, they want the whole plan laid out start to finish before building, so they can catch everything in one pass and not redo setup (screenshots, crops) repeatedly.
- Once they say to build: build without stopping to confirm, and only stop if something is genuinely unclear or doesn't add up.
- They test on the real game and report back precisely. Respond to what they report.
- They want explanations of *why* something behaves as it does, not just a fix.
- They tune timings in `settings.py` themselves.

## Game facts (from the user)

- Blood Hunt, solo, Auto-Fill Teammates off. Game at **1920x1080** normally. Since 2026-11-22 the user runs it on their **second monitor** (to the right of the main one) to keep using the main one, and tests 720p there.
- The PC is a laptop with an external monitor, extended. The laptop's own screen is **16:10, 2560x1600**, which is how the user tests the 16:10 setup (2026-11-23).
- **F = Awakening Rune.** It lasts a while, then has a cooldown before it can be pressed again. Both depend on gear (`F_DURATION`, `F_COOLDOWN`).
- **X = heal.** It doesn't change anything on screen that would interfere with detection. The HUD shows a charge count above the X icon.
- Each match starts with a **prep phase of ~15 s**. Abilities already work during it, and Thor can't die for the first ~10 s.
- The game moves the mouse to the **centre of the screen** after each match.
- Matches have a 1-hour cap, so a stalled run ends on its own.
- The user has their valuable gear **locked** in game.

## The in-game loop (current, working)

| # | Screen | Bot recognises | Bot does |
|---|---|---|---|
| 1 | Prep (~15 s), then the match | `ingame_lshift` (the LSHIFT key label) / `ingame_portrait` (Thor's face), each locked to its HUD spot | F `FIRST_PRESS_DELAY` after the HUD is first seen (the user lowered it from 10 s on 2026-11-21: healing in each cooldown means Thor can't die, so the exact F timing no longer matters), then every `F_DURATION` + `F_COOLDOWN`. Each F is sent `ABILITY_PRESSES` times over `ABILITY_SPAN`: a single F sometimes didn't fire, and the user tested that the later presses don't cancel it. X through each cooldown: from `HEAL_DELAY_POST_F` into it, every `HEAL_EVERY`, until the next F (two heals per cooldown weren't enough, user 2026-11-21; the user added the delay on 2026-11-22) |
| 2 | MVP animation | nothing | wait |
| 3 | Victory **or** Defeat screen. Bottom right: `SPACE NEXT` and `SPACE HOLD TO SKIP` | `click_skip` (a SPACE box) | Click the SPACE box next to HOLD TO SKIP, at the profile's fixed `click_at` spot, then mouse back to the centre. Retried after `REPEAT_CLICK_AFTER` while it's still there. Matching hits both SPACE boxes (the NEXT one scores 0.895), which is why the spot is fixed |
| 4 | "One more round" | `click_one_more_round` | click, mouse back to the centre; retried the same way |
| 5 | The same button again, **dimmed** behind a translucent layer, just before character select | that button at low contrast | nothing: the contrast check skips dimmed buttons. Clicking it would be harmless anyway (the user confirmed) |
| 6 | Character select. Thor's portrait may appear here too | nothing (the portrait template is locked to its HUD spot) | nothing: the game auto-picks Thor |
| 7 | Back to 1 | | |
| – | Storage full: after "One more round", the screen stays and a message shows **briefly** | `routine_storage_full` (the message text, cropped by the user 2026-11-21; scores 1.00 on it, ≤0.19 elsewhere) | looks again soon after the One more round click (`AFTER_CLICK_WAIT_FOR`); runs the `storage_full` routine (below). **Backup:** One more round still there after `BACKUP_ROUTINE_AFTER` clicks runs it too (the message can be missed, and at 720p it doesn't match) |

Dying leads to the Defeat screen, which has the same buttons in the same places, so failed runs loop the same way.

**The user has run this setup on the real game at 1920x1080 and it works.** That confirms simulated input is accepted, and the window title/class and the templates are correct.

## Decisions so far, and why

- **Screen reading, not recorded macros:** round length and load times vary.
- **Location lock (`NAME.json`, `SEARCH_MARGIN`):** Thor's portrait also appears on character select. Locking each template to where it was cropped stops false matches.
- **Contrast check:** "One more round" comes back dimmed before character select. `TM_CCOEFF_NORMED` ignores brightness, so a dimmed button still scores ~1.0, which is why contrast is checked separately and dimmed buttons are skipped.
- **Retry for every button, settle wait after focus returns** (done 2026-11-21, see "Done" below).
- **`crop` snaps boxes to even pixels:** matching runs at half scale, and odd offsets cost ~0.12 of score.
- **Second monitor:** the user works on another monitor while the bot runs.
  - When the game isn't the front window, the bot **never steals focus**. It skips presses and clicks and **queues nothing**: each scan acts only on the current screen. The only carried-over state is the F timer, and it only acts when the current screen is a match.
  - The bot brings the game back itself only after `IDLE_BEFORE_REFOCUS` with no mouse or keyboard input, which covers something stealing focus overnight.
- **Stuck screenshots** (`STUCK_AFTER`, at most `STUCK_SHOTS_MAX` in a row).
- **The game can be on any monitor** (the user asked, 2026-11-22, to put it on their second monitor). `Screen` captures the inside of the game window wherever it is, and clicks use a mouse move that reaches every monitor (`inputs.move_to`, the same `SendInput` move as pydirectinput with `MOUSEEVENTF_VIRTUALDESK`). The fallback, while the game window isn't found, is the main monitor at (0,0): the user's own earlier fix (mss doesn't reliably list it first). Keep that fallback.

## Pending work

### Setup for other screens: built 2026-11-21/22, not yet run on the real game

The user asked for this so other people can set the bot up on their own screens. Their decisions:

- **One profile per screen shape** (2026-11-22). The user noticed that at 720p on their 16:9 monitor everything is in the same relative place, and asked why profiles weren't per aspect ratio. Built: profiles are named after the shape (`16x9`, `16x10`; an unusual shape gets `WxH`), `profile.json`'s `screen` is the size it was cropped at, and on any other size of that shape the bot resizes the images and scales the click spots in memory each time it starts (`Profile.fit`). Nothing is written per size. This replaced the first version (2026-11-21), which wrote a scaled copy of the profile for each new size; a copy goes stale when the source is re-cropped. `1080p` → `1920x1080` → `16x9`. A profile cropped at exactly the screen's size is picked over the shape's one, for someone whose resized images score too low (`snap --profile WxH`). `crop` only takes screenshots at the profile's own size; `routine record` at another size converts the clicks to the profile's size.
- One guided `crop` command: it goes through every screenshot, the user picks what's on it from a menu and boxes it, with a "done already" check. Built with the menu drawn on the screenshot and keys pressed in its window, an example image from another profile shown alongside, and auto-recognition of templates already made.
- `routine record`: the user does the routine by hand, and only the clicks are recorded. It prints the exact steps and the click count first, says to start from the VICTORY/DEFEAT screen with PREPARE showing (otherwise START could launch Quick Match), and says a Legendary item at or under the rating is needed so the smelt popup shows (the user chose this over handling a missing popup in code). At the end: "a round should be starting now; if not, record again". Added by Claude and accepted: a beep per click, F9 undo, a screenshot per click (so `routine check` works on the user's screen).
- README: play solo with AUTO-FILL TEAMMATES unticked (fewer ban reports, and no effect on other players).

- **Exclusive fullscreen** (2026-11-22). The user tested 720p by setting the game itself to Fullscreen at 1280x720, not Windows (changing the Windows resolution is a hassle for them). One run started at 1280x720 and clicked the SPACE box at **0.92**: the first real-game score at 720p. The next ones read 1920x1080 in the terminal, so nothing was resized, and the game then ran at 1280x720 ("WARNING: the screen is 1280x720 but ... were cropped from a different-sized screenshot"). Fixed at the user's request: the bot follows the screen size while the game is in front (`Screen.refresh()`, re-fit in `bot.run`; see `BOT_NOTES.md`).

- **Lower threshold for resized images** (2026-11-22). With the re-fit working, One more round still wasn't clicked at 720p. The user snipped the real 720p Defeat screen: the resized button scored 0.79, under 0.80, because the game draws text at whole font sizes (details in `BOT_NOTES.md`, Image matching). The user chose `MATCH_THRESHOLD_SCALED` (0.70 "for now") over per-size override crops or a full 720p profile. Per-size overrides (crop just the failing image at that size, inside the shape profile) remain the fallback if a resolution draws text very differently.

- **Game on the second monitor** (2026-11-22, see Decisions). Read-only check on the real setup: the game's picture was found at desktop (1920, 141), 1280x720, and a frame grabbed there scored `ingame_portrait` 0.94 (in a match at 720p); `ingame_lshift` only 0.47 (small text), which doesn't matter while the portrait matches.

**Next, by the user:** `run` with the game on the second monitor at 1280x720 and watch a round or two: the clicks there (SPACE, One more round) are the first real test of `inputs.move_to`. Still unscored at 720p on the real game: the in-match images (`ingame_lshift`, `ingame_portrait`) and the storage-full message; a snip during a match lets Claude score them (crop the window's 1280x720 area: the snip includes the title bar). The log should say "the screen is now 1280x720 - using profile 16x9 (cropped at 1920x1080, scaled to 1280x720)" once the game is in front. If a screen stalls, live `check` while it's up gives the real score. The guided `crop` has since run on the real game (16:10, below); `routine record` hasn't.
- **16:10 on the real game** (2026-11-23): on the laptop's 2560x1600 screen the user ran `snap` and `crop`, which made `profiles/16x10/` (click_skip, One more round, LSHIFT, portrait; no message crop, empty `routines`). The game loop works with it. Still to do for 16x10, later (user): `routine record`, and the gear-limit message crop. Until then full storage isn't handled there: no routine means neither the message trigger nor the backup fires, and One more round is retried until stopped (the startup log and the window now say so).
- **Real 720p results** (2026-11-22, user snips of the game's 1280x720 area, plus one mss grab): the user reported the clicks on the second monitor work. One more round 0.79 (counts with `MATCH_THRESHOLD_SCALED`), SPACE 0.92, portrait 0.94, LSHIFT 0.47, **storage-full message 0.55** (text spaced ~4% wider and wrapped differently at 720p; details and everything tried in `BOT_NOTES.md`, Image matching). So the 3-click backup trigger was built (below, Done).
- **The user's idea, not adopted yet (2026-11-22):** replace the 2-line message crop with the first line's first few words, at 1080p, for every size (wrap-proof). Tested: it doesn't help at 720p by itself (0.57, the text is drawn wider, not just wrapped); with extra stretched matching "A player in your team" reaches 0.78, longer pieces less. Claude recommended keeping the full message (most distinctive; a false trigger smelts gear) and relying on the backup at other sizes. The user then snipped the same words at both sizes: 418 px at 1080p vs 288 px at 720p (279 expected), drifting ~9 px along the line, and agreed: the full message stays the trigger at its own size, and **the backup is the main storage-full detection at other resolutions** (user, 2026-11-22).

### GUI and exe: built 2026-11-23, not yet run by the user

The user asked for a simple GUI and an exe so other people can use the bot. Built as agreed below; details in `BOT_NOTES.md` (The settings file, The window, The exe). Tested with the bot and Windows stubbed (`gui_test`), in the simulation, and as a built exe (`check` on the user's screenshots gave the same scores; the window's self-test). Never run against the real game by Claude.

**First look by the user (2026-11-23):** the window's columns shifted while pointing at fields, and resizing lagged. Cause and fix in `BOT_NOTES.md` (The window, Layout rule). A bug/optimisation pass over the day's new code followed, covering:
- the smelt fields didn't un-grey after `routine record` until the screen size changed
- a BOM in `settings.py` made it unreadable
- saves rewrote the file even when nothing had changed
- a repeating window error was logged 5x a second
- closing during a key test/check did nothing
- the game window was looked up twice a second
- every field was re-checked for each field while the tabs were built

The remaining resize cost is Tk redrawing each widget (measured; see `BOT_NOTES.md`). Claude left it, since resizing is rare and the alternatives are fewer widgets or another toolkit.

**Next, by the user:** build with `build.ps1` (a build with the admin prompt is in `dist\` already), unzip to a fresh folder outside the project, start `BloodHuntAFK.exe`, Key test, then Start and a round or two. Then try the Setup tools menu once (it opens the commands in a console window). The GitHub workflow hasn't run yet: the first `v*` tag pushed is its first test.

Agreed with the user:
- **tkinter window.**
  - Status line: profile and size, game found/in front, state, next F, counts.
  - Start / Pause / Stop, sharing state with F8/F10. Start has no countdown.
  - Key test, Check screen, and Setup tools (snap, crop, routine record/check, opened in a console window).
  - Log box, errors shown in the window, a ban-risk line.
- **Every setting in the GUI** (the user: players have different cooldowns and keybinds), split as agreed:
  - **Main:** ability key/duration/cooldown/first press/presses per burst; heal key/first heal/interval; storage full on/off (greyed out without a recorded routine), smelt rating, backup click count; hours to run; the pause/quit/undo hotkeys. The on/off switch is a new setting, `RUN_ROUTINES`; with no routine in the profile, the window and the startup log say full storage isn't handled (this was the "no routine" log line Claude offered).
  - **Advanced, folded:** button timings, seeing, game window, routines, watchdogs.
  - **Not shown:** `MATCH_SCALE` (the crops are aligned to it). The `BACKUP_ROUTINES` mapping was hidden too, then removed (below).
  - Key fields work by click and press. Tooltips come from the comments in `settings.py`, and new settings appear under Advanced by themselves. Values are checked before saving. Fields lock while the bot runs; changes apply on Start.
- **Exe:** PyInstaller, one folder, zipped. `BloodHuntAFK.exe` (window) and `BloodHuntAFK-console.exe` (the commands), both asking for admin. The zip holds the profiles' `profile.json` + `templates/` only, never `shots/`, `routines/`, `debug/` or `bot.log`. Unsigned, so SmartScreen will warn. Nothing is done to get around antivirus.
- **Builds:** `build.ps1` for local tests, plus a GitHub Actions workflow that builds on a pushed version tag and attaches the zip to a **draft** release. The user tests it, then publishes.
- **Settings stay a single file** (the user, 2026-11-23: "settings.py so it's just a single file"): `settings.py` next to the exe, read as literals (never run) and changed in place by the window, comments kept. Each comment is the window's help text for that setting, so comments must read on their own (a few were reworded for that). Rejected: a `settings.json` overriding `settings.py` (a value in two places).
- **The backup is fixed to One more round** (the user, 2026-11-23): the `BACKUP_ROUTINES` button → routine table was removed. No other button can show the gear-limit message: every other way into the forge starts from a different click, and Start (only clicked at the routine's end) prompting it means the routine already failed, so starting again would fail too, and Prepare wouldn't be where expected. `BACKUP_ROUTINE_AFTER` stays.
- **The smelt rating is one setting, `SMELT_RATING`** (the user, 2026-11-23, after asking whether the typed rating was tied to the profile). It was the text of each profile's `type` step since 2026-11-21, not by choice but because the whole routine went into `profile.json`. Now the step types `{SMELT_RATING}` (any `{SETTING}` in a `type` step is filled in), so every profile smelts at the same rating, and the window shows it as an ordinary setting. A profile whose step still holds a number keeps typing that, and the window says the setting isn't used there.

### Future, agreed with the user

- **Image check before each routine step** (deferred by the user, 2026-11-21): before each click, check the spot against a small image, waiting a few seconds for slow menus, and abort if it never matches. Notes from the user: for the Play now step, check the **PREPARE** button, not PLAY NOW, because PLAY NOW has a lightning animation. Crop these images from `snap` screenshots, not from the step screenshots in `profiles/16x9/routines/` (they come from a different capture path and score only ~0.84).

## Storage-full routine: the user's decisions (built 2026-11-21)

The steps as the user gave them. Click spots and waits are in `profiles/16x9/profile.json`; the typed rating is `SMELT_RATING` in `settings.py` (since 2026-11-23; before, it was in the step).

| # | Screen | Action |
|---|---|---|
| 1 | Victory/Defeat | click PREPARE |
| 2 | Hero tab | click FORGE tab |
| 3 | Forge (Scrap) | click FILTER |
| 4–6 | Gear Filter | click the SHOW RATING number box (clicking selects the old value), type the rating (a `"type"` step), click CONFIRM |
| 7 | Forge, filtered | click SELECT ALL |
| 8 | Forge, selected | click SMELT |
| 9 | "Smelt Gear: currently contains Legendary quality gear" popup | click CONFIRM. Added as a step instead of ticking "Don't show again today" (the user, 2026-11-21) |
| 10 | "Acquired" rewards | press SPACE |
| 11 | Forge, after smelting | click OVERVIEW tab |
| 12 | Overview | click PLAY NOW (it closes that UI) |
| 13 | Play screen | click START, then the main loop |

- Originally steps 4–7 ticked NORMAL, ADVANCED, RARE, EPIC (never LEGENDARY). The user ran that version on the real game on 2026-11-21: it works. The same day they switched to the rating filter, to smelt bad Legendary gear too; that brings up the Legendary warning popup (step 9). Its CONFIRM spot is empty background when the popup doesn't show. The user ran the rating version on the real game (with the Legendary popup showing): it works. Not yet seen without the popup. The user's own rating was 5950; it was lowered to 5600 before publishing on GitHub so the default only smelts gear that is bad for anyone (that default is now `SMELT_RATING`'s).
- The filter doesn't remember settings between visits.
- The message after One more round shows **briefly**, so that button gets a shorter after-click wait (`AFTER_CLICK_WAIT_FOR`; the user: pressing it twice is harmless).
- After the routine, something must be recognised within `ROUTINE_RECOVER`, or the bot stops with a screenshot (confirmed by the user).
- The routine waits for the game to be in front before each step (+ `FOCUS_SETTLE`), and never skips a step.
- If the message appears again before a match has started (smelting freed nothing), stop instead of looping.
- Smelting is permanent; the user's valuable gear is locked.

## Done (2026-11-21/22, in Claude Code)

- **Item 1, the skip click after tabbing back in:** the click was sent the instant the game came back in front, and the game swallowed it. The old 45 s disarm then stopped any retry. Now: a `FOCUS_SETTLE` wait before any input after the game is back in front (you clicked in, or `ensure_focus` brought it back). Every button is retried after `REPEAT_CLICK_AFTER`, with the contrast check kept. After `NO_EFFECT_AFTER` clicks without the button leaving the screen, one `debug/noeffect_*` screenshot, and retries continue.
- **Item 2, F timing split and X heals:** `F_DURATION` + `F_COOLDOWN`; X during each cooldown (first a fixed two heals, then every `HEAL_EVERY`, later from `HEAL_DELAY_POST_F` in), timed from the actual F press. Same rules as F. When several presses are overdue, only the latest is pressed and the rest are dropped. Also fixed: while a press was overdue (HUD hidden, game not in front), the old loop re-scanned constantly. It now scans at the normal rate.
- **Item 4, profiles:** `profiles/<name>/` with `profile.json` (screen size, `click_at`), `templates/`, `shots/`. Auto-selected by main-screen size, or `--profile NAME`; `snap --profile NEWNAME` creates one. The old `templates/` and `shots/` were moved into `profiles/1080p/` (renamed `1920x1080` later the same day, then `16x9` on 2026-11-22). `check` scores were identical before and after.
- **Item 5, split into files:** the `bloodhunt/` package (see `BOT_NOTES.md` for the module list). `BloodHuntAFK.py` is now just the entry point.
- **Item 3, storage-full routine** (run on the real game by the user: works; trigger cropped from the real message): steps in `profiles/16x9/profile.json`, measured on the user's screenshots in `profiles/16x9/routines/storage_full/`. `routine_*` templates trigger routines; there are `routine check` / `routine run` commands; One more round has a shorter after-click wait. The `noeffect` screenshot is now taken of the screen after the click (so it captures the brief message). There's a recovery check (`ROUTINE_RECOVER`), and the bot stops if the message repeats before a match. Tested in the simulation.
- **F sent several times in a burst** (`ABILITY_PRESSES`, `ABILITY_SPAN`): a single F sometimes didn't fire.
- **Routine `type` step** and the rating filter (see the routine table).
- **Setup for other screens** (see Pending): one profile per screen shape, fitted to the screen size in memory; guided `crop`; `routine record`. Tested with stubs, in the simulation at 1280x720, and on resized screenshots only.
- **Docs name settings instead of copying their values** (2026-11-22, see the rule at the top).
- **3-click backup trigger** (agreed 2026-11-21 as a future plan, built 2026-11-22 when the message didn't match at 720p): if One more round is still there after `BACKUP_ROUTINE_AFTER` clicks, run the storage-full routine, in case the message is missed or its template doesn't match. Its first click (Prepare) is right next to that button, so it's a safe place to start. Worst case of a false trigger: gear at or below the routine's rating is smelted early (accepted). (Storage filling overnight on 2026-11-21, before the trigger was cropped, cost ~7 h of One more round retries.) Tested in the simulation; not yet on the real game.

## Testing

- Loop logic is tested in a **simulation**: fake clock, Windows focus/input calls stubbed, a scripted fake game built from the user's real screenshots. Its timing checks follow the settings, so they pass whatever the user tunes. `BOT_NOTES.md` lists what it covers and how to patch the modules. Claude Code can also run `check` against the user's real screenshots in `profiles/16x9/shots/` (or resized copies of them, to test fitting). A second test script covers profiles, fitting, the guided crop and `routine record` with Windows stubbed (see `BOT_NOTES.md`).
- The window is tested hidden, with the bot, Windows calls and message boxes stubbed (`gui_test`), and can be looked at without showing it on screen (rendered transparent and captured with `PrintWindow`; see `BOT_NOTES.md`, Testing). A built exe is checked with `BloodHuntAFK-console.exe check <shot>` (same scores as from source) and the window self-test (`BLOODHUNT_GUI_SELFTEST`). Test builds use `build.ps1 -NoAdmin`, so nothing prompts for admin on the user's screen.
- **Never drive the actual game from Claude Code.** The user runs `run` themselves.

## Context and boundaries

Marvel Rivals' prohibited-software list names AutoHotkey under "Emulation Scripts", and also lists hardware macros and devices like Kmbox. The user knows this and accepts the risk to their own account; they play solo, so no one else is affected. The script uses ordinary `SendInput`. **Don't add anything meant to hide from or get around anti-cheat** (driver-level input, hardware HID emulation, process hiding). It's on the same list and out of scope.
