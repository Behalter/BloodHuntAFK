"""Lossless, versioned wave recognition bundle. Offline export only.

Run once with the two calibrated reference videos. The resulting NPZ
contains only recognition crops/masks, not the full recordings.
No game capture or input is performed by this module.
"""
import argparse
import hashlib
from pathlib import Path

import cv2
import numpy as np

from scripts.analyze_video import (
    Calibration, INCOMING_GLYPH, COMBAT_GLYPH, VICTORY_GLYPH,
    BOSS_OBJECTIVE_GLYPH, MATCH_ENDING_GLYPH, F_GLYPH, PHASE_HEADER_GLYPH,
)
from scripts.post_match_detector import PostMatchDetector, MARKERS

BUNDLE_RELATIVE = Path("profiles") / "16x9" / "wave_templates.npz"
WAVE_BOXES = {
    "incoming": INCOMING_GLYPH,
    "combat": COMBAT_GLYPH,
    "victory": VICTORY_GLYPH,
    "boss_objective": BOSS_OBJECTIVE_GLYPH,
    "ending": MATCH_ENDING_GLYPH,
    "f_glyph": F_GLYPH,
    "phase_header": PHASE_HEADER_GLYPH,
}
HERO_BOXES = {
    "thor": (40, 665, 170, 720),
    "confirm": (1638, 715, 1732, 744),
    "cancel": (1638, 715, 1732, 744),
}
HERO_TIMES = {"thor": 61, "confirm": 61, "cancel": 65}


def shape(box):
    x, y, x2, y2 = box
    return y2 - y, x2 - x


def hero_crop(image, name):
    x, y, x2, y2 = HERO_BOXES[name]
    return cv2.cvtColor(image[y:y2, x:x2], cv2.COLOR_BGR2GRAY)


def from_recordings(wave_reference, screen_reference):
    wave = Calibration.from_video(wave_reference, 55., 80., 285., 56., 255., 260.)
    post = PostMatchDetector.from_recording(screen_reference)
    hero = {}
    cap = cv2.VideoCapture(str(screen_reference))
    try:
        if not cap.isOpened():
            raise ValueError("Cannot open hero reference recording")
        for name, seconds in HERO_TIMES.items():
            if not cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000):
                raise ValueError(f"Cannot seek hero reference: {name}")
            ok, image = cap.read()
            if not ok or image.shape != (1080, 1920, 3):
                raise ValueError(f"Cannot read hero reference: {name}")
            hero[name] = hero_crop(image, name)
    finally:
        cap.release()
    return wave, post, hero


def arrays(wave, post, hero):
    return {
        "schema": np.array(1, dtype=np.uint8),
        **{"wave_" + name: getattr(wave, name) for name in WAVE_BOXES},
        **{"post_" + name: post.templates[name] for name in MARKERS},
        **{"hero_" + name: hero[name] for name in HERO_BOXES},
    }


def load_bundle(path):
    expected = {"schema"} | {"wave_" + n for n in WAVE_BOXES} | {
        "post_" + n for n in MARKERS} | {"hero_" + n for n in HERO_BOXES}
    with np.load(path, allow_pickle=False) as data:
        if set(data.files) != expected or len(data.files) != len(expected):
            raise ValueError("Incomplete or unexpected wave bundle entries")
        version = data["schema"]
        if version.shape != () or version.dtype != np.uint8 or int(version) != 1:
            raise ValueError("Unsupported wave bundle schema")
        masks = {}
        for name, box in WAVE_BOXES.items():
            mask = data["wave_" + name]
            dtype = np.bool_ if name == "f_glyph" else np.uint8
            if (mask.shape != shape(box) or mask.dtype != dtype
                    or not 0.08 < np.count_nonzero(mask) / mask.size < 0.85):
                raise ValueError(f"Invalid wave mask: {name}")
            if name != "f_glyph" and not np.all((mask == 0) | (mask == 255)):
                raise ValueError(f"Nonbinary wave mask: {name}")
            masks[name] = mask.copy()
        post = PostMatchDetector({name: data["post_" + name] for name in MARKERS})
        hero = {}
        for name, box in HERO_BOXES.items():
            patch = data["hero_" + name]
            if patch.shape != shape(box) or patch.dtype != np.uint8 or float(patch.std()) < 8:
                raise ValueError(f"Invalid hero template: {name}")
            hero[name] = patch.copy()
    return Calibration(**masks), post, hero


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wave-reference", type=Path, required=True)
    parser.add_argument("--screen-reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=BUNDLE_RELATIVE)
    args = parser.parse_args()
    if args.output.suffix.lower() != ".npz":
        parser.error("Output must have an .npz extension")
    if args.output.exists():
        parser.error("Output already exists; will not overwrite")
    original = arrays(*from_recordings(args.wave_reference, args.screen_reference))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        try:
            np.savez_compressed(stream, **original)
            stream.flush()
        except Exception:
            stream.close()
            args.output.unlink()
            raise
    try:
        restored = arrays(*load_bundle(args.output))
        for name, value in original.items():
            other = restored[name]
            if value.dtype != other.dtype or not np.array_equal(value, other):
                raise ValueError(f"Lossless round-trip failed: {name}")
    except Exception:
        args.output.unlink()
        raise
    print(f"PASS: {len(original)-1} recognition arrays preserved exactly.")
    print(f"Bundle: {args.output.resolve()}")
    print(f"Bytes: {args.output.stat().st_size}")
    print(f"SHA-256: {hashlib.sha256(args.output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
