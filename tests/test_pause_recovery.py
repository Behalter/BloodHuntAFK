import unittest
from scripts.pause_recovery import ResumeGate, pending_reconciled


class PauseRecoveryTests(unittest.TestCase):
    def test_same_combat_ready(self):
        gate = ResumeGate()
        self.assertEqual([gate.observe("combat", "ready") for _ in range(3)], [False, False, True])

    def test_same_preparation_active(self):
        gate = ResumeGate()
        self.assertEqual([gate.observe("preparation", "active") for _ in range(3)], [False, False, True])

    def test_unknown_breaks_streak(self):
        gate = ResumeGate()
        for phase, rune in [("combat", "ready"), ("combat", "ready"), ("unknown", "unknown"), ("combat", "ready"), ("combat", "ready")]:
            self.assertFalse(gate.observe(phase, rune))
        self.assertTrue(gate.observe("combat", "ready"))

    def test_rune_change_breaks_streak(self):
        gate = ResumeGate()
        self.assertFalse(gate.observe("combat", "cooldown"))
        self.assertFalse(gate.observe("combat", "cooldown"))
        self.assertFalse(gate.observe("combat", "ready"))
        self.assertFalse(gate.observe("combat", "ready"))
        self.assertTrue(gate.observe("combat", "ready"))

    def test_phase_change_breaks_streak(self):
        gate = ResumeGate()
        self.assertFalse(gate.observe("combat", "ready"))
        self.assertFalse(gate.observe("combat", "ready"))
        self.assertFalse(gate.observe("preparation", "ready"))
        self.assertFalse(gate.observe("preparation", "ready"))
        self.assertTrue(gate.observe("preparation", "ready"))

    def test_active_and_cooldown_are_valid_recovery_states(self):
        for rune in ("active", "cooldown"):
            gate = ResumeGate()
            self.assertEqual([gate.observe("combat", rune) for _ in range(3)], [False, False, True])

    def test_results_never_rearm_gameplay(self):
        gate = ResumeGate()
        for _ in range(5):
            self.assertFalse(gate.observe("final_summary", "ready"))

    def test_pending_activation(self):
        self.assertTrue(pending_reconciled("combat", "active", "combat", {"active"}))
        self.assertFalse(pending_reconciled("combat", "ready", "combat", {"active"}))
        self.assertFalse(pending_reconciled("preparation", "active", "combat", {"active"}))

    def test_pending_cancel(self):
        for rune in ("cooldown", "ready"):
            self.assertTrue(pending_reconciled("preparation", rune, "preparation", {"cooldown", "ready"}))
        self.assertFalse(pending_reconciled("preparation", "active", "preparation", {"cooldown", "ready"}))


if __name__ == "__main__":
    unittest.main()
