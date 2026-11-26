"""Pure, input-free preview of a future wave-aware F-key controller.

This module NEVER presses keys, moves a mouse, or imports any input module.
It consumes ShadowSample observations and writes *hypothetical* one-tap
decisions for audit. It is not a live game controller.
"""
from __future__ import annotations

from dataclasses import dataclass

from bloodhunt.wave_state import Phase, Rune
from scripts.shadow_monitor import ShadowSample

PREVIEW_FIELDS = ("seconds", "phase", "rune", "would_press", "intent", "reason")

# Hypothetical actions, NOT executable callbacks or button presses.
_INTENTS = {
    "consider_cancel_rune": ("cancel", Phase.PREPARATION, Rune.ACTIVE),
    "consider_activate_rune": ("activate", Phase.COMBAT, Rune.READY),
    "consider_long_wave_activation": ("long_wave_activate", Phase.COMBAT, Rune.READY),
}


@dataclass(frozen=True)
class PreviewEvent:
    seconds: float
    phase: str
    rune: str
    intent: str
    reason: str

    def csv_row(self):
        return {
            "seconds": f"{self.seconds:.2f}",
            "phase": self.phase,
            "rune": self.rune,
            "would_press": "F (one tap; NOT SENT)",
            "intent": self.intent,
            "reason": self.reason,
        }


class WaveActionPreview:
    """Preview at most one F tap per suggestion and confirmed phase epoch.

    Conditions: exact confirmed phase; two consecutive observations with a
    consistent expected Rune state; no gaps over max_gap; never trust UNKNOWN,
    match-ending, or post-match frames. After any sampling gap, fail closed
    until a newly confirmed phase transition. Manual F presses are not
    inferred or dispatched; they may happen before a preview would trigger.
    """

    def __init__(self, *, stable_samples=2, max_gap_seconds=2.5):
        if stable_samples < 2 or max_gap_seconds <= 0:
            raise ValueError("Invalid preview stability settings")
        self.stable_samples = stable_samples
        self.max_gap_seconds = max_gap_seconds
        self._last_seconds: float | None = None
        self._last_phase = Phase.UNKNOWN
        self._signature = None
        self._streak = 0
        self._pending = None
        self._used = set()
        self._blocked_for_gap = False
        self._ending = False

    def observe(self, sample: ShadowSample) -> tuple[PreviewEvent, ...]:
        now = sample.seconds
        if self._last_seconds is not None and now < self._last_seconds:
            raise ValueError("Preview samples must be in timestamp order")
        if (self._last_seconds is not None and
                now - self._last_seconds > self.max_gap_seconds):
            self._blocked_for_gap = True
            self._pending = None
            self._signature = None
            self._streak = 0
        self._last_seconds = now

        phase = sample.confirmed_phase
        changed = phase is not self._last_phase
        previous_phase = self._last_phase
        if changed:
            self._last_phase = phase
            self._used.clear()
            self._pending = None
            self._signature = None
            self._streak = 0
            if self._blocked_for_gap:
                # A new confirmed phase, rather than simply returning focus
                # to a stale frame, is required before considering an intent.
                self._blocked_for_gap = False
        if phase in (Phase.MATCH_ENDING, Phase.POST_MATCH):
            self._ending = True
            self._pending = None
            return ()
        if self._ending:
            if changed and previous_phase is Phase.POST_MATCH:
                self._ending = False  # new match
            else:
                return ()
        if self._blocked_for_gap:
            return ()

        d = sample.detection
        if d.phase is not phase or d.rune is Rune.UNKNOWN:
            self._pending = None
            self._signature = None
            self._streak = 0
            return ()

        signature = (d.phase, d.rune)
        if signature == self._signature:
            self._streak += 1
        else:
            self._signature, self._streak = signature, 1

        for event in sample.events:
            if event.kind != "suggestion":
                continue
            spec = _INTENTS.get(event.details)
            if spec is not None:
                intent, required_phase, required_rune = spec
                if phase is required_phase and d.rune is required_rune:
                    self._pending = intent

        if not self._pending or self._streak < self.stable_samples:
            return ()

        required = next(
            ((p, r) for intent, p, r in _INTENTS.values()
             if intent == self._pending), None)
        if required != (phase, d.rune) or self._pending in self._used:
            self._pending = None
            return ()

        intent = self._pending
        self._pending = None
        self._used.add(intent)
        return (PreviewEvent(now, phase.value, d.rune.value, intent,
                             "confirmed phase and Rune; hypothetical single F tap"),)
