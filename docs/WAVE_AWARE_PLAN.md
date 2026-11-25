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
