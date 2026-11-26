#!/usr/bin/env python3
"""Read-only Blood Hunt MP4 analyzer for the user's first 1920x1080 Steam recording.

Calibrates from known example moments in a reference video. Finds the shared
INCOMING text (including boss announcements), a positive combat title, the
VICTORY results screen, and Thor's F icon colors. Feeds those observations
into wave_state.WaveAdvisor and writes CSVs. NO LIVE INPUTS OR GAME ACCESS.

The default sample times apply to the November 25 Blood Night New York clip.
Other maps, resolutions, languages, or HUDs require fresh validation.
"""
from __future__ import annotations
import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from bloodhunt.wave_state import Observation, Phase, Rune, WaveAdvisor

REFERENCE_SHAPE = (1920, 1080)
INCOMING_GLYPH = (970, 7, 1045, 26)
COMBAT_GLYPH = (874, 29, 927, 49)
VICTORY_GLYPH = (50, 23, 340, 94)
# Generic boss objective header and a long orange boss-health bar.
# Both must be present; an isolated orange bar can appear in cinematics.
BOSS_OBJECTIVE_GLYPH = (63, 71, 231, 93)
BOSS_OBJECTIVE_SEARCH = (35, 63, 285, 103)
# The word "Phase" and its wave icon are stable across both elimination
# and survival objectives. Only trust it with a visible, classifiable F icon;
# otherwise a card menu or loading scene could look like combat.
PHASE_HEADER_GLYPH = (45, 62, 103, 82)
PHASE_HEADER_SEARCH = (26, 56, 150, 93)
BOSS_BAR_AREA = (650, 105, 1290, 160)
MATCH_ENDING_GLYPH = (880, 35, 1047, 56)
MATCH_ENDING_SEARCH = (770, 23, 1150, 73)
F_GLYPH = (1650, 953, 1705, 997)
INCOMING_SEARCH = (820, 0, 1120, 40)
COMBAT_SEARCH = (700, 20, 1220, 60)
VICTORY_SEARCH = (0, 0, 470, 115)


def box(image, rect):
    x0, y0, x1, y1 = rect
    return image[y0:y1, x0:x1]


def light_text(image):
    """Binary mask of white/yellow text; ignores most backgrounds. No OCR."""
    b, g, r = cv2.split(image)
    white = (r > 165) & (g > 160) & (b > 160)
    yellow = (r > 160) & (g > 135) & (b < 175)
    return np.where(white | yellow, 255, 0).astype(np.uint8)


def normalize(frame):
    h, w = frame.shape[:2]
    if abs(w / h - 16 / 9) > 0.01:
        raise ValueError(f"Expected 16:9 video, got {w}x{h}")
    if (w, h) != REFERENCE_SHAPE:
        return cv2.resize(frame, REFERENCE_SHAPE, interpolation=cv2.INTER_AREA)
    return frame


def frame_at(video: Path, seconds: float):
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video}")
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, frame = cap.read()
        if not ok:
            raise ValueError(f"Cannot read {video} at {seconds:g}s")
        return normalize(frame)
    finally:
        cap.release()


def bright_white(image):
    b, g, r = cv2.split(image)
    return (r > 130) & (g > 130) & (b > 130) & (
        np.abs(r.astype(np.int16) - g.astype(np.int16)) < 45)


@dataclass
class Calibration:
    incoming: np.ndarray
    combat: np.ndarray
    victory: np.ndarray
    boss_objective: np.ndarray
    ending: np.ndarray
    f_glyph: np.ndarray
    phase_header: np.ndarray | None = None  # optional for old synthetic fixtures

    @classmethod
    def from_video(cls, video: Path, prep: float, combat: float,
                   victory: float, ready: float,
                   boss_objective: float = 177.5, ending: float = 181.0):
        inc = light_text(box(frame_at(video, prep), INCOMING_GLYPH))
        fight = light_text(box(frame_at(video, combat), COMBAT_GLYPH))
        win = light_text(box(frame_at(video, victory), VICTORY_GLYPH))
        boss = light_text(box(frame_at(video, boss_objective), BOSS_OBJECTIVE_GLYPH))
        ending_mask = light_text(box(frame_at(video, ending), MATCH_ENDING_GLYPH))
        f = bright_white(box(frame_at(video, ready), F_GLYPH))
        phase_header = light_text(box(frame_at(video, combat), PHASE_HEADER_GLYPH))
        for name, mask in (("incoming", inc), ("combat", fight),
                           ("victory", win), ("boss objective", boss),
                           ("match ending", ending_mask), ("ready F", f),
                           ("phase header", phase_header)):
            density = float(mask.mean() / 255) if mask.dtype == np.uint8 else float(mask.mean())
            if not 0.08 < density < 0.85:
                raise ValueError(f"Invalid {name} reference; verify reference timestamp")
        return cls(inc, fight, win, boss, ending_mask, f, phase_header)


def match_score(frame, template, search):
    """Match a meaningful binary text marker, never an empty/sparse placeholder.

    TM_CCOEFF_NORMED can give misleadingly high scores to an almost empty
    synthetic template (for example, one white pixel among many black pixels).
    Real calibration markers are already required to have 8–85% foreground.
    Enforce that same contract here so an invalid marker cannot recognize an
    unrelated screen, including the Victory/results overlay.
    """
    if template.ndim != 2 or template.size == 0:
        return 0.0
    density = np.count_nonzero(template) / template.size
    if not 0.08 < density < 0.85:
        return 0.0
    region = light_text(box(frame, search))
    if region.shape[0] < template.shape[0] or region.shape[1] < template.shape[1]:
        return 0.0
    score = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
    return float(np.nan_to_num(score.max(), nan=0.0))


def boss_health_bar_run(frame):
    """Longest orange horizontal segment within the fixed boss-health-bar area.

    Restrict to the health bar and require an independent generic boss-objective
    match. The orange match summary graphics alone must not count as combat.
    """
    patch = box(frame, BOSS_BAR_AREA)
    b, g, r = cv2.split(patch)
    orange = ((r > 115) & (g > 60) & (g < 190) & (b < 140) &
              (r > g * 1.3) & (g > b * 1.2))
    longest = 0
    for row in orange:
        transitions = np.diff(np.r_[False, row, False].astype(np.int8))
        begins = np.flatnonzero(transitions == 1)
        if len(begins):
            ends = np.flatnonzero(transitions == -1)
            longest = max(longest, int((ends - begins).max()))
    return longest


def classify_rune(frame, reference_mask):
    """Only read colors at pixels belonging to the known white F icon glyph."""
    if reference_mask.sum() < 50:
        return Rune.UNKNOWN
    b, g, r = [c.astype(np.float32) for c in cv2.split(box(frame, F_GLYPH))]
    white = (r > 130) & (g > 130) & (b > 130) & (np.abs(r-g) < 45)
    gold = (r > 120) & (g > 95) & (b < 170) & (r > b*1.35)
    red = (r > 65) & (r > g*1.25) & (r > b*1.3) & (g < 115)
    coverage = [float(mask[reference_mask].mean()) for mask in (white, gold, red)]
    best = int(np.argmax(coverage))
    if coverage[best] < 0.70:
        return Rune.UNKNOWN
    return (Rune.READY, Rune.ACTIVE, Rune.COOLDOWN)[best]


@dataclass(frozen=True)
class Detection:
    phase: Phase
    rune: Rune
    incoming_score: float
    combat_score: float
    victory_score: float
    boss_objective_score: float = 0.
    ending_score: float = 0.
    boss_bar_run: int = 0
    phase_header_score: float = 0.


def detect(frame, calibration):
    incoming = match_score(frame, calibration.incoming, INCOMING_SEARCH)
    combat = match_score(frame, calibration.combat, COMBAT_SEARCH)
    victory = match_score(frame, calibration.victory, VICTORY_SEARCH)
    ending = match_score(frame, calibration.ending, MATCH_ENDING_SEARCH)
    boss_objective = match_score(frame, calibration.boss_objective, BOSS_OBJECTIVE_SEARCH)
    bar_run = boss_health_bar_run(frame)
    phase_header = (match_score(frame, calibration.phase_header, PHASE_HEADER_SEARCH)
                    if calibration.phase_header is not None else 0.0)
    possible_rune = classify_rune(frame, calibration.f_glyph)
    if victory >= 0.90:
        phase = Phase.POST_MATCH
    elif ending >= 0.90:
        phase = Phase.MATCH_ENDING
    elif incoming >= 0.78:
        phase = Phase.PREPARATION
    elif (combat >= 0.86 or
          (phase_header >= 0.88 and possible_rune is not Rune.UNKNOWN) or
          (boss_objective >= 0.90 and bar_run >= 180)):
        phase = Phase.COMBAT
    else:
        phase = Phase.UNKNOWN
    rune = possible_rune if phase in (Phase.PREPARATION, Phase.COMBAT) else Rune.UNKNOWN
    return Detection(phase, rune, incoming, combat, victory,
                     boss_objective, ending, bar_run, phase_header)


def sampled_frames(video: Path, sample_rate: float):
    """Sequential decoding using presentation timestamps, including VFR clips.

    Steam recordings may be variable-frame-rate. index / average_fps can
    drift several seconds from the actual countdown shown in the footage.
    Prefer each decoded frame's media timestamp; estimate from the average
    frame rate only if OpenCV provides no usable timestamp.
    """
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps < 1 or fps > 240:
            raise ValueError(f"Invalid video FPS: {fps}")
        index, next_sample, previous_time = 0, 0.0, -1.0
        while cap.grab():
            presentation_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if (not np.isfinite(presentation_time) or
                    (presentation_time <= 0 and index > 0) or
                    presentation_time < previous_time):
                seconds = max(index / fps, previous_time)
            else:
                seconds = presentation_time
            previous_time = seconds
            index += 1
            if seconds + 1e-6 < next_sample:
                continue
            ok, frame = cap.retrieve()
            if not ok:
                break
            yield seconds, normalize(frame)
            next_sample += 1 / sample_rate
    finally:
        cap.release()


def analyze(video: Path, reference: Path, out: Path, *, rate: float = 2.,
            preparation_second: float = 33., combat_second: float = 80.,
            victory_second: float = 206., ready_second: float = 33.,
            boss_objective_second: float = 177.5, ending_second: float = 181.):
    if rate <= 0 or rate > 30:
        raise ValueError("--rate must be >0 and <=30")
    cal = Calibration.from_video(reference, preparation_second, combat_second,
                                 victory_second, ready_second,
                                 boss_objective_second, ending_second)
    out.mkdir(parents=True, exist_ok=True)
    timeline_path, events_path = out / "timeline.csv", out / "events.csv"
    advisor = WaveAdvisor(stable_frames=2, long_wave_seconds=75)
    fields = ("seconds", "detected_phase", "rune", "incoming_score",
              "combat_score", "victory_score", "boss_objective_score",
              "ending_score", "boss_bar_run", "phase_header_score",
              "confirmed_phase", "suggestions")
    event_fields = ("seconds", "kind", "phase", "rune", "details")
    events, samples = [], 0
    seen_rune, pending_rune, pending_count = Rune.UNKNOWN, Rune.UNKNOWN, 0
    with timeline_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for seconds, frame in sampled_frames(video, rate):
            d = detect(frame, cal)
            decision = advisor.observe(Observation(seconds, d.phase, d.rune))
            writer.writerow(dict(seconds=f"{seconds:.2f}",
                detected_phase=d.phase.value, rune=d.rune.value,
                incoming_score=f"{d.incoming_score:.3f}",
                combat_score=f"{d.combat_score:.3f}",
                victory_score=f"{d.victory_score:.3f}",
                boss_objective_score=f"{d.boss_objective_score:.3f}",
                ending_score=f"{d.ending_score:.3f}",
                boss_bar_run=d.boss_bar_run,
                phase_header_score=f"{d.phase_header_score:.3f}",
                confirmed_phase=decision.confirmed_phase.value,
                suggestions=";".join(s.value for s in decision.suggestions)))
            if d.rune is Rune.UNKNOWN:
                pending_rune, pending_count = Rune.UNKNOWN, 0
            elif d.rune == pending_rune:
                pending_count += 1
            else:
                pending_rune, pending_count = d.rune, 1
            if pending_count >= 2 and pending_rune != seen_rune:
                previous, seen_rune = seen_rune, pending_rune
                events.append(dict(seconds=f"{seconds:.2f}", kind="rune",
                    phase=d.phase.value, rune=d.rune.value,
                    details=f"F icon: {previous.value} -> {seen_rune.value}"))
            if decision.transition_confirmed:
                events.append(dict(seconds=f"{seconds:.2f}", kind="phase",
                    phase=decision.confirmed_phase.value, rune=d.rune.value,
                    details="phase confirmed"))
            for suggestion in decision.suggestions:
                events.append(dict(seconds=f"{seconds:.2f}", kind="suggestion",
                    phase=decision.confirmed_phase.value, rune=d.rune.value,
                    details=suggestion.value))
            samples += 1
    with events_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=event_fields)
        writer.writeheader()
        writer.writerows(events)
    return samples, events, timeline_path, events_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path, help="MP4 to analyze (never modified)")
    parser.add_argument("--reference-video", type=Path,
        help="MP4 with calibration moments; defaults to the target video")
    parser.add_argument("--output", type=Path, default=Path("video_analysis_output"))
    parser.add_argument("--rate", type=float, default=2.0, help="Samples/second")
    parser.add_argument("--prep-second", type=float, default=33.0)
    parser.add_argument("--combat-second", type=float, default=80.0)
    parser.add_argument("--victory-second", type=float, default=206.0)
    parser.add_argument("--ready-second", type=float, default=33.0)
    parser.add_argument("--boss-objective-second", type=float, default=177.5)
    parser.add_argument("--ending-second", type=float, default=181.0)
    args = parser.parse_args(argv)
    try:
        n, events, timeline, event_path = analyze(
            args.video, args.reference_video or args.video, args.output,
            rate=args.rate, preparation_second=args.prep_second,
            combat_second=args.combat_second, victory_second=args.victory_second,
            ready_second=args.ready_second,
            boss_objective_second=args.boss_objective_second,
            ending_second=args.ending_second)
    except (ValueError, OSError, cv2.error) as exc:
        parser.exit(2, f"Analysis failed: {exc}\n")
    print(f"Analyzed {n} sampled frames (read only).")
    print(f"Timeline: {timeline}\nEvents: {event_path}")
    for e in events:
        print(f"{e['seconds']:>7}s  {e['kind']:<10} {e['phase']:<12} {e['rune']:<9} {e['details']}")
    print("No game controls were sent; Rune suggestions require manual verification.")


if __name__ == "__main__":
    main()
