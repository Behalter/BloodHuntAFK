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
