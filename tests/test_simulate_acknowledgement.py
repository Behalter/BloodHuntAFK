"""Synthetic-only tests; no game, screen capture, or input devices."""
import unittest

from scripts.simulate_acknowledgement import (
    AcknowledgementSimulation, Frame, Proposal,
)


def frame(t, rune="ready", phase="combat", *, raw=None, focused=True, stop=False):
    return Frame(t, phase if raw is None else raw, phase, rune, focused, stop)


def statuses(events):
    return [e.status for e in events]


class AcknowledgementSimulationTests(unittest.TestCase):
    def setUp(self):
        self.sim = AcknowledgementSimulation()

    def start(self):
        self.assertEqual(statuses(self.sim.observe(frame(0), Proposal("activate"))),
                         ["simulated"])

    def test_activation_acknowledged(self):
        self.start()
        self.assertEqual(self.sim.observe(frame(.5, "active")), ())
        self.assertEqual(statuses(self.sim.observe(frame(1, "active"))),
                         ["acknowledged"])
        self.assertEqual(self.sim.observe(frame(1.5, "active")), ())

    def test_cancellation_acknowledged(self):
        self.assertEqual(statuses(self.sim.observe(
            frame(0, "active", "preparation"), Proposal("cancel"))), ["simulated"])
        self.assertEqual(self.sim.observe(frame(.5, "cooldown", "preparation")), ())
        self.assertEqual(statuses(self.sim.observe(frame(1, "ready", "preparation"))),
                         ["acknowledged"])

    def test_unchanged_state_times_out_without_retry(self):
        self.start()
        for t in (.5, 1, 1.5, 2, 2.5):
            self.assertEqual(self.sim.observe(frame(t)), ())
        self.assertEqual(statuses(self.sim.observe(frame(3))), ["timeout"])
        self.assertEqual(statuses(self.sim.observe(frame(3.5), Proposal("activate"))),
                         ["rejected"])

    def test_unknown_breaks_acknowledgement_streak(self):
        self.start()
        self.assertEqual(self.sim.observe(frame(.5, "active")), ())
        self.assertEqual(self.sim.observe(frame(1, "unknown")), ())
        self.assertEqual(self.sim.observe(frame(1.5, "active")), ())
        self.assertEqual(statuses(self.sim.observe(frame(2, "active"))),
                         ["acknowledged"])

    def test_unknown_phase_cannot_acknowledge(self):
        self.start()
        for t in (.5, 1, 1.5, 2, 2.5):
            self.assertEqual(self.sim.observe(frame(t, "active", raw="unknown")), ())
        self.assertEqual(statuses(self.sim.observe(frame(3, "active", raw="unknown"))),
                         ["timeout"])

    def test_focus_loss_aborts(self):
        self.start()
        self.assertEqual(statuses(self.sim.observe(frame(.5, "active", focused=False))),
                         ["aborted"])
        self.assertEqual(self.sim.observe(frame(1, "active")), ())
        self.assertEqual(statuses(self.sim.observe(frame(1.5), Proposal("activate"))),
                         ["rejected"])

    def test_gap_aborts(self):
        self.start()
        self.assertEqual(statuses(self.sim.observe(frame(2.6, "active"))), ["aborted"])
        self.assertEqual(self.sim.observe(frame(3, "active")), ())

    def test_raw_phase_change_aborts_before_confirmation(self):
        self.start()
        self.assertEqual(statuses(self.sim.observe(
            frame(.5, "active", raw="preparation"))), ["aborted"])

    def test_raw_ending_permanently_stops(self):
        self.start()
        self.assertEqual(statuses(self.sim.observe(
            frame(.5, "unknown", raw="match_ending"))), ["aborted"])
        self.assertEqual(statuses(self.sim.observe(frame(1), Proposal("activate"))),
                         ["rejected"])

    def test_emergency_stop_is_permanent(self):
        self.start()
        self.assertEqual(statuses(self.sim.observe(frame(.5, stop=True))), ["aborted"])
        self.assertEqual(statuses(self.sim.observe(
            frame(1, "active", "preparation"), Proposal("cancel"))), ["rejected"])

    def test_delivery_failure_is_not_retried(self):
        self.assertEqual(statuses(self.sim.observe(
            frame(0), Proposal("activate", False))), ["delivery_failed"])
        self.assertEqual(statuses(self.sim.observe(frame(.5), Proposal("activate"))),
                         ["rejected"])

    def test_contradictory_state_is_not_acknowledged(self):
        self.start()
        self.assertEqual(statuses(self.sim.observe(frame(.5, "cooldown"))), ["unexpected"])
        self.assertEqual(self.sim.observe(frame(1, "active")), ())

    def test_mismatched_proposal_rejected(self):
        self.assertEqual(statuses(self.sim.observe(
            frame(0, "unknown"), Proposal("activate"))), ["rejected"])
        self.assertEqual(statuses(self.sim.observe(
            frame(.5, raw="unknown"), Proposal("activate"))), ["rejected"])

    def test_overlapping_proposal_rejected(self):
        self.start()
        self.assertEqual(statuses(self.sim.observe(
            frame(.5, "active"), Proposal("activate"))), ["rejected"])
        self.assertEqual(statuses(self.sim.observe(frame(1, "active"))),
                         ["acknowledged"])

    def test_late_acknowledgement_rejected(self):
        self.start()
        self.assertEqual(self.sim.observe(frame(2.5, "active")), ())
        self.assertEqual(statuses(self.sim.observe(frame(3.1, "active"))), ["timeout"])

    def test_invalid_timing_rejected(self):
        for value in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                AcknowledgementSimulation(timeout_seconds=value)
        self.start()
        for value in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.sim.observe(frame(value))


if __name__ == "__main__":
    unittest.main()
