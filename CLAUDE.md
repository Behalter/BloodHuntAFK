# Blood Hunt AFK bot: project memory

This file hands the project over from a claude.ai chat to Claude Code. Read it fully before changing anything, then read `BOT_NOTES.md` for how the current code works.

## What this is

`BloodHuntAFK.py` is a Windows Python script that farms gear overnight in Marvel Rivals' **Blood Hunt** PvE mode. The user plays solo as a Thor build that clears runs as long as **F (Awakening Rune)** is pressed on a timer. The script watches the screen with OpenCV template matching. It presses F during matches and clicks through the end-of-match screens, looping indefinitely.

**The local files are the source of truth.** The user edits them directly, so values here can be out of date: read the actual code before relying on a number. The user is tuning the F timing to find the minimum: `F_DURATION` 60 + `F_COOLDOWN` 9 = F every 69 s, in `bloodhunt/settings.py`.

Files in the project folder: `BloodHuntAFK.py` (entry point and usage text), `bloodhunt/` (the code, split into modules; settings in `bloodhunt/settings.py`), `profiles/<name>/` (per resolution: `profile.json`, `templates/` with `NAME.png` + `NAME.json`, `shots/`), `BOT_NOTES.md` (architecture and settings reference, written for agents), `CLAUDE.md` (this file), `debug/`, `bot.log`, `.venv/`.

`BOT_NOTES.md` describes the code as it is now. Update it whenever the code changes, and update this file's pending-work list as items get done.

## How the user works

- The user understands the game flow very well and plans steps carefully. Their game-flow descriptions have been accurate every time; the storage-full popup was the first thing missed. **Treat the steps they give as correct and final.** Don't second-guess the sequence, and don't add confirmation questions about it.
- When asked, they want the whole plan laid out start to finish before building, so they can catch everything in one pass and not redo setup (screenshots, crops) repeatedly.
- Once they say to build: build without stopping to confirm, and only stop if something is genuinely unclear or doesn't add up.
- They test on the real game and report back precisely. Respond to what they report.
- They want explanations of *why* something behaves as it does, not just a fix.

## Game facts (from the user)

- Blood Hunt, solo, Auto-Fill Teammates off. Game in borderless fullscreen at **1920x1080** on the primary monitor.
- **F = Awakening Rune.** It lasts about **60 s**, then about **9 s** of cooldown before it can be pressed again. The user is still tuning these numbers.
- **X = heal.** It doesn't change anything on screen that would interfere with detection. The HUD shows a charge count above the X icon.
- Each match starts with a **prep phase of ~15 s**. Abilities already work during it, and Thor can't die for the first ~10 s.
- The game moves the mouse to the **centre of the screen** after each match.
- Matches have a 1-hour cap, so a stalled run ends on its own.
- The user has their valuable gear **locked** in game.

## The in-game loop (current, working)

| # | Screen | Bot recognises | Bot does |
|---|---|---|---|
| 1 | Prep (~15 s), then the match | `ingame_lshift` (the LSHIFT key label) / `ingame_portrait` (Thor's face), each locked to its HUD spot | F 1.5 s after the HUD is first seen (`FIRST_PRESS_DELAY`; the user lowered it from 10 on 2026-11-21, since healing in each cooldown means Thor can't die, so the exact F timing no longer matters), then every 69 s (each F is sent **3 times over 0.55 s**, `ABILITY_PRESSES`/`ABILITY_SPAN`: a single F sometimes didn't fire, and the user tested that the later presses don't cancel it); X every 2 s through each cooldown, 62–68 s after each F (`HEAL_EVERY`; two heals at 63/66 s weren't enough, user 2026-11-21) |
| 2 | MVP animation | nothing | wait |
| 3 | Victory **or** Defeat screen. Bottom right: `SPACE NEXT` and `SPACE HOLD TO SKIP` | `click_skip` (a SPACE box) | Click at the fixed spot **(1735, 1047)**, the SPACE box next to HOLD TO SKIP, then mouse back to the centre. Retried every 5 s while it's still there. Matching hits both SPACE boxes (the NEXT one scores 0.895), so the spot is fixed in the profile's `click_at` |
| 4 | "One more round" | `click_one_more_round` | click, mouse back to the centre; retried every 5 s while it's still there |
| 5 | The same button again, **dimmed** behind a translucent layer, just before character select | that button at low contrast | nothing: the contrast check skips dimmed buttons. Clicking it would be harmless anyway (the user confirmed) |
| 6 | Character select. Thor's portrait may appear here too | nothing (the portrait template is locked to its HUD spot) | nothing: the game auto-picks Thor |
| 7 | Back to 1 | | |
| – | Storage full: after "One more round", the screen stays and a message shows **briefly** | `routine_storage_full` (the message text, cropped by the user 2026-11-21; scores 1.00 on it, ≤0.19 elsewhere) | looks 1.5 s after the One more round click; runs the `storage_full` routine (below) |

Dying leads to the Defeat screen, which has the same buttons in the same places, so failed runs loop the same way.

**The user has run this setup on the real game at 1080p and it works.** That confirms simulated input is accepted, and the window title/class and the templates are correct.

## Decisions so far, and why

- **Screen reading, not recorded macros:** round length and load times vary.
- **Location lock (`NAME.json`, `SEARCH_MARGIN` = 80 px):** Thor's portrait also appears on character select. Locking each template to where it was cropped stops false matches.
- **Contrast check:** "One more round" comes back dimmed before character select. `TM_CCOEFF_NORMED` ignores brightness, so a dimmed button still scores ~1.0, which is why contrast is checked separately and dimmed buttons are skipped.
- **5 s retry for every button, 1.5 s settle after focus returns** (done 2026-11-21, see "Done" below).
- **`crop` snaps boxes to even pixels:** matching runs at half scale, and odd offsets cost ~0.12 of score.
- **Second monitor:** the user works on another monitor while the bot runs.
  - When the game isn't the front window, the bot **never steals focus**. It skips presses and clicks and **queues nothing**: each scan acts only on the current screen. The only carried-over state is the F timer, and it only acts when the current screen is a match.
  - The bot brings the game back itself only after `IDLE_BEFORE_REFOCUS` (120 s) with no mouse or keyboard input, which covers something stealing focus overnight.
- **Stuck screenshots** every 10 min, at most 6 in a row.
- The user fixed monitor selection themselves: `Screen` captures the monitor at (0,0), the primary, because mss doesn't reliably list it first. Keep that.

## Pending work

### Future, agreed with the user

- **3-click backup trigger** (user: "good, add as a future plan", 2026-11-21): if "One more round" is still there after 3 clicks, run the storage-full routine, in case the message is missed or the template doesn't match. Its first click (Prepare) is right next to that button, so it's a safe place to start. Worst case of a false trigger: gear rated 5600 or below is smelted early. (Storage filling overnight on 2026-11-21, before the trigger was cropped, cost ~7 h of One more round retries.)
- **Image check before each routine step** (deferred by the user, 2026-11-21): before each click, check the spot against a small image, waiting a few seconds for slow menus, and abort if it never matches. Notes from the user: for the Play now step, check the **PREPARE** button, not PLAY NOW, because PLAY NOW has a lightning animation. Crop these images from `snap` screenshots, not from the step screenshots in `profiles/1080p/routines/` (they come from a different capture path and score only ~0.84).
- A "record mode" (the user does the routine once by hand and the script records it) was suggested earlier but not chosen.

## Storage-full routine: the user's decisions (built 2026-11-21)

Steps and waits as the user gave them:

| # | Screen | Action | Wait after |
|---|---|---|---|
| 1 | Victory/Defeat | click PREPARE | 7 s |
| 2 | Hero tab | click FORGE tab | 2 s |
| 3 | Forge (Scrap) | click FILTER | 2 s |
| 4–6 | Gear Filter | click the SHOW RATING number box (1177, 537; clicking selects the old value), type **5600** (a `"type"` step), click CONFIRM | 0.5 s each |
| 7 | Forge, filtered | click SELECT ALL | 0.5 s |
| 8 | Forge, selected | click SMELT | 3.5 s |
| 9 | "Smelt Gear: currently contains Legendary quality gear" popup | click CONFIRM (794, 829). Added as a step instead of ticking "Don't show again today" (the user, 2026-11-21) | 5 s |
| 10 | "Acquired" rewards | press SPACE | 0.5 s |
| 11 | Forge, after smelting | click OVERVIEW tab | 1.5 s |
| 12 | Overview | click PLAY NOW (it closes that UI) | 3 s |
| 13 | Play screen | click START | then the main loop |

- Originally steps 4–7 ticked NORMAL, ADVANCED, RARE, EPIC (never LEGENDARY). The user ran that version on the real game on 2026-11-21: it works. The same day they switched to the rating filter (5600 or below), to smelt bad Legendary gear too; that brings up the Legendary warning popup (step 9). Its CONFIRM spot is empty background when the popup doesn't show. The `type` step types one character per key press; `TYPE_GAP` (0) adds a pause between characters. The user ran the rating version on the real game (with the Legendary popup showing): it works. Not yet seen without the popup. The value was 5950 for the user; lowered to 5600 before publishing on GitHub so the default only smelts gear that is bad for anyone.
- The filter doesn't remember settings between visits.
- The message after One more round shows **briefly**, so that button gets a 1.5 s after-click wait instead of 4 s (the user: pressing it twice is harmless).
- After the routine, something must be recognised within **1 minute**, or the bot stops with a screenshot (confirmed by the user).
- The routine waits for the game to be in front before each step (+ `FOCUS_SETTLE`), and never skips a step.
- If the message appears again before a match has started (smelting freed nothing), stop instead of looping.
- Smelting is permanent; the user's valuable gear is locked.

## Done (2026-11-21, in Claude Code)

- **Item 1, the skip click after tabbing back in:** the click was sent the instant the game came back in front, and the game swallowed it. The old 45 s disarm then stopped any retry. Now: `FOCUS_SETTLE` (1.5 s) wait before any input after the game is back in front (you clicked in, or `ensure_focus` brought it back). Every button is retried after `REPEAT_CLICK_AFTER` (5 s), with the contrast check kept. After `NO_EFFECT_AFTER` (3) clicks without the button leaving the screen, one `debug/noeffect_*` screenshot, and retries continue.
- **Item 2, F timing split and X heals:** `F_DURATION` 60 + `F_COOLDOWN` 9; X during each cooldown (first two at 63/66 s; changed later the same day to every 2 s, `HEAL_EVERY`), timed from the actual F press. Same rules as F. When several presses are overdue, only the latest is pressed and the rest are dropped. Also fixed: while a press was overdue (HUD hidden, game not in front), the old loop re-scanned every 0.05 s. It now scans at the normal rate.
- **Item 4, profiles:** `profiles/<name>/` with `profile.json` (screen size, `click_at`), `templates/`, `shots/`. Auto-selected by main-screen size, or `--profile NAME`; `snap --profile NEWNAME` creates one. The old `templates/` and `shots/` were moved into `profiles/1080p/`. `check` scores were identical before and after.
- **Item 5, split into files:** the `bloodhunt/` package (see `BOT_NOTES.md` for the module list). `BloodHuntAFK.py` is now just the entry point.
- **Item 3, storage-full routine** (run on the real game by the user: works; trigger cropped from the real message): steps in `profiles/1080p/profile.json`, measured on the user's screenshots in `profiles/1080p/routines/storage_full/`. `routine_*` templates trigger routines; there are `routine check` / `routine run` commands; One more round waits 1.5 s after a click. The `noeffect` screenshot is now taken of the screen after the click (so it captures the brief message). There's a 60 s recovery check, and the bot stops if the message repeats before a match. Tested in the simulation.
- **F sent 3 times over 0.55 s** (`ABILITY_PRESSES`, `ABILITY_SPAN`): a single F sometimes didn't fire.
- **Routine `type` step** and the rating filter (see the routine table).

## Testing

- Loop logic is tested in a **simulation**: fake clock, Windows focus/input calls stubbed, a scripted fake game built from the user's real screenshots. `BOT_NOTES.md` lists what it covers and how to patch the modules. Claude Code can also run `check` against the user's real screenshots in `profiles/1080p/shots/`.
- **Never drive the actual game from Claude Code.** The user runs `run` themselves.

## Context and boundaries

Marvel Rivals' prohibited-software list names AutoHotkey under "Emulation Scripts", and also lists hardware macros and devices like Kmbox. The user knows this and accepts the risk to their own account; they play solo, so no one else is affected. The script uses ordinary `SendInput`. **Don't add anything meant to hide from or get around anti-cheat** (driver-level input, hardware HID emulation, process hiding). It's on the same list and out of scope.
