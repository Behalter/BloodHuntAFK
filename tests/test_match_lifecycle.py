"""Integration tests with synthetic classifications; no live game or input.

The detector is replaced with an identity function. The real shadow monitor,
advisor, preview planner, and offline acknowledgement simulator run unchanged.
This tests their composition, not pixel recognition or input latency.
"""
import unittest

from bloodhunt.wave_state import Phase, Rune
from scripts.analyze_video import Detection
from scripts.shadow_monitor import ShadowMonitor
from scripts.wave_action_preview import WaveActionPreview
from scripts.simulate_acknowledgement import (
    AcknowledgementSimulation, Frame, Proposal,
)


class MatchFixture:
    def __init__(self):
        self.monitor = ShadowMonitor(None, detector=lambda d, _: d)
        self.preview = WaveActionPreview()
        self.simulation = AcknowledgementSimulation()
        self.seconds = -0.5
        self.samples = []
        self.previews = []
        self.audit = []

    def feed(self, phase, rune=Rune.UNKNOWN, *, delivered=True,
             focused=True, stop=False):
        self.seconds += 0.5
        sample = self.monitor.feed(self.seconds, Detection(phase, rune, 0, 0, 0))
        previews = self.preview.observe(sample)
        if len(previews) > 1:
            raise AssertionError("More than one preview on a synthetic frame")
        proposal = Proposal(previews[0].intent, delivered) if previews else None
        audit = self.simulation.observe(
            Frame(self.seconds, phase.value, sample.confirmed_phase.value,
                  rune.value, focused=focused, stop=stop), proposal)
        self.samples.append(sample)
        self.previews.extend(previews)
        self.audit.extend(audit)
        return audit

    def repeat(self, phase, rune=Rune.UNKNOWN, count=2):
        for _ in range(count):
            self.feed(phase, rune)

    def first_combat(self, *, delivered=True, acknowledge=True):
        self.repeat(Phase.PREPARATION, Rune.READY)
        self.feed(Phase.COMBAT, Rune.READY)
        self.feed(Phase.COMBAT, Rune.READY, delivered=delivered)
        if acknowledge:
            self.repeat(Phase.COMBAT, Rune.ACTIVE)

    def next_combat(self, *, acknowledge=True):
        self.repeat(Phase.PREPARATION, Rune.ACTIVE)
        self.repeat(Phase.PREPARATION, Rune.COOLDOWN)
        self.repeat(Phase.PREPARATION, Rune.READY)
        self.repeat(Phase.COMBAT, Rune.READY)
        if acknowledge:
            self.repeat(Phase.COMBAT, Rune.ACTIVE)

    def finish_match(self):
        self.repeat(Phase.MATCH_ENDING)
        self.repeat(Phase.UNKNOWN, count=4)  # unclassified cinematic/MVP interval
        self.repeat(Phase.POST_MATCH, count=6)

    def intents(self):
        return [e.intent for e in self.previews]

    def statuses(self, status):
        return [e for e in self.audit if e.status == status]

    def suggestions(self):
        return [e.details for s in self.samples for e in s.events
                if e.kind == "suggestion"]

    def phases(self):
        return [e.phase for s in self.samples for e in s.events
                if e.kind == "phase"]


class MatchLifecycleTests(unittest.TestCase):
    def test_complete_five_combat_match(self):
        f = MatchFixture()
        f.repeat(Phase.UNKNOWN, count=6)
        self.assertEqual(f.previews, [])
        f.first_combat()
        for _ in range(4):
            f.next_combat()
        f.finish_match()
        expected = ["activate"] + ["cancel", "activate"] * 4
        self.assertEqual(f.intents(), expected)
        self.assertEqual(f.phases(), ["preparation", "combat"] * 5
                         + ["match_ending", "post_match"])
        self.assertEqual([e.intent for e in f.statuses("simulated")], expected)
        self.assertEqual([e.intent for e in f.statuses("acknowledged")], expected)
        self.assertEqual(len(f.audit), 18)
        self.assertEqual(f.suggestions().count("match_complete"), 1)
        self.assertEqual(len(f.previews), 9)

    def test_boss_ending_interrupts_pending_acknowledgement(self):
        f = MatchFixture()
        f.first_combat()
        for _ in range(3):
            f.next_combat()
        f.next_combat(acknowledge=False)
        f.feed(Phase.COMBAT, Rune.ACTIVE)  # only one positive sample
        f.finish_match()
        self.assertEqual(len(f.previews), 9)
        self.assertEqual(len(f.statuses("acknowledged")), 8)
        self.assertEqual([e.intent for e in f.statuses("aborted")], ["activate"])
        self.assertEqual(f.statuses("timeout"), [])
        self.assertEqual(f.suggestions().count("match_complete"), 1)

    def test_delivery_failure_does_not_repeat_same_intent(self):
        f = MatchFixture()
        f.first_combat(delivered=False, acknowledge=False)
        f.repeat(Phase.COMBAT, Rune.READY, count=8)
        self.assertEqual(f.intents(), ["activate"])
        self.assertEqual([e.intent for e in f.statuses("delivery_failed")],
                         ["activate"])
        self.assertEqual(f.statuses("acknowledged"), [])
        f.repeat(Phase.COMBAT, Rune.ACTIVE)  # manual/synthetic state change
        f.next_combat()
        self.assertEqual(f.intents(), ["activate", "cancel", "activate"])
        self.assertEqual([e.intent for e in f.statuses("acknowledged")],
                         ["cancel", "activate"])

    def test_extended_combat_extra_preview_is_one_shot(self):
        f = MatchFixture()
        f.first_combat()
        # Early READY observations must not produce the long-wave suggestion.
        f.repeat(Phase.COMBAT, Rune.READY, count=4)
        self.assertEqual(f.intents(), ["activate"])
        # Default advisor threshold is 75s from confirmed combat.
        f.repeat(Phase.COMBAT, Rune.COOLDOWN, count=150)
        self.assertEqual(f.intents(), ["activate"])
        f.repeat(Phase.COMBAT, Rune.READY)
        self.assertEqual(f.intents(), ["activate", "long_wave_activate"])
        f.repeat(Phase.COMBAT, Rune.ACTIVE)
        f.repeat(Phase.COMBAT, Rune.READY, count=10)
        self.assertEqual(f.intents(), ["activate", "long_wave_activate"])
        self.assertEqual([e.intent for e in f.statuses("acknowledged")],
                         ["activate", "long_wave_activate"])

    def test_unknown_hud_does_not_rearm_completed_intent(self):
        f = MatchFixture()
        f.first_combat()
        f.repeat(Phase.UNKNOWN, count=4)
        f.repeat(Phase.COMBAT, Rune.READY, count=4)
        self.assertEqual(f.intents(), ["activate"])
        self.assertEqual(len(f.statuses("acknowledged")), 1)
        self.assertEqual(f.phases(), ["preparation", "combat"])

    def test_focus_loss_aborts_pending_audit(self):
        f = MatchFixture()
        f.first_combat(acknowledge=False)
        # Focus is a synthetic flag for the audit, not a real window check.
        f.feed(Phase.COMBAT, Rune.ACTIVE, focused=False)
        f.repeat(Phase.COMBAT, Rune.ACTIVE)
        self.assertEqual(len(f.statuses("aborted")), 1)
        self.assertEqual(f.statuses("acknowledged"), [])
        f.next_combat()
        self.assertEqual([e.intent for e in f.statuses("acknowledged")],
                         ["cancel", "activate"])

    def test_ending_latches_until_results(self):
        f = MatchFixture()
        f.first_combat()
        f.repeat(Phase.MATCH_ENDING)
        # A misleading combat classification during the ending is not a new match.
        f.repeat(Phase.COMBAT, Rune.READY, count=6)
        f.repeat(Phase.UNKNOWN, count=4)
        f.repeat(Phase.POST_MATCH, count=6)
        self.assertEqual(f.intents(), ["activate"])
        self.assertEqual(f.suggestions().count("match_complete"), 1)
        self.assertEqual(len(f.statuses("acknowledged")), 1)

    def test_emergency_stop_rejects_subsequent_previews(self):
        f = MatchFixture()
        f.first_combat(acknowledge=False)
        f.feed(Phase.COMBAT, Rune.ACTIVE, stop=True)
        f.repeat(Phase.COMBAT, Rune.ACTIVE)
        f.next_combat()
        # The read-only planner may still produce previews; the simulator
        # permanently rejects them after stop. Neither sends actual inputs.
        self.assertEqual(f.intents(), ["activate", "cancel", "activate"])
        self.assertEqual([e.intent for e in f.statuses("aborted")], ["activate"])
        self.assertEqual([e.intent for e in f.statuses("rejected")],
                         ["cancel", "activate"])
        self.assertEqual(f.statuses("acknowledged"), [])


if __name__ == "__main__":
    unittest.main()
