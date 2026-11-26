"""Regression tests for the shadow path: fake frames, NO Windows/game inputs."""
import unittest

from bloodhunt.wave_state import Phase, Rune
from scripts.analyze_video import Detection
from scripts.shadow_monitor import ShadowMonitor, EVENT_FIELDS, SAMPLE_FIELDS


def reading(phase, rune):
    return Detection(phase, rune, 0.0, 0.0, 0.0)


class ShadowMonitorTests(unittest.TestCase):
    def test_monitor_debounces_and_emits_one_shot_suggestions(self):
        def detector(frame, _calibration):
            return frame

        monitor = ShadowMonitor(None, detector=detector)
        observations = [
            reading(Phase.PREPARATION, Rune.ACTIVE),
            reading(Phase.PREPARATION, Rune.ACTIVE),
            reading(Phase.PREPARATION, Rune.ACTIVE),
            reading(Phase.COMBAT, Rune.READY),
            reading(Phase.COMBAT, Rune.READY),
            reading(Phase.COMBAT, Rune.READY),
            reading(Phase.MATCH_ENDING, Rune.ACTIVE),
            reading(Phase.MATCH_ENDING, Rune.ACTIVE),
            reading(Phase.POST_MATCH, Rune.UNKNOWN),
            reading(Phase.POST_MATCH, Rune.UNKNOWN),
        ]
        result = [monitor.feed(i, d) for i, d in enumerate(observations)]
        recommendations = [(i, e.details) for i, sample in enumerate(result)
                           for e in sample.events if e.kind == "suggestion"]
        self.assertEqual(recommendations, [
            (1, "consider_cancel_rune"),
            (4, "consider_activate_rune"),
            (9, "match_complete"),
        ])
        self.assertTrue(all(set(sample.csv_row()) == set(SAMPLE_FIELDS)
                            for sample in result))
        self.assertTrue(all(set(e.csv_row()) == set(EVENT_FIELDS)
                            for sample in result for e in sample.events))

    def test_unknown_frames_do_not_trigger_rune_press(self):
        m = ShadowMonitor(None, detector=lambda f, _: f)
        for time, observed in enumerate((
            reading(Phase.UNKNOWN, Rune.UNKNOWN),
            reading(Phase.COMBAT, Rune.UNKNOWN),
            reading(Phase.COMBAT, Rune.UNKNOWN),
            reading(Phase.UNKNOWN, Rune.UNKNOWN),
            reading(Phase.PREPARATION, Rune.UNKNOWN),
            reading(Phase.PREPARATION, Rune.UNKNOWN),
        )):
            sample = m.feed(time, observed)
            self.assertFalse(any(e.kind == "suggestion" for e in sample.events))

    def test_reject_out_of_order_samples(self):
        m = ShadowMonitor(None, detector=lambda f, _: f)
        m.feed(3.0, reading(Phase.UNKNOWN, Rune.UNKNOWN))
        with self.assertRaises(ValueError):
            m.feed(2.0, reading(Phase.UNKNOWN, Rune.UNKNOWN))


if __name__ == "__main__":
    unittest.main()
