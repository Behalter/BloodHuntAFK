"""Synthetic offline tests. No game or input permissions needed."""
import unittest

from bloodhunt.wave_state import Observation, Phase, Rune, Suggestion, WaveAdvisor


def observe(advisor, second, phase, rune=Rune.UNKNOWN):
    return advisor.observe(Observation(second, phase, rune))


class WaveAdvisorTests(unittest.TestCase):
    def test_incoming_banner_is_debounced(self):
        a = WaveAdvisor()
        self.assertEqual(observe(a, 1, Phase.PREPARATION, Rune.ACTIVE).suggestions, ())
        self.assertEqual(observe(a, 2, Phase.PREPARATION, Rune.ACTIVE).suggestions,
                         (Suggestion.CANCEL_RUNE,))
        self.assertEqual(observe(a, 3, Phase.PREPARATION, Rune.ACTIVE).suggestions, ())

    def test_unknown_rune_never_triggers_cancel(self):
        a = WaveAdvisor()
        observe(a, 1, Phase.PREPARATION)
        self.assertEqual(observe(a, 2, Phase.PREPARATION).suggestions, ())
        self.assertEqual(observe(a, 3, Phase.PREPARATION, Rune.ACTIVE).suggestions,
                         (Suggestion.CANCEL_RUNE,))

    def test_banner_absence_alone_does_not_activate(self):
        a = WaveAdvisor()
        observe(a, 1, Phase.PREPARATION, Rune.ACTIVE)
        observe(a, 2, Phase.PREPARATION, Rune.ACTIVE)
        self.assertEqual(observe(a, 3, Phase.UNKNOWN, Rune.READY).suggestions, ())
        self.assertEqual(observe(a, 4, Phase.COMBAT, Rune.READY).suggestions, ())
        self.assertEqual(observe(a, 5, Phase.COMBAT, Rune.READY).suggestions,
                         (Suggestion.ACTIVATE_RUNE,))

    def test_start_activation_is_one_shot(self):
        a = WaveAdvisor()
        observe(a, 1, Phase.COMBAT, Rune.READY)
        self.assertEqual(observe(a, 2, Phase.COMBAT, Rune.READY).suggestions,
                         (Suggestion.ACTIVATE_RUNE,))
        self.assertEqual(observe(a, 3, Phase.COMBAT, Rune.READY).suggestions, ())
        self.assertEqual(observe(a, 80, Phase.COMBAT, Rune.READY).suggestions, ())

    def test_long_wave_extra_requires_prior_active_confirmation(self):
        a = WaveAdvisor(long_wave_seconds=75)
        observe(a, 0, Phase.COMBAT, Rune.READY)
        observe(a, 1, Phase.COMBAT, Rune.READY)
        observe(a, 10, Phase.COMBAT, Rune.ACTIVE)
        self.assertEqual(observe(a, 76, Phase.COMBAT, Rune.COOLDOWN).suggestions, ())
        self.assertEqual(observe(a, 77, Phase.COMBAT, Rune.READY).suggestions,
                         (Suggestion.LONG_WAVE_ACTIVATION,))
        self.assertEqual(observe(a, 100, Phase.COMBAT, Rune.READY).suggestions, ())

    def test_new_preparation_and_combat_rearm(self):
        a = WaveAdvisor()
        observe(a, 0, Phase.COMBAT, Rune.READY)
        observe(a, 1, Phase.COMBAT, Rune.READY)
        observe(a, 2, Phase.PREPARATION, Rune.ACTIVE)
        self.assertEqual(observe(a, 3, Phase.PREPARATION, Rune.ACTIVE).suggestions,
                         (Suggestion.CANCEL_RUNE,))
        observe(a, 4, Phase.COMBAT, Rune.READY)
        self.assertEqual(observe(a, 5, Phase.COMBAT, Rune.READY).suggestions,
                         (Suggestion.ACTIVATE_RUNE,))

    def test_results_suppress_combat_suggestions(self):
        a = WaveAdvisor()
        observe(a, 1, Phase.COMBAT, Rune.READY)
        observe(a, 2, Phase.COMBAT, Rune.READY)
        self.assertEqual(observe(a, 3, Phase.POST_MATCH, Rune.READY).suggestions, ())
        self.assertEqual(observe(a, 4, Phase.POST_MATCH, Rune.READY).suggestions,
                         (Suggestion.MATCH_COMPLETE,))
        self.assertEqual(observe(a, 5, Phase.POST_MATCH, Rune.READY).suggestions, ())

    def test_transient_unknown_does_not_rearm_same_phase(self):
        a = WaveAdvisor()
        observe(a, 1, Phase.COMBAT, Rune.READY)
        observe(a, 2, Phase.COMBAT, Rune.READY)
        observe(a, 3, Phase.UNKNOWN)
        self.assertEqual(observe(a, 4, Phase.COMBAT, Rune.READY).suggestions, ())
        self.assertEqual(observe(a, 5, Phase.COMBAT, Rune.READY).suggestions, ())

    def test_reject_backwards_timestamps(self):
        a = WaveAdvisor()
        observe(a, 3, Phase.COMBAT)
        with self.assertRaises(ValueError):
            observe(a, 2, Phase.COMBAT)

    def test_validate_configuration(self):
        with self.assertRaises(ValueError):
            WaveAdvisor(stable_frames=1)
        with self.assertRaises(ValueError):
            WaveAdvisor(long_wave_seconds=0)

    def test_cooldown_does_not_trigger_activation(self):
        a = WaveAdvisor()
        observe(a, 1, Phase.COMBAT, Rune.COOLDOWN)
        self.assertEqual(observe(a, 2, Phase.COMBAT, Rune.COOLDOWN).suggestions, ())
        self.assertEqual(observe(a, 3, Phase.COMBAT, Rune.READY).suggestions,
                         (Suggestion.ACTIVATE_RUNE,))


if __name__ == '__main__':
    unittest.main()
