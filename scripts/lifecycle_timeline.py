"""Retrospective recorded-video report. No live capture or input handling."""
from dataclasses import asdict, dataclass
from math import isfinite
import csv
from pathlib import Path

WAVE_PHASES = {"unknown", "preparation", "combat", "match_ending", "post_match"}
RUNES = {"unknown", "ready", "active", "cooldown"}
RESULTS = {"victory_banner", "mvp", "progression", "results", "final_summary"}
SCREENS = RESULTS | {"unknown", "match_found", "map_loading", "hero_selection", "blessing_shop"}


@dataclass(frozen=True)
class TimelineRow:
    seconds: float
    raw_phase: str
    raw_rune: str
    raw_screen: str
    markers: str
    screen: str
    visible_rune: str
    reason: str


def combine(seconds, phase, rune, screen, markers=()):
    """Describe a single recorded sample; never infer missing observations."""
    if not isfinite(seconds) or seconds < 0:
        raise ValueError("Invalid sample timestamp")
    if phase not in WAVE_PHASES or rune not in RUNES or screen not in SCREENS:
        raise ValueError("Invalid classification")
    hits = tuple(sorted(set(markers)))
    label, visible = "unknown", "unknown"
    if screen == "blessing_shop" and phase in {"unknown", "preparation", "combat"}:
        label, reason = screen, "overlay_observed"
    elif screen != "unknown":
        if phase == "unknown" or (phase == "post_match" and screen in RESULTS | {"match_found"}):
            label, reason = screen, "screen_observed"
        else:
            reason = "classifier_disagreement"
    elif hits:
        reason = "unresolved_screen_markers"
    elif phase != "unknown":
        label, reason = phase, "wave_observed"
        if phase in {"preparation", "combat"}:
            visible = rune
    else:
        reason = "no_positive_classification"
    return TimelineRow(seconds, phase, rune, screen, ";".join(hits), label, visible, reason)


@dataclass(frozen=True)
class Segment:
    first_sample: float
    last_sample: float
    screen: str
    samples: int


def segments(rows, max_gap=2.5):
    """Group contiguous observed labels, retaining unknown and sampling gaps.

    Endpoints are sample times, not exact transition times or durations.
    """
    if not isfinite(max_gap) or max_gap <= 0:
        raise ValueError("Invalid maximum gap")
    result = []
    for row in rows:
        if not result:
            result.append(Segment(row.seconds, row.seconds, row.screen, 1))
            continue
        previous = result[-1]
        gap = row.seconds - previous.last_sample
        if gap < 0:
            raise ValueError("Samples must be chronological")
        if gap <= max_gap and row.screen == previous.screen:
            result[-1] = Segment(previous.first_sample, row.seconds, row.screen, previous.samples + 1)
        else:
            result.append(Segment(row.seconds, row.seconds, row.screen, 1))
    return result


def write_csv(path, records, record_type):
    with path.open("x", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=tuple(record_type.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(record) for record in records)


def main(argv=None):
    import argparse
    import cv2
    from scripts.analyze_video import Calibration, detect, sampled_frames
    from scripts.post_match_detector import PostMatchDetector

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--wave-reference", type=Path, required=True,
                        help="Second recording, clip_1,795,706,443,940.mp4")
    parser.add_argument("--screen-reference", type=Path, required=True,
                        help="Third recording, clip_1,795,724,137,367.mp4")
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    parser.add_argument("--rate", type=float, default=1.0)
    args = parser.parse_args(argv)
    try:
        if not isfinite(args.rate) or not 0 < args.rate <= 5:
            raise ValueError("Rate must be >0 and <=5")
        if args.output.exists():
            raise ValueError("Output directory already exists; choose a new directory")
        for path in (args.video, args.wave_reference, args.screen_reference):
            if not path.is_file():
                raise ValueError(f"Not a local video file: {path}")
            cap = cv2.VideoCapture(str(path))
            try:
                if not cap.isOpened() or (cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) != (1920, 1080):
                    raise ValueError(f"Expected 1920x1080 recording: {path}")
            finally:
                cap.release()
        wave = Calibration.from_video(args.wave_reference, 55., 80., 285., 56., 255., 260.)
        post = PostMatchDetector.from_recording(args.screen_reference)
        rows = []
        for seconds, frame in sampled_frames(args.video, args.rate):
            d = detect(frame, wave)
            p = post.classify(frame)
            rows.append(combine(seconds, d.phase.value, d.rune.value, p.screen, p.markers))
        if not rows:
            raise ValueError("No decoded samples")
        grouped = segments(rows, max_gap=2.5 / args.rate)
        args.output.mkdir(parents=True, exist_ok=False)
        write_csv(args.output / "lifecycle_samples.csv", rows, TimelineRow)
        write_csv(args.output / "lifecycle_segments.csv", grouped, Segment)
    except (ValueError, OSError, cv2.error) as exc:
        parser.exit(2, f"Report failed: {exc}\n")
    print(f"Recorded samples: {len(rows)}; observed segments: {len(grouped)}")
    print(f"Reports: {args.output}")
    print("Read-only retrospective report; unknown samples are not interpolated.")


if __name__ == "__main__":
    main()
