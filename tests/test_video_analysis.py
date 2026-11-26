"""Offline-only detector tests; no game, accounts, or input permissions."""
import unittest
import cv2
import numpy as np

from bloodhunt.wave_state import Rune
from scripts.analyze_video import (F_GLYPH, BOSS_BAR_AREA, BOSS_OBJECTIVE_SEARCH,
    PHASE_HEADER_GLYPH, PHASE_HEADER_SEARCH,
    MATCH_ENDING_SEARCH, Calibration, classify_rune, light_text, match_score,
    normalize, boss_health_bar_run, detect)
from bloodhunt.wave_state import Phase


class VideoDetectorTests(unittest.TestCase):
    def make_frame(self, color):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        x0, y0, x1, y1 = F_GLYPH
        frame[y0 + 12:y1 - 12, x0 + 15:x1 - 15] = color
        mask = np.zeros((y1 - y0, x1 - x0), dtype=np.bool_)
        mask[12:-12, 15:-15] = True
        return frame, mask

    def test_f_white_ready(self):
        frame, mask = self.make_frame((230, 230, 230))
        self.assertIs(classify_rune(frame, mask), Rune.READY)

    def test_f_gold_active(self):
        frame, mask = self.make_frame((20, 190, 230))
        self.assertIs(classify_rune(frame, mask), Rune.ACTIVE)

    def test_f_red_cooldown(self):
        frame, mask = self.make_frame((25, 48, 112))
        self.assertIs(classify_rune(frame, mask), Rune.COOLDOWN)

    def test_uncertain_icon_is_unknown(self):
        frame, mask = self.make_frame((32, 32, 32))
        self.assertIs(classify_rune(frame, mask), Rune.UNKNOWN)

    def test_yellow_and_white_text_have_similar_masks(self):
        white = np.zeros((30, 100, 3), dtype=np.uint8)
        yellow = np.zeros_like(white)
        # Use a sufficiently substantial text mask (>8% foreground).
        # Tiny, single-stroke masks are intentionally rejected by match_score.
        cv2.putText(white, 'INCOMING', (2, 25), cv2.FONT_HERSHEY_SIMPLEX,
                    .45, (240, 240, 240), 2)
        cv2.putText(yellow, 'INCOMING', (2, 25), cv2.FONT_HERSHEY_SIMPLEX,
                    .45, (25, 180, 225), 2)
        # Anti-aliasing at colored text edges can cross the brightness cutoff;
        # require near-equivalence rather than pixel-perfect binary equality.
        white_mask, yellow_mask = light_text(white), light_text(yellow)
        disagreement = np.count_nonzero(white_mask != yellow_mask) / white_mask.size
        self.assertLess(disagreement, 0.01)
        self.assertGreater(match_score(white, white_mask, (0, 0, 100, 30)), .99)

    def test_boss_bar_requires_long_orange_segment(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        x0, y0, x1, y1 = BOSS_BAR_AREA
        frame[y0 + 8:y0 + 14, x0 + 30:x0 + 420] = (20, 115, 170)
        self.assertGreaterEqual(boss_health_bar_run(frame), 350)
        frame[y0 + 8:y0 + 14, x0 + 30:x0 + 420] = (255, 255, 255)
        self.assertEqual(boss_health_bar_run(frame), 0)

    def test_boss_phase_requires_objective_as_well_as_bar(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        x0, y0, x1, y1 = BOSS_BAR_AREA
        frame[y0 + 8:y0 + 14, x0 + 30:x0 + 420] = (20, 115, 170)
        blank = np.zeros((8, 12), np.uint8)
        blank[3, 4] = 255  # nonconstant: OpenCV constant templates match everywhere
        objective = np.zeros((15, 45), np.uint8)
        cv2.putText(objective, "BOSS", (1, 12),
                    cv2.FONT_HERSHEY_SIMPLEX, .35, 255, 1)
        calibration = Calibration(blank, blank, blank, objective, blank,
                                  np.ones((F_GLYPH[3]-F_GLYPH[1],
                                           F_GLYPH[2]-F_GLYPH[0]), dtype=bool))
        self.assertIs(detect(frame, calibration).phase, Phase.UNKNOWN)
        # Paste the *same* binary glyph as white BGR pixels. This tests the
        # detector itself, without relying on separate OpenCV text-rasterization
        # calls having identical alignment across OpenCV versions.
        paste_x = BOSS_OBJECTIVE_SEARCH[0] + 4
        paste_y = BOSS_OBJECTIVE_SEARCH[1] + 5
        patch = frame[paste_y:paste_y + objective.shape[0],
                      paste_x:paste_x + objective.shape[1]]
        patch[objective > 0] = (255, 255, 255)
        objective_score = match_score(frame, objective, BOSS_OBJECTIVE_SEARCH)
        self.assertGreater(objective_score, 0.90, f"objective score={objective_score}")
        self.assertGreaterEqual(boss_health_bar_run(frame), 180)
        self.assertIs(detect(frame, calibration).phase, Phase.COMBAT)

    def test_ending_overlay_blocks_combat(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        x0, y0, _, _ = MATCH_ENDING_SEARCH
        phrase = np.zeros((15, 80), np.uint8)
        cv2.putText(phrase, "ENDING", (2, 12),
                    cv2.FONT_HERSHEY_SIMPLEX, .33, 255, 1)
        cv2.putText(frame, "ENDING", (x0 + 2, y0 + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, .33, (255, 255, 255), 1)
        blank = np.zeros((8, 12), np.uint8)
        blank[3, 4] = 255  # nonconstant: OpenCV constant templates match everywhere
        calibration = Calibration(blank, blank, blank, blank, phrase,
                                  np.ones((F_GLYPH[3]-F_GLYPH[1],
                                           F_GLYPH[2]-F_GLYPH[0]), dtype=bool))
        self.assertIs(detect(frame, calibration).phase, Phase.MATCH_ENDING)

    def test_generic_phase_header_with_visible_rune_detects_combat(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        x0, y0, x1, y1 = PHASE_HEADER_GLYPH
        frame[y0+3:y1-3, x0+5:x1-5] = (240, 240, 240)
        fx0, fy0, fx1, fy1 = F_GLYPH
        frame[fy0:fy1, fx0:fx1] = (240, 240, 240)
        blank = np.zeros((8, 12), dtype=np.uint8)
        blank[3, 4] = 255
        phase = np.zeros((y1-y0, x1-x0), dtype=np.uint8)
        phase[3:-3, 5:-5] = 255
        f_mask = np.ones((fy1-fy0, fx1-fx0), dtype=bool)
        calibration = Calibration(blank, blank, blank, blank, blank,
                                  f_mask, phase)
        self.assertIs(detect(frame, calibration).phase, Phase.COMBAT)
        frame[fy0:fy1, fx0:fx1] = (0, 0, 0)
        self.assertIs(detect(frame, calibration).phase, Phase.UNKNOWN)

    def test_other_aspect_ratio_is_not_silently_scaled(self):
        with self.assertRaises(ValueError):
            normalize(np.zeros((100, 100, 3), dtype=np.uint8))


if __name__ == '__main__':
    unittest.main()
