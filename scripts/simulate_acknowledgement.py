"""Offline-only acknowledgement simulation.

Consumes synthetic observations and hypothetical proposals. A delivery flag is
fixture data, not a call to an input device. No callbacks, capture, game
integration, keyboard/mouse imports, or retry mechanism are provided.
One instance models one simulated match; ending/stop is permanent.
"""
from dataclasses import dataclass
from math import isfinite

_PHASES = {"unknown", "preparation", "combat", "match_ending", "post_match"}
_RUNES = {"unknown", "ready", "active", "cooldown"}
_END = {"match_ending", "post_match"}
_EXPECT = {
    "activate": ("combat", "ready", frozenset({"active"})),
    "long_wave_activate": ("combat", "ready", frozenset({"active"})),
    "cancel": ("preparation", "active", frozenset({"cooldown", "ready"})),
}


@dataclass(frozen=True)
class Frame:
    seconds: float
    raw_phase: str
    confirmed_phase: str
    rune: str
    focused: bool = True
    stop: bool = False


@dataclass(frozen=True)
class Proposal:
    intent: str
    simulated_delivery: bool = True


@dataclass(frozen=True)
class AuditEvent:
    seconds: float
    intent: str
    status: str
    reason: str


class AcknowledgementSimulation:
    """Pure audit of hypothetical delivery and later synthetic observations.

    Two consecutive expected observations acknowledge a simulated delivery.
    Unknown observations break that streak. A timeout, contradiction, gap,
    focus loss, or phase transition ends the pending audit without retry.
    Timing defaults are test parameters, not measured game-input timings.
    """

    def __init__(self, *, timeout_seconds=3.0, max_gap_seconds=2.5):
        if (not isfinite(timeout_seconds) or timeout_seconds <= 0
                or not isfinite(max_gap_seconds) or max_gap_seconds <= 0):
            raise ValueError("Timing limits must be finite and positive")
        self.timeout = timeout_seconds
        self.max_gap = max_gap_seconds
        self._last = None
        self._phase = None
        self._pending = None
        self._streak = 0
        self._used = set()
        self._stopped = False

    def observe(self, frame: Frame, proposal: Proposal | None = None):
        now = frame.seconds
        if (not isfinite(now) or now < 0
                or (self._last is not None and now <= self._last)):
            raise ValueError("Synthetic timestamps must strictly increase")
        if (frame.raw_phase not in _PHASES
                or frame.confirmed_phase not in _PHASES
                or frame.rune not in _RUNES):
            raise ValueError("Invalid synthetic observation")
        if proposal is not None and (proposal.intent not in _EXPECT
                or type(proposal.simulated_delivery) is not bool):
            raise ValueError("Invalid synthetic proposal")

        gap = self._last is not None and now - self._last > self.max_gap
        self._last = now
        changed = frame.confirmed_phase != self._phase
        if changed:
            self._phase = frame.confirmed_phase
            self._used.clear()

        events = []

        def report(intent, status, reason):
            events.append(AuditEvent(now, intent, status, reason))

        def finish(status, reason):
            intent, _ = self._pending
            report(intent, status, reason)
            self._pending = None
            self._streak = 0

        if (frame.stop or frame.raw_phase in _END
                or frame.confirmed_phase in _END):
            self._stopped = True

        if self._stopped or not frame.focused or gap:
            reason = ("simulation stopped or ended" if self._stopped else
                      "focus lost" if not frame.focused else "observation gap")
            if self._pending is not None:
                finish("aborted", reason)
            if proposal is not None:
                report(proposal.intent, "rejected", reason)
            return tuple(events)

        if self._pending is not None:
            intent, started = self._pending
            phase, before, expected = _EXPECT[intent]
            elapsed = now - started
            if (changed or frame.confirmed_phase != phase
                    or frame.raw_phase not in (phase, "unknown")):
                finish("aborted", "phase changed")
            elif elapsed > self.timeout:
                finish("timeout", "no stable acknowledgement before deadline")
            else:
                if frame.raw_phase == phase and frame.rune in expected:
                    self._streak += 1
                elif (frame.raw_phase == phase
                      and frame.rune not in (before, "unknown")):
                    finish("unexpected", "contradictory observed state")
                else:
                    self._streak = 0
                if self._pending is not None:
                    if self._streak >= 2:
                        finish("acknowledged", "two expected observations")
                    elif elapsed >= self.timeout:
                        finish("timeout", "no stable acknowledgement before deadline")
            if proposal is not None:
                report(proposal.intent, "rejected", "prior audit occupied this frame")
            return tuple(events)

        if proposal is None:
            return ()
        intent = proposal.intent
        phase, before, _ = _EXPECT[intent]
        if (frame.confirmed_phase != phase or frame.raw_phase != phase
                or frame.rune != before):
            report(intent, "rejected", "proposal does not match observation")
        elif intent in self._used:
            report(intent, "rejected", "duplicate proposal in phase")
        else:
            self._used.add(intent)
            if not proposal.simulated_delivery:
                report(intent, "delivery_failed", "synthetic delivery failure")
            else:
                self._pending = (intent, now)
                self._streak = 0
                report(intent, "simulated", "fixture accepted; no input sent")
        return tuple(events)
