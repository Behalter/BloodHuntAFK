"""Offline-only detector tests; no game, accounts, or input permissions."""
import unittest
import cv2
import numpy as np

from bloodhunt.wave_state import Rune
from scripts.analyze_video import F_GLYPH, classify_rune, light_text, match_score, normalize


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
        cv2.putText(white, 'INCOMING', (2, 25), cv2.FONT_HERSHEY_SIMPLEX,
                    .45, (240, 240, 240), 1)
        cv2.putText(yellow, 'INCOMING', (2, 25), cv2.FONT_HERSHEY_SIMPLEX,
                    .45, (25, 180, 225), 1)
        np.testing.assert_array_equal(light_text(white), light_text(yellow))
        self.assertGreater(match_score(white, light_text(white), (0, 0, 100, 30)), .99)

    def test_other_aspect_ratio_is_not_silently_scaled(self):
        with self.assertRaises(ValueError):
            normalize(np.zeros((100, 100, 3), dtype=np.uint8))


if __name__ == '__main__':
    unittest.main()
