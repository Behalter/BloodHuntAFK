"""Offline score-rule and image-crop tests; no game or reference video required."""
import unittest
from pathlib import Path
import numpy as np
from scripts.post_match_detector import MARKERS, PostMatchDetector, classify_scores


def scores(*hits):
    return {name: 0.95 if name in hits else 0.1 for name in MARKERS}


class ScreenRulesTests(unittest.TestCase):
    def test_distinct_markers(self):
        for marker, screen in (("victory_banner", "victory_banner"),
                               ("mvp", "mvp"), ("hero_mode", "hero_selection"),
                               ("map_title", "map_loading"), ("shop", "blessing_shop"),
                               ("match_found", "match_found")):
            with self.subTest(marker=marker):
                self.assertEqual(classify_scores(scores(marker)).screen, screen)

    def test_generic_results(self):
        self.assertEqual(classify_scores(scores("victory_header")).screen, "results")

    def test_progression(self):
        self.assertEqual(classify_scores(scores("victory_header", "acquired")).screen,
                         "progression")

    def test_final_summary(self):
        self.assertEqual(classify_scores(scores("victory_header", "summary")).screen,
                         "final_summary")

    def test_shared_back_prompt_is_not_summary(self):
        self.assertEqual(classify_scores(scores("summary")).screen, "unknown")
        self.assertEqual(classify_scores(scores("shop", "summary")).screen, "blessing_shop")

    def test_acquired_without_header_is_unknown(self):
        self.assertEqual(classify_scores(scores("acquired")).screen, "unknown")

    def test_match_found_over_results(self):
        self.assertEqual(classify_scores(scores("match_found", "victory_header", "summary")).screen,
                         "match_found")

    def test_conflicting_markers_are_unknown(self):
        for hits in (("mvp", "shop"), ("hero_mode", "victory_header"),
                     ("victory_header", "summary", "acquired"), ("match_found", "shop")):
            with self.subTest(hits=hits):
                self.assertEqual(classify_scores(scores(*hits)).screen, "unknown")

    def test_below_threshold_is_unknown(self):
        s = scores()
        s["mvp"] = 0.849
        self.assertEqual(classify_scores(s).screen, "unknown")
        s["mvp"] = 0.85
        self.assertEqual(classify_scores(s).screen, "mvp")

    def test_invalid_scores_are_unknown(self):
        for invalid in (float("nan"), float("inf"), 1.01, -1.01):
            s = scores("mvp")
            s["shop"] = invalid
            self.assertEqual(classify_scores(s).screen, "unknown")
        self.assertEqual(classify_scores({}).screen, "unknown")

    def test_invalid_threshold(self):
        for threshold in (0, -1, 1.1, float("nan")):
            with self.assertRaises(ValueError):
                classify_scores(scores(), threshold)


class ImageFixtureTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.templates = {name: rng.integers(0, 256, (y1-y0, x1-x0), dtype=np.uint8)
                          for name, (_, (x0, y0, x1, y1)) in MARKERS.items()}
        self.detector = PostMatchDetector(self.templates)

    def test_matching_shop_crop(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        _, (x0, y0, x1, y1) = MARKERS["shop"]
        frame[y0:y1, x0:x1] = self.templates["shop"][:, :, None]
        self.assertEqual(self.detector.classify(frame).screen, "blessing_shop")

    def test_final_summary_requires_distinctive_crop(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        _, (x0, y0, x1, y1) = MARKERS["victory_header"]
        frame[y0:y1, x0:x1] = self.templates["victory_header"][:, :, None]
        # A populated legacy navigation crop must not identify final summary.
        rng = np.random.default_rng(7)
        frame[1028:1065, 1780:1910] = rng.integers(0, 256, (37, 130, 1), dtype=np.uint8)
        self.assertEqual(self.detector.classify(frame).screen, "results")
        _, (x0, y0, x1, y1) = MARKERS["summary"]
        frame[y0:y1, x0:x1] = self.templates["summary"][:, :, None]
        self.assertEqual(self.detector.classify(frame).screen, "final_summary")

    def test_blank_frame_unknown(self):
        self.assertEqual(self.detector.classify(np.zeros((1080, 1920, 3), dtype=np.uint8)).screen,
                         "unknown")

    def test_wrong_resolution_rejected(self):
        with self.assertRaises(ValueError):
            self.detector.classify(np.zeros((720, 1280, 3), dtype=np.uint8))

    def test_constant_template_rejected(self):
        self.templates["shop"].fill(0)
        with self.assertRaises(ValueError):
            PostMatchDetector(self.templates)

    def test_incomplete_templates_rejected(self):
        del self.templates["shop"]
        with self.assertRaises(ValueError):
            PostMatchDetector(self.templates)

    def test_missing_reference_rejected(self):
        with self.assertRaises(ValueError):
            PostMatchDetector.from_recording(Path("nonexistent_reference.mp4"))


if __name__ == "__main__":
    unittest.main()
