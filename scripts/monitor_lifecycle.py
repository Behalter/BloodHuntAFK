"""Read-only live lifecycle observations; no input, previews, or bot loop.

Run only where screen observation is permitted. Captures foreground game
frames, writes classification metadata (not screenshots), and stops on
Ctrl+C or the time limit. Unknown observations are never interpolated.
"""
import argparse
import csv
from dataclasses import asdict
from math import isfinite
from pathlib import Path
import time

from scripts.analyze_video import Calibration, detect, normalize
from scripts.lifecycle_timeline import TimelineRow, Segment, combine, segments, write_csv
from scripts.post_match_detector import PostMatchDetector


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wave-reference", required=True, type=Path)
    parser.add_argument("--screen-reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--rate", type=float, default=2.0)
    parser.add_argument("--minutes", type=float, default=15.0)
    args = parser.parse_args(argv)
    if not isfinite(args.rate) or not 0 < args.rate <= 5:
        parser.error("rate must be >0 and <=5")
    if not isfinite(args.minutes) or not 0 < args.minutes <= 30:
        parser.error("minutes must be >0 and <=30")
    if args.output.exists():
        parser.error("choose a new output directory")
    if not all(p.is_file() for p in (args.wave_reference, args.screen_reference)):
        parser.error("references must be local recording files")
    wave = Calibration.from_video(args.wave_reference, 55., 80., 285., 56., 255., 260.)
    post = PostMatchDetector.from_recording(args.screen_reference)

    from bloodhunt import vision, winapi

    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    previous = None
    screen = vision.Screen()
    start = time.monotonic()
    print("Read-only lifecycle monitor. No keyboard or mouse input.")
    print("Play manually; Ctrl+C stops. No screenshots saved.")
    try:
        with (args.output / "lifecycle_samples.csv").open("x", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=tuple(TimelineRow.__dataclass_fields__))
            writer.writeheader()
            while time.monotonic() - start < args.minutes * 60:
                tick = time.monotonic()
                area = winapi.game_area() if winapi.game_in_front() else None
                if area:
                    screen.refresh()
                    w, h = screen.size
                    captured_area = (screen.mon["left"], screen.mon["top"], w, h)
                    if w > 0 and h > 0 and w * 9 == h * 16 and tuple(area) == captured_area:
                        frame = screen.grab()
                        # Discard samples if focus or geometry changed during capture.
                        if winapi.game_in_front() and winapi.game_area() == area:
                            image = normalize(frame)
                            d = detect(image, wave)
                            p = post.classify(image)
                            row = combine(tick - start, d.phase.value, d.rune.value, p.screen, p.markers)
                            rows.append(row)
                            writer.writerow(asdict(row))
                            f.flush()
                            label = (row.screen, row.visible_rune, row.reason)
                            if label != previous:
                                print(f"{row.seconds:7.2f}s  {row.screen:<16} {row.visible_rune:<9} {row.reason}", flush=True)
                                previous = label
                else:
                    previous = None
                time.sleep(max(0, 1 / args.rate - (time.monotonic() - tick)))
    except KeyboardInterrupt:
        print("Stopped by operator.")
    finally:
        screen.sct.close()
        grouped = segments(rows, max_gap=2.5 / args.rate)
        write_csv(args.output / "lifecycle_segments.csv", grouped, Segment)
        print(f"Recorded samples: {len(rows)}; observed segments: {len(grouped)}")
        print(f"Reports: {args.output}")


if __name__ == "__main__":
    main()
