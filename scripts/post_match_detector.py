"""Offline screen classification for recorded 1920x1080 Blood Hunt footage.

Reference times are specific to clip_1,795,724,137,367.mp4. This module
has no capture, game control, or input dependencies. Labels describe
visible screens, not button availability or recommended actions.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import cv2
import numpy as np

# name: (reference seconds, fixed crop x0, y0, x1, y1)
MARKERS = {
    "victory_banner": (28, (480, 430, 1440, 720)),
    "mvp": (31, (1540, 875, 1900, 1005)),
    "victory_header": (40, (35, 25, 340, 105)),
    "acquired": (40, (1090, 270, 1310, 305)),
    "summary": (45, (1780, 1028, 1910, 1065)),
    "match_found": (50, (500, 450, 1450, 650)),
    "map_title": (55, (680, 370, 1240, 580)),
    "hero_mode": (61, (0, 43, 510, 91)),
    "shop": (85, (890, 200, 1030, 230)),
}


@dataclass(frozen=True)
class ScreenObservation:
    screen: str
    markers: tuple[str, ...]


def classify_scores(scores: Mapping[str, float], threshold: float = 0.85):
    """Classify evidence conservatively; missing/invalid scores are unknown."""
    if not 0 < threshold <= 1:
        raise ValueError("threshold must be in (0, 1]")
    if set(scores) != set(MARKERS) or any(
        not np.isfinite(v) or not -1 <= v <= 1 for v in scores.values()
    ):
        return ScreenObservation("unknown", ())
    hits = {name for name, score in scores.items() if score >= threshold}
    groups = hits & {"victory_banner", "mvp", "match_found", "map_title",
                     "hero_mode", "shop"}
    result = "unknown"
    if len(groups) == 1:
        marker = next(iter(groups))
        # Match Found may be drawn over the final summary/results header.
        if marker == "match_found" or "victory_header" not in hits:
            result = {"hero_mode": "hero_selection", "map_title": "map_loading",
                      "shop": "blessing_shop"}.get(marker, marker)
    elif not groups and "victory_header" in hits:
        if {"acquired", "summary"} <= hits:
            result = "unknown"
        elif "acquired" in hits:
            result = "progression"
        elif "summary" in hits:
            result = "final_summary"
        else:
            result = "results"
    return ScreenObservation(result, tuple(sorted(hits)))


def _crop(frame, name):
    if frame.shape != (1080, 1920, 3) or frame.dtype != np.uint8:
        raise ValueError("Expected a 1920x1080 uint8 BGR video frame")
    _, (x0, y0, x1, y1) = MARKERS[name]
    return cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)


class PostMatchDetector:
    def __init__(self, templates, threshold=0.85):
        if not 0 < threshold <= 1 or set(templates) != set(MARKERS):
            raise ValueError("Invalid threshold or incomplete reference templates")
        self.threshold = threshold
        self.templates = {}
        for name, template in templates.items():
            _, (x0, y0, x1, y1) = MARKERS[name]
            if (template.shape != (y1-y0, x1-x0) or template.dtype != np.uint8
                    or float(template.std()) < 8):
                raise ValueError(f"Invalid reference template: {name}")
            self.templates[name] = template.copy()

    @classmethod
    def from_recording(cls, video: Path, threshold=0.85):
        if not Path(video).is_file():
            raise ValueError("Reference must be a local recorded video file")
        cap = cv2.VideoCapture(str(video))
        try:
            if not cap.isOpened():
                raise ValueError("Cannot open reference recording")
            templates = {}
            for name, (seconds, _) in MARKERS.items():
                if not cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000):
                    raise ValueError(f"Cannot seek reference for {name}")
                ok, frame = cap.read()
                if not ok:
                    raise ValueError(f"Cannot read reference for {name}")
                templates[name] = _crop(frame, name)
            return cls(templates, threshold)
        finally:
            cap.release()

    def scores(self, frame):
        scores = {}
        for name, template in self.templates.items():
            patch = _crop(frame, name)
            score = float(cv2.matchTemplate(patch, template, cv2.TM_CCOEFF_NORMED)[0, 0])
            scores[name] = max(-1., min(1., score)) if np.isfinite(score) else -1.
        return scores

    def classify(self, frame):
        return classify_scores(self.scores(frame), self.threshold)
