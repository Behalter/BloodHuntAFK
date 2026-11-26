# Offline Blood Hunt video analysis

This is a read-only MP4 analyzer, **not** a replacement for the live bot. It
writes two CSVs, never sends keyboard/mouse inputs, and never launches the game.

## Windows setup

1. Keep your original BloodHuntAFK-main folder unchanged.
2. Open [the development branch](https://github.com/Behalter/BloodHuntAFK/tree/feature/wave-aware-rune),
   select Code > Download ZIP, and extract it into a **separate** folder.
3. Open PowerShell in the extracted folder and install dependencies:

   ~~~powershell
   py -3.15 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ~~~

4. Save the **exported MP4** somewhere convenient, such as Downloads.
   Replace the placeholder path below with its actual name:

   ~~~powershell
   .\.venv\Scripts\python.exe scripts\analyze_video.py "C:\Users\YOUR_USER\Downloads\BloodHuntTest.mp4"
   ~~~

5. Read the generated files:
   - video_analysis_output/events.csv: notable phases, Rune changes, suggestions
   - video_analysis_output/timeline.csv: every sampled frame and match scores

To run all offline tests:

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~

**No administrator permissions are needed.**

## What gets recognized

- **Preparation**: the shared INCOMING suffix, including VAMPIRES INCOMING
  and DRACULA INCOMING, independent of the boss name.
- **Combat**: a positive DEFEAT title during ordinary vampire waves, or
  a long orange boss-health bar **and** matching generic boss-objective
  text, for the final encounter in the reference recording.
  Neither a boss label alone nor an orange visual alone is sufficient.
- **Match ending**: the generic MATCH ENDING SOON message, a separate
  phase where no more Rune action is suggested. Recognition remains
  suppressed if a cinematic briefly obscures the text.
- **Post-match**: the VICTORY results screen.
- **Rune**: colors only in the reference F-icon silhouette. White means
  READY, yellow/gold ACTIVE, and dark red COOLDOWN. Otherwise UNKNOWN.

Preparation and combat are confirmed after two consistent sampled frames.
The disappearance of the preparation banner alone is not evidence of combat.

## Calibration

Defaults are **specific to the user's first 3:30 recording** from Blood Night
New York at 1920x1080:

| Reference visual | Timestamp |
| --- | ---: |
| White VAMPIRES INCOMING | 00:33 |
| DEFEAT ALL VAMPIRES | 01:20 |
| VICTORY results screen | 03:26 |
| F icon visibly ready/white | 00:33 |
| Generic boss objective + long orange health bar | 02:57.5 |
| MATCH ENDING SOON | 03:01 |

The analyzer extracts small visual calibration patterns from the supplied MP4;
it neither uses OCR nor stores private screenshots.

For a different video, reuse the original calibration source:

~~~powershell
.\.venv\Scripts\python.exe scripts\analyze_video.py "C:\path\new.mp4" --reference-video "C:\path\first-clip.mp4"
~~~

For another reference clip, override its sample moments with
--prep-second, --combat-second, --victory-second, --ready-second,
--boss-objective-second, and --ending-second.

Only 16:9 video is supported for now. Other maps, localization, UI scaling,
different objectives, and new post-match screens require recalibration.
Timestamps use the nominal video frame rate and are approximate if the export
has variable frame rate.

## First validation results

On the first recorded run, the local prototype sampled **422 frames** and
detected **five preparation phases**, **four normal vampire combat phases**,
**a short boss combat phase at approximately 02:57.5–02:59.0**, the
**match-ending overlay at approximately 02:59.5–03:09.5**, and the
**victory results screen at approximately 03:25**.

- 00:25.5: preparation, Rune ready
- 00:40.5: combat; suggests initial activation
- 00:43.5: F icon changes to active
- 01:01.0: next preparation; active
- 01:36.0: preparation
- 01:39.5: F icon changes to cooldown
- 01:49.0: F icon changes to active
- 02:12.0: preparation
- 02:42.5: Dracula preparation
- 02:57.5: boss combat positively confirmed with objective and health bar
- 02:59.5: MATCH ENDING SOON overlay detected
- 03:09.5–03:25: cinematic/unknown; Rune advice remains suppressed
- 03:25.5: victory screen

These observations **do not establish** that manually cancelling Rune resets
its cooldown or duration. That needs a separate supervised manual experiment.

## Safeguards

No inputs are sent, the existing gameplay loop remains untouched, and
automatic gear smelting is not enabled by this tool. Never treat offline
detection as permission to use live automation: Marvel Rivals prohibits
unauthorized automation scripts and account penalties are possible.
Avoid committing raw video or player-UID screenshots to this public fork.


## November 26 detector revision

The previous analyzer left the final encounter UNKNOWN. The revised detector
looks for **two independent signals** (boss health bar + generic objective)
to confirm boss combat and separately detects the MATCH ENDING SOON overlay.
The first recorded match was re-scanned locally at 2 samples/second:
five preparation intervals, four ordinary combats, one short boss combat,
one match-ending overlay and victory were all observed. The ending transition
also latches in the advisor, preventing late recommendations through cutscenes.

These reference-marker changes were validated against the supplied recording
and focused synthetic pattern checks. The complete unit-test suite remains
to be run on Windows after downloading the updated development branch.
The logic is still read-only and not integrated with the live bot.

## Second recording validation — November 26, 2026

The second 1920x1080 / approximately 4:53 recording contains four ordinary
**Defend the Area and Survive** waves instead of **Defeat All Vampires**,
followed by a **Ratatoskr** boss. This exposed a false negative: the old
combat detector used the literal DEFEAT objective template and reported
UNKNOWN for all four ordinary combat intervals, though it identified all five
INCOMING banners correctly.

The revised detector includes a *generic Phase header* marker that appears
under both types of objective, **and** requires Thor's F icon to be positively
recognized. A frame-based local comparison at one sample per second classified
all four ordinary combat intervals and the short boss phase.

| Second video (approx.) | Screen | Detection |
| --- | --- | --- |
| 00:50–01:04 | Incoming preparation | Preparation |
| 01:05–01:39 | Survive wave 1 | Combat |
| 01:40–01:54 | Incoming preparation | Preparation |
| 01:55–02:35 | Survive wave 2 | Combat |
| 02:36–02:50 | Incoming preparation | Preparation |
| 02:51–03:17 | Survive wave 3 | Combat |
| 03:18–03:32 | Incoming preparation | Preparation |
| 03:33–03:57 | Survive wave 4 | Combat |
| 03:58–04:12 | Ratatoskr incoming | Preparation |
| 04:14–04:16 | Ratatoskr boss health bar | Combat |
| 04:17–04:26 | Match ending soon | Match ending |
| 04:42 onward | Victory/results | Post-match |

The intervals above are from **sampled recorded frames**, not a live
automated gameplay test. A number of initial loading/card-selection frames
remain UNKNOWN by design. This is preferable to issuing unwanted actions.

To analyze the second MP4 using its **own** reference frames, in PowerShell
from the latest development branch, run:

~~~powershell
.\.venv\Scripts\python.exe scripts\analyze_video.py "C:\Users\succe\Videos\clip_1,795,706,443,940.mp4" --prep-second 55 --combat-second 80 --victory-second 285 --ready-second 56 --boss-objective-second 255 --ending-second 260 --output second_recording_results
~~~

The quoted path above comes from the user-supplied recording location.
The optional reference timestamps make this analysis self-calibrating for
the second recording. For a different clip, verify and adjust them rather
than reusing these timestamps blindly.

**Validation boundary:** The revised phase-marker and boss rules were
checked against extracted sampled frames from both supplied recordings.
The complete newly updated Windows test suite and an end-to-end run of the
updated GitHub analyzer on the user's PC have not yet been verified. Do not
merge to main or enable gameplay inputs based solely on these offline checks.
