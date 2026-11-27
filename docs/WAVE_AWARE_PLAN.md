# Wave-aware Thor Rune controller — implementation plan

Status: read-only recognition and action preview validated for tested scenarios. No live gameplay behavior changed. Input delivery remains unimplemented.

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

- The first real desktop-capture shadow run completed successfully on November 26, 2026. The recordings and CSVs support phase/rune recognition; output-input integration remains untested.
- The current `vision.Screen` captured the user's 16:9 game window at approximately 2 samples/second in one live session. Other display scaling, focus changes and performance conditions are not yet validated.
- There is no live-input integration, and it is intentionally not the
  next test. Establish an accurate shadow log first.
- Gameplay automation may violate Marvel Rivals' terms and expose the
  account to sanctions, regardless of whether controls can be simulated.


## First read-only live shadow-monitor result — November 26, 2026

User ran the monitor on Windows with Python 3.15 and OpenCV 5.1.
All **25 unit tests passed** locally. The first live event and timeline CSVs
contained **420 observations**, from monitor elapsed **23.02s through 232.66s**;
some initial time was skipped while the game was not foregrounded. Monitoring
recorded no keyboard/mouse inputs.

Observed chronological phases:

- Preparations confirmed: 64.54s, 94.56s, 126.08s, 155.11s, 184.62s.
- Combats confirmed: 79.05s, 109.57s, 140.59s, 169.61s, 200.13s.
- Ending confirmed: 201.64s; victory/results: 227.15s.
- Four one-shot cancellation suggestions at 94.56s, 126.08s,
  155.11s and 184.62s. No unnecessary activation suggestion because
  the Rune HUD was already ACTIVE at the confirmed combat boundaries.
- Rune COOLDOWN -> READY: 97.57 -> 106.57 (9.0s),
  129.58 -> 136.09 (6.51s), 159.61 -> 165.61 (6.0s),
  189.63 -> 195.63 (6.0s).
- Rune readiness preceded next confirmed combat by 3.0, 4.5, 4.0 and
  4.5 seconds, respectively. These are **visual detection intervals**, not
  precise measurements of game ability cooldown or user keypress timings.
- Preparation signal 0.934–0.992; normal-combat Phase header ~0.953–0.969;
  boss objective 0.960–0.969 with >=180px health bar; ending ~0.982–0.986;
  victory ~0.962–0.963. Strong boss-objective matches also appeared during
  preparations, underscoring why the health-bar condition is mandatory.
- Post-ending cinematic frames were UNKNOWN and generated no new suggestions.

**Assessment:** Recorded behavior is consistent with all expected wave
transitions and manual Rune cancellations. The CSVs are detector-produced
evidence, not independent visual ground truth for every frame; do not claim
universal accuracy or live-control reliability from a single shadow session.

**Next development work** is a separately switchable controller behind an
explicit opt-in and a dry-run/monitor-only default. Preserve the original
timed mode. Critically, the existing `ABILITY_PRESSES=3` policy is unsuitable
as an assumed default for toggle-to-cancel actions: do not issue multiple F
presses without verifying state between them. Require foreground/focus,
consecutive confirmed observations, no actions after ending, and bounded
manual stop controls. Do not enable storage-full smelting. Gameplay
automation may violate game rules and risk account enforcement.

## Optional wave-aware action preview — November 26, 2026

An opt-in dry-run preview is implemented in the development branch. The
files `scripts/wave_action_preview.py` and `tests/test_wave_action_preview.py`
are new; `scripts/monitor_game.py` was updated with the
`--preview-actions` option. **Default remains read-only monitoring without
preview**; even with this option enabled, there are no key or mouse calls.
The original `bloodhunt/bot.py`, its fixed-timer `Presses` logic, and
input/routine modules are unchanged.

Preview logic:
- Begin only on a one-shot `WaveAdvisor` suggestion.
- Require two consecutive matching, positively classified Rune/phase
  observations before outputting a hypothetical single `F` tap.
- Never emit on an unknown Rune state, an uncertain/raw phase, after
  `MATCH_ENDING` or results, or after an observation gap larger than
  2.5 seconds without a new phase transition.
- One hypothetical tap per intent per confirmed phase. Do not convert
  this CSV directly to keypresses: real input requires independent
  post-input visual verification, focus checks, retries bounded by
  explicit safety rules, and a separate deliberate opt-in.
- `preview_actions.csv` lists the simulated intent. It is not evidence
  that the game would have accepted an input or that the user actually
  pressed a key.

### Run on Windows

Sync the two new files and updated `scripts/monitor_game.py` first.
Run all tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Verified Windows baseline: **36 tests passed** (25 existing + 11 preview tests).

Run with the optional preview enabled while manually playing:

```powershell
.\.venv\Scripts\python.exe scripts\monitor_game.py --reference-video "C:\Users\succe\Videos\clip_1,795,706,443,940.mp4" --preview-actions --output shadow_preview_results
```

After Ctrl+C, inspect three CSVs in `shadow_preview_results`:
`timeline.csv`, `events.csv`, and `preview_actions.csv`.
The original bot's `RUN_ROUTINES` / smelting behavior is not invoked by
this standalone monitor. Do not launch `BloodHuntAFK.py` for this test.


## Final live preview validation — November 26, 2026

**PASS for the tested read-only scenario.** User reported 36/36 local
unit tests passing in 0.164s after downloading preview implementation
commit `ac08827f13abf1b7508afd193231a79a9c18b906` and regression tests
commit `2549e5fa61ddb619fc5b027946768e69b6c5094a`.

The final uploaded CSVs were directly inspected: 780 timeline rows
(164.29–555.20s monitor elapsed), 35 event rows, 9 preview rows.
419 timeline rows preceded the first confirmed preparation. The match
itself had five confirmed preparations, five confirmed combat phases,
one ending and one results transition.

| Stage | Activation preview (s) | Following cancellation preview (s) |
|---|---:|---:|
| Wave 1 | 389.60 | 409.11 |
| Wave 2 | 424.12 | 440.63 |
| Wave 3 | 455.64 | 471.65 |
| Wave 4 | 486.66 | 501.17 |
| Boss | 516.68 | — |

Every preview coincided with phase confirmation and was supported by
two consecutive matching raw phase/Rune observations 0.50s apart.
No duplicate, pre-match, or post-ending previews were present.
All four cancellations had incoming score 0.990. Rune readiness
preceded the next confirmed combat by 3.00, 3.50, 1.50 and 3.00s.

The final boss had objective score 0.984 and 380px health-bar run
at activation preview. A single raw ACTIVE observation at 518.68s
was followed by raw MATCH_ENDING at 519.18s and confirmed ending at
519.68s; the two-frame Rune event did not fire. This is consistent
with the manual activation but is not independent input verification.
Results confirmed at 544.70s. No action preview followed the ending.

Limitations: detector-derived CSVs are not independent frame-level
ground truth; this is not a test of real input delivery, focus loss
during a pending action, long-wave live recovery, or arbitrary
resolutions. No actual input was sent. No additional live match is
required to close this read-only milestone.

Recommended next milestone: isolated, simulated action acknowledgement
and failure handling with a fake input sink, without sending gameplay
inputs. Keep the existing bot and smelting routines unchanged.


## Offline acknowledgement simulation — November 26, 2026

The isolated `scripts/simulate_acknowledgement.py` module and its
16 synthetic tests are committed. The user verified the cumulative
Windows suite: **52/52 passed in 0.294s**. Breakdown: 12 advisor,
10 video detector, 3 shadow monitor, 11 preview, 16 acknowledgement.
The simulation has no device calls, callbacks, or live monitor integration.
Defaults: two matching subsequent observations, 3s acknowledgement
timeout, 2.5s maximum gap, no retries. These are provisional fixture
parameters, not measured response times.

Reinspection of final timeline(5).csv (780 observations),
events(5).csv (35 events), and preview_actions(1).csv (9 previews)
found the following elapsed seconds from hypothetical preview to two
consecutive matching raw phase/Rune observations:

| Stage | Activation | Following cancellation |
|---|---:|---:|
| Wave 1 | 4.00 | 1.50 |
| Wave 2 | 4.01 | 2.50 |
| Wave 3 | 5.00 | 4.51 |
| Wave 4 | 5.50 | 7.50 |
| Boss | interrupted by raw ending | — |

The boss had one ACTIVE sample 2.00s after preview, followed by raw
ending 2.50s after preview. These are preview-to-observation intervals,
including unknown manual reaction delays. They do not measure input
delivery or game response latency and cannot validate a live timeout.
Retain the provisional synthetic timeout and no-retry policy. No
input integration or timing changes were made. Future offline work
may test complete synthetic match sequences and post-match recognition
without connecting the simulator to gameplay controls.


## Synthetic match lifecycle validation — November 26, 2026

The user ran the cumulative Windows unittest suite after downloading
`tests/test_match_lifecycle.py` at commit
`b13c4f93967f4ff7ca1b46f9a99bbcd7f0e6b6d4`.
**60/60 tests passed in 0.170s**, including all eight new integration tests.
The breakdown is 12 advisor, 10 video detector, 3 shadow monitor, 11
preview, 16 acknowledgement, and 8 lifecycle tests.

The integration fixture substitutes synthetic Detection classifications
for image recognition and exercises the real advisor, shadow monitor,
preview planner, and isolated acknowledgement simulation. It covers a
complete five-combat match with nine simulated proposals and nine
acknowledgements, rapid boss ending, delivery failure, extended combat,
unknown HUD, synthetic focus loss, ending latch, and emergency stop.
No production code or input routines changed. The fixture does not
establish real input response, real window focus behavior, or visual
recognition of MVP/menu screens. Its cinematic interval is UNKNOWN.
Next read-only milestone: inspect existing recorded post-match footage
to determine which distinct screens can be positively recognized and
which must remain unknown. Do not infer visual evidence from synthetic
phase fixtures.


## Recorded post-match visual investigation — November 26, 2026

Both original 1920x1080 recordings were reopened and their closing
sequences inspected visually. Sampled video times (seconds, not exact
transition times):

| Screen | clip_1,795,641,798,652.mp4 | clip_1,795,706,443,940.mp4 |
|---|---:|---:|
| Full-screen Victory banner | 193.52 | 270.35 |
| MVP animation | 195.44 | 274.18 |
| MVP statistics | 201.21 | 279.94 |
| Progression / acquired gear | 205.06 | 283.81 |
| Event rewards | 206.99 | 285.73 |
| Final character summary | 208.90 | 289.57 |
| ONE MORE ROUND label visible | 209.52 (fading in) | 291.37 (fully visible) |

The first clip ends during the final button fade-in; the second has
several samples of the fully displayed button. Neither shows a
subsequent hero selection or next-match loading sequence. The
progression page displays ACQUIRED THIS MATCH and SPACE NEXT /
SPACE HOLD TO SKIP. Event cards vary (two versus three cards);
the event page may display NEXT or SKIP. The final summary has
ESC BACK and later PREPARE / ONE MORE ROUND. A visible button label
does not prove the button is enabled.

Exploratory fixed-crop grayscale normalized correlation
(OpenCV TM_CCOEFF_NORMED, same-size reference and sample crop).
Templates were taken from the second recording; samples were decoded
sequentially at intervals of at least 0.49s from approximately 160s
(first clip) and 245s (second). 100 + 96 = 196 observations.
The first clip is a cross-recording check; the second is not independent
of calibration. The threshold 0.80 was exploratory, not a production
acceptance criterion.

| Visual marker | First clip hits / min score | Second clip hits / min score |
|---|---:|---:|
| Lower-right MVP logo | 17 / 0.956 | 16 / 0.956 |
| Upper-left VICTORY | 12 / 0.991 | 21 / 0.991 |
| ACQUIRED THIS MATCH | 3 / 0.997 | 3 / 0.998 |
| HOLD TO SKIP | 8 / 0.996 | 14 / 0.996 |
| Final summary BACK prompt | 4 / 0.998 | 7 / 0.998 |
| ONE MORE ROUND text | 1 / 0.983 | 4 / 0.999 |

No marker reached 0.80 in sampled pre-victory intervals
(t < 190s and t < 269s respectively); highest such score was 0.201.
The first clip's ONE MORE ROUND match was visually checked and the
label was still fading in, illustrating why text correlation alone
cannot establish availability. The MVP logo persists into the MVP
statistics card. The VICTORY corner and HOLD TO SKIP prompts are shared
by multiple pages, so they cannot distinguish event rewards from
progression on their own. Event cards and layouts can change; no
general event-reward classifier has been validated.

These are exploratory offline observations, not a production detector,
and not exhaustive frame-level ground truth. No code changes, live
capture, inputs, or new regression tests were made in this increment.
The verified Windows baseline remains 60 tests. Additional footage
covering the final summary through the next hero selection would
close the remaining visual evidence gap.


## Recorded match-to-match transition — November 26, 2026

New uploaded source: `clip_1,795,724,137,367.mp4`, 1920x1080,
124.317s duration. Inspected sampled frames throughout the clip and
full-resolution detail frames. The source covers the preceding boss
preparation, victory, post-match screens, next hero selection, loading,
first preparation, and first combat. Sampled timestamps (not exact
transition or input times):

| Seconds | Observed screen |
|---:|---|
| 8 | DRACULA INCOMING with BLESSING SHOP overlay |
| 28 | Full-screen VICTORY |
| 31 | MVP animation |
| 36 | MVP statistics |
| 40 | Progression / acquired gear |
| 41 | Event rewards |
| 45 | Final summary with ONE MORE ROUND and PREPARE |
| 50 | MATCH FOUND! overlay |
| 55 | BLOOD-NIGHT NEW YORK loading |
| 61 | BLOOD HUNT-NIGHTMARE 1; THOR selected; CONFIRM |
| 65 | THOR confirmed; CANCEL visible; countdown continues |
| 80 | Next match HUD |
| 85 | VAMPIRES INCOMING with BLESSING SHOP |
| 89 | VAMPIRES INCOMING, 4.8s, normal HUD visible |
| 95 | DEFEND THE AREA AND SURVIVE |

Exploratory same-clip fixed-crop grayscale normalized correlation
(TM_CCOEFF_NORMED). Reference frames at 45, 50, 61, 65, 85 seconds.
Sequential decode sampled at >=0.49s intervals, 248 observations
from 0 to 123.742s. Threshold 0.80 is exploratory, not production
calibration. Results:

| Marker | Hits | Sampled hit interval(s), s | Minimum hit score |
|---|---:|---|---:|
| ONE MORE ROUND | 7 | 45.11–48.11 | 0.936 |
| MATCH FOUND! | 3 | 49.64–50.65 | 0.818 |
| BLOOD HUNT-NIGHTMARE 1 | 38 | 60.19–78.69 | 0.915 |
| THOR name | 38 | 60.19–78.69 | 0.983 |
| CONFIRM YOUR HERO | 5 | 60.19–64.18, intermittent | 0.806 |
| CONFIRM | 5 | 60.68–62.68 | 0.903 |
| CANCEL | 32 | 63.18–78.69 | 0.997 |
| BLESSING SHOP | 9 | 7.03–9.53; 85.20–86.21 | 0.999 |

The shop match at 8s was independently visually checked against
the source frame. The shop is not exclusive to initial preparation:
it also appears before the preceding boss, with different cards.
Treat an obscured HUD as uncertain, not as a reliable Rune state.
The CONFIRM YOUR HERO text persists after confirmation and is
background-sensitive; it is not a reliable independent indication
of confirmation. The hero name and mode header are more stable in
this sample. No evidence that hero selection always defaults to
Thor, that the game accepts a particular input, or that visible
labels are necessarily actionable. The loading screen was visually
observed but not quantitatively tested. All correlations use
same-clip references; independent cross-recording validation and
frame-level ground truth remain outstanding for these new markers.

No production code, input handling, or tests changed. Verified
Windows baseline remains 60. This clip supplies the missing
visual examples; no additional recording is needed for the
current investigation. Future work can remain offline and
read-only, evaluating screen recognition on recorded footage.


## Post-match classifier baseline and three-recording replay

User Windows run: **77/77 tests passed in 0.720s**, including all
17 new classifier tests. Classifier commit 849197999114a367c1b66b9682486e03e02ff615,
tests commit 2a8204d52215898b14534808fd6f3bd3b9edbd7d.
Replay used a local classifier copy with git blob
880722521d32486ea6d124a14149caf32deaf408, verified against GitHub.
References from clip_1,795,724,137,367.mp4; threshold 0.85 unchanged.
OpenCV 4.13.0, FFmpeg fps=1, 1920x1080 BGR, full duration of each
recording, nominal output sample seconds (not exact source PTS).
No live capture or input.

| Classification | First clip | Second clip | Third clip |
|---|---:|---:|---:|
| map_loading | 2 | 3 | 2 |
| hero_selection | 18 | 14 | 19 |
| match_found | 0 | 1 | 2 |
| blessing_shop | 0 | 19 | 5 |
| victory_banner | 2 | 2 | 2 |
| mvp | 9 | 8 | 7 |
| progression | 1 | 2 | 2 |
| results | 3 | 5 | 5 |
| final_summary | 2 | 4 | 5 |
| unknown | 173 | 235 | 75 |
| Total | 210 | 293 | 124 |

627 sampled frames; 144 non-unknown, 483 unknown. Exact resampled
frame contact sheets included all non-unknown samples and their
immediate neighbors (42 + 77 + 62 = 181 visually inspected samples).
Both independent clips recognize loading, hero selection, victory,
MVP, progression, generic results and final summary. The second
clip additionally recognizes five distinct Blessing Shop intervals
and Match Found. No non-unknown sample reviewed was ordinary
unobscured combat. This is a targeted visual audit, not exhaustive
ground truth or a measured accuracy rate.

Observed limitations: alternate map loading illustration is missed
(first 2s, second 17s, third 57/59s); Match Found animation is
intermittent (second 6/8s unknown; third 51/52s generic results
despite overlay). MVP effects produce unknown frames (second 278s,
third 32/35s). Early progression is generic results until acquired
marker appears (first 204s, second 282s). The third clip returns
generic results at 48s and 51–52s during transition, so per-frame
labels alone do not establish a monotonic match lifecycle.
Final summary is not evidence of button availability. No changes
to classifier thresholds or production code in this increment.
The next read-only review should preserve these uncertainties
and distinguish raw frame labels from a retrospective timeline.


## Unified timeline regression baseline

The user downloaded lifecycle_timeline.py (commit
5eafe705e615ae03db1a13b459331a4164c96487) and its 12 tests
(commit 39563d73c0d90caaca61d14854e511481c086887).
Windows unittest discovery returned **89/89 passed in 0.349s**.
The retrospective report combines raw wave and screen observations,
preserves unknown/conflicting observations and masks the displayed Rune
state when an overlay is identified. The segment report groups only
contiguous observed labels; it does not interpolate unknown frames.
This is a unit-test baseline, not an end-to-end video replay result.
The full Windows CLI replay remains to be validated. No live input
handling or existing classifier threshold changes were made.
