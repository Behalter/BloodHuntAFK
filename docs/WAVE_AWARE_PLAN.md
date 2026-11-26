# Wave-aware Thor Rune controller — implementation plan

Status: design only. No live gameplay behavior changed.

## Baseline
- Source fork: `decea1st/BloodHuntAFK`, preserved on `main`.
- Development branch: `feature/wave-aware-rune`.
- Current match loop: `bloodhunt/bot.py`, class `Presses`; schedules `F` for `FIRST_PRESS_DELAY` after recognizing an `ingame*` template and then every `F_DURATION + F_COOLDOWN`.
- Input delivery: `bloodhunt/inputs.py`; configured `ABILITY_PRESSES = 3` sends multiple `F` taps.
- Vision: `bloodhunt/vision.py` uses image template matching and per-resolution profiles, with existing match HUD templates but no preparation countdown or active-Rune template.
- Existing `click_skip` and `click_one_more_round` templates already provide a foundation for post-match navigation.
- `RUN_ROUTINES = True` and storage-full smelting can destroy gear (including Legendary items) at or below the configured rating. Disable that routine for all exploratory testing.

## Proposed state machine (detection first, monitor-only)
- `UNKNOWN`: ambiguous frame; log and do nothing.
- `IN_MATCH`: HUD recognized; Rune state is independently `ACTIVE`, `INACTIVE`, or `UNKNOWN`.
- `PREPARATION`: 'Vampires Incoming' countdown/banner recognized for consecutive scans.
- `COMBAT`: preparation has ended and combat HUD is positively confirmed, not just 'banner missing'.
- `POST_MATCH`: victory/MVP/menu templates recognized.

Transition rules, to validate against user footage:
1. Confirm initial combat: propose one Rune activation only if visibly inactive and ready.
2. Confirm preparation: propose one cancellation only if Rune is visibly active and cancellation is available.
3. Confirm fresh combat after preparation: propose one activation only if visibly inactive and ready.
4. Unusually long combat: propose a fallback activation only after confirming Rune has expired or is inactive, and its cooldown is ready; never press `F` based on elapsed time alone if state is unknown.
5. Post-match: stop proposing combat actions immediately; leave the existing skip/replay logic untouched in the first implementation.

## Important uncertainty
Do **not** assume canceling Awakening Rune resets its duration or bypasses cooldown. Validate the actual in-game behavior during a preparation interval. If cancellation starts a cooldown, adapt the plan to that mechanic.

## Safety & test controls
- Default to read-only/monitor-only: screen capture and event log, no key presses or clicks.
- Use hysteresis (multiple consistent scans), transition IDs, and one-shot events to prevent repeated key presses from a persistent UI marker.
- Require a positively recognized, ready Rune state before generating a prospective activation/cancellation event.
- Keep the existing timed controller available behind an explicit setting during development; do not modify the default live control path until offline tests pass.
- Disable gear-smelting for trial runs; gear-full detection should alert/stop rather than auto-smelt.
- Prefer stop-on-unknown and manual review to automatic retries on ambiguous screens.
- Never implement anti-cheat evasion. Game automation can breach NetEase's rules and risks account sanctions.

## Capture/calibration needed
- 1080p or native-resolution screenshots/video of: Rune visibly active and inactive; 'Vampires Incoming' around 15s; the 0.0s/countdown end; immediate combat restart; end-of-run MVP and results; one-more-round button and Thor selection when applicable.
- Crop new markers and add per-profile template metadata; do not commit whole screenshots containing player identifiers.
- Evaluate detection on recorded frames first and log expected actions without performing them.

## Tests to add
- Preparation detected across multiple frames -> one cancellation recommendation.
- Preparation banner remains visible -> no repeated recommendation.
- Banner disappears without a confirmed combat HUD -> no activation.
- Combat confirmed, Rune inactive and ready -> one activation recommendation.
- Rune state unknown -> no input recommendation.
- Long combat and inactive but cooldown unavailable -> no activation.
- Final results/MVP -> no further combat recommendation.
- Lost focus / pause / stop -> no action.
- 16:9 and 16:10 profile matching and resolution scaling.

## Files likely to change later
- `bloodhunt/vision.py`: read-only preparation and Rune-state detectors.
- `profiles/*/templates/`: calibrated markers and crop locations.
- New isolated wave-state module: pure state transitions and proposed actions.
- `bloodhunt/bot.py`: integrate when tested; retain legacy timed mode as fallback.
- `bloodhunt/settings.py` / `bloodhunt/gui.py`: opt-in strategy and monitoring controls.
- `tests/`: synthetic-sequence and recorded-frame regressions.

No live gameplay inputs should be sent during development until the logic and the user's account-risk decision have been considered.


## Shadow-monitor integration checkpoint (November 26, 2026)

**Implemented on the development branch only.** The original `main`
branch, `bloodhunt/bot.py`, `bloodhunt/inputs.py`, gameplay hotkeys and
automation timing are unchanged. The new files are:

- `scripts/shadow_monitor.py` — pure adapter that accepts a timestamp,
  a BGR frame, and the existing detector calibration. Feeds `WaveAdvisor`
  and produces typed samples/events with the same CSV columns as the offline
  MP4 analysis. There are no input API calls.
- `scripts/monitor_game.py` — optional Windows command to sample the existing
  `bloodhunt.vision.Screen` camera in the foreground Marvel Rivals window,
  load reference markers from the second recording, and write CSVs.
- `tests/test_shadow_monitor.py` — three synthetic, game-free regression
  tests for debounce, one-shot recommendations, CSV compatibility and invalid
  timestamps.

**Safety characteristics:** Ctrl+C to stop, foreground-only observations,
no re-focusing the window, no clicks/presses, no automatic smelting, and no
alteration of any in-game settings. No automation should be inferred from
the suggestion events: they are logged, never executed.

### Windows instructions

First download the development-branch ZIP afresh (or synchronize Git). The
new `scripts` and `tests` files must actually exist locally. The existing
Python 3.15 virtual environment may be reused; do not need to reinstall
dependencies if they are already installed.

1. Run all tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

After the previous 22 tests and three new tests, the expected count is 25,
but the newly added test suite has **not yet been confirmed on Windows**.

2. With Marvel Rivals already open, run the monitor in another PowerShell
window from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\monitor_game.py --reference-video "C:\Users\succe\Videos\clip_1,795,706,443,940.mp4" --output shadow_results
```

Default reference markers correspond to that second Ratatoskr recording.
Run the game manually and keep it foregrounded for observation. Stop the
monitor with Ctrl+C. It writes `shadow_results\timeline.csv` and
`shadow_results\events.csv`. If calibration raises an error, it
does not start the monitor; capture/reference times must be checked.

3. Inspect the event log for phase transitions and Rune recommendations
against manual gameplay. Compare to offline CSV findings. Be aware that
recognition is based on 1920x1080 calibrated crops and accepts only
16:9 game pictures. Different resolutions, borderless window sizes, UI
layouts or performance may need further calibration and testing.

**Do not use the original `BloodHuntAFK.py` launch command for this
test.** That starts the existing input-sending bot, which can trigger
smelting if routines are enabled. The shadow monitor does not execute
that code.

### Open integration questions

- The monitor has not yet been validated on a real desktop capture stream,
  only on recorded clips / state-machine tests.
- The current `vision.Screen` capture method must be validated against
  real game display scaling, focus and scan cadence.
- There is no live-input integration, and it is intentionally not the
  next test. Establish an accurate shadow log first.
- Gameplay automation may violate Marvel Rivals' terms and expose the
  account to sanctions, regardless of whether controls can be simulated.
