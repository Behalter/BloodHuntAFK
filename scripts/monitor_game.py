#!/usr/bin/env python3
"""Monitor Marvel Rivals' visible HUD without sending any gameplay inputs.

Uses the calibrated, read-only MP4 detector with the existing screen capture
module. Logs phases and Rune recommendations in CSVs. It does NOT start the
BloodHuntAFK bot, click Skip, press F/X, refocus the game, or run routines.
Exit with Ctrl+C. Windows only because bloodhunt.vision uses Windows APIs.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import time

from scripts.analyze_video import Calibration, normalize
from scripts.shadow_monitor import EVENT_FIELDS, SAMPLE_FIELDS, ShadowMonitor


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-video", required=True, type=Path,
                        help="Existing MP4 with clear reference UI images")
    parser.add_argument("--output", type=Path, default=Path("shadow_results"))
    parser.add_argument("--rate", type=float, default=2.0,
                        help="Maximum screen observations per second (default 2)")
    parser.add_argument("--prep-second", type=float, default=55)
    parser.add_argument("--combat-second", type=float, default=80)
    parser.add_argument("--victory-second", type=float, default=285)
    parser.add_argument("--ready-second", type=float, default=56)
    parser.add_argument("--boss-objective-second", type=float, default=255)
    parser.add_argument("--ending-second", type=float, default=260)
    args = parser.parse_args(argv)
    if not 0 < args.rate <= 10:
        parser.error("--rate must be greater than zero and no more than 10")
    try:
        calibration = Calibration.from_video(
            args.reference_video, args.prep_second, args.combat_second,
            args.victory_second, args.ready_second,
            args.boss_objective_second, args.ending_second)
    except (ValueError, OSError) as exc:
        parser.error(f"cannot calibrate reference video: {exc}")

    # Import only after validating the offline reference video. These modules
    # read the Windows game window and screen; the input module is NEVER used.
    from bloodhunt import vision, winapi

    args.output.mkdir(parents=True, exist_ok=True)
    events_path = args.output / "events.csv"
    timeline_path = args.output / "timeline.csv"
    monitor = ShadowMonitor(calibration)
    screen = vision.Screen()
    start = time.monotonic()
    observations = 0
    print("Read-only shadow monitor. NO keyboard or mouse actions will be sent.")
    print("Start a match manually. Press Ctrl+C here to stop.")
    print(f"Writing {timeline_path} and {events_path} (game foreground only)")
    try:
        with timeline_path.open("w", newline="", encoding="utf-8") as tf, \
             events_path.open("w", newline="", encoding="utf-8") as ef:
            tw = csv.DictWriter(tf, fieldnames=SAMPLE_FIELDS)
            ew = csv.DictWriter(ef, fieldnames=EVENT_FIELDS)
            tw.writeheader()
            ew.writeheader()
            while True:
                iteration_start = time.monotonic()
                # Never resume a stale phase after a focus change. We simply
                # skip frames when another application is in the foreground.
                if winapi.game_in_front():
                    screen.refresh()
                    if screen.size[0] * 9 == screen.size[1] * 16:
                        image = normalize(screen.grab())
                        sample = monitor.feed(iteration_start - start, image)
                        tw.writerow(sample.csv_row())
                        observations += 1
                        for event in sample.events:
                            ew.writerow(event.csv_row())
                            ef.flush()
                            print(f"{event.seconds:7.2f}s  {event.kind:<10} "
                                  f"{event.phase:<13} {event.rune:<9} {event.details}")
                        if observations % 10 == 0:
                            tf.flush()
                    elif observations == 0:
                        print(f"Waiting for 16:9 game picture; found {screen.size}")
                time.sleep(max(0, 1 / args.rate - (time.monotonic() - iteration_start)))
    except KeyboardInterrupt:
        print(f"Stopped read-only shadow monitor after {observations} observations.")
    finally:
        if hasattr(screen.sct, "close"):
            screen.sct.close()
    print(f"Timeline: {timeline_path}\nEvents: {events_path}")


if __name__ == "__main__":
    main()
