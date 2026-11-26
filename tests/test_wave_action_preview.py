"""Pure preview planner tests. Never import Windows input or run the bot."""
import unittest

from bloodhunt.wave_state import Phase, Rune
from scripts.analyze_video import Detection
from scripts.shadow_monitor import ShadowEvent, ShadowSample
from scripts.wave_action_preview import PREVIEW_FIELDS, WaveActionPreview


def sample(t, phase, rune, suggestion=None, detected_phase=None):
    detection = Detection(detected_phase or phase, rune, 0, 0, 0)
    events = (() if suggestion is None else
              (ShadowEvent(t, "suggestion", phase.value, rune.value, suggestion),))
    return ShadowSample(t, detection, phase, events)


class WaveActionPreviewTests(unittest.TestCase):
    def test_confirmed_active_preparation_emits_exactly_one_cancel(self):
        p = WaveActionPreview()
        self.assertEqual(p.observe(sample(0, Phase.PREPARATION, Rune.ACTIVE,
                                          "consider_cancel_rune")), ())
        events = p.observe(sample(.5, Phase.PREPARATION, Rune.ACTIVE))
        self.assertEqual([e.intent for e in events], ["cancel"])
        self.assertEqual(events[0].csv_row()["would_press"],
                         "F (one tap; NOT SENT)")
        self.assertEqual(tuple(events[0].csv_row()), PREVIEW_FIELDS)
        for i in range(2, 20):
            self.assertEqual(p.observe(sample(i / 2, Phase.PREPARATION,
                                              Rune.ACTIVE)), ())

    def test_ready_combat_only_activates_after_stability(self):
        p = WaveActionPreview()
        self.assertEqual(p.observe(sample(0, Phase.COMBAT, Rune.READY,
                                          "consider_activate_rune")), ())
        self.assertEqual([e.intent for e in
                          p.observe(sample(.5, Phase.COMBAT, Rune.READY))],
                         ["activate"])

    def test_changed_or_unknown_rune_cancels_pending_intent(self):
        p = WaveActionPreview()
        p.observe(sample(0, Phase.PREPARATION, Rune.ACTIVE,
                         "consider_cancel_rune"))
        self.assertEqual(p.observe(sample(.5, Phase.PREPARATION,
                                          Rune.COOLDOWN)), ())
        self.assertEqual(p.observe(sample(1, Phase.PREPARATION,
                                          Rune.ACTIVE)), ())
        self.assertEqual(p.observe(sample(1.5, Phase.PREPARATION,
                                          Rune.UNKNOWN)), ())
        self.assertEqual(p.observe(sample(2, Phase.PREPARATION,
                                          Rune.ACTIVE)), ())

    def test_raw_phase_must_match_confirmed_phase(self):
        p = WaveActionPreview()
        p.observe(sample(0, Phase.PREPARATION, Rune.ACTIVE,
                         "consider_cancel_rune", detected_phase=Phase.UNKNOWN))
        self.assertEqual(p.observe(sample(.5, Phase.PREPARATION,
                                          Rune.ACTIVE)), ())

    def test_gap_blocks_stale_actions_until_new_confirmed_phase(self):
        p = WaveActionPreview()
        p.observe(sample(0, Phase.PREPARATION, Rune.ACTIVE,
                         "consider_cancel_rune"))
        self.assertEqual(p.observe(sample(5, Phase.PREPARATION,
                                          Rune.ACTIVE)), ())
        self.assertEqual(p.observe(sample(5.5, Phase.PREPARATION,
                                          Rune.ACTIVE,
                                          "consider_cancel_rune")), ())
        self.assertEqual(p.observe(sample(6, Phase.COMBAT, Rune.READY,
                                          "consider_activate_rune")), ())
        self.assertEqual([e.intent for e in p.observe(
            sample(6.5, Phase.COMBAT, Rune.READY))], ["activate"])

    def test_no_preview_after_match_ending(self):
        p = WaveActionPreview()
        p.observe(sample(0, Phase.MATCH_ENDING, Rune.UNKNOWN))
        p.observe(sample(.5, Phase.COMBAT, Rune.READY,
                         "consider_activate_rune"))
        self.assertEqual(p.observe(sample(1, Phase.COMBAT, Rune.READY)), ())
        p.observe(sample(1.5, Phase.POST_MATCH, Rune.UNKNOWN))
        p.observe(sample(2, Phase.COMBAT, Rune.READY,
                         "consider_activate_rune"))
        self.assertEqual([e.intent for e in p.observe(
            sample(2.5, Phase.COMBAT, Rune.READY))], ["activate"])

    def test_reject_backwards_time(self):
        p = WaveActionPreview()
        p.observe(sample(4, Phase.UNKNOWN, Rune.UNKNOWN))
        with self.assertRaises(ValueError):
            p.observe(sample(3, Phase.UNKNOWN, Rune.UNKNOWN))

    def test_preparation_confirmation_reuses_raw_streak(self):
        p = WaveActionPreview()
        self.assertEqual(p.observe(sample(0, Phase.COMBAT, Rune.ACTIVE,
                                          detected_phase=Phase.PREPARATION)), ())
        self.assertEqual([e.intent for e in p.observe(sample(
            .5, Phase.PREPARATION, Rune.ACTIVE, "consider_cancel_rune"))],
            ["cancel"])
        self.assertEqual(p.observe(sample(1, Phase.PREPARATION, Rune.UNKNOWN)), ())

    def test_combat_confirmation_reuses_raw_streak(self):
        p = WaveActionPreview()
        self.assertEqual(p.observe(sample(0, Phase.PREPARATION, Rune.READY,
                                          detected_phase=Phase.COMBAT)), ())
        self.assertEqual([e.intent for e in p.observe(sample(
            .5, Phase.COMBAT, Rune.READY, "consider_activate_rune"))],
            ["activate"])

    def test_cooldown_permanently_discards_pending_cancel(self):
        p = WaveActionPreview()
        self.assertEqual(p.observe(sample(0, Phase.PREPARATION, Rune.ACTIVE,
                                          "consider_cancel_rune")), ())
        for t, rune in ((.5, Rune.COOLDOWN), (1, Rune.ACTIVE),
                        (1.5, Rune.ACTIVE), (2, Rune.ACTIVE)):
            self.assertEqual(p.observe(sample(t, Phase.PREPARATION, rune)), ())

    def test_bad_configuration(self):
        with self.assertRaises(ValueError):
            WaveActionPreview(stable_samples=1)
        with self.assertRaises(ValueError):
            WaveActionPreview(max_gap_seconds=0)


if __name__ == "__main__":
    unittest.main()
