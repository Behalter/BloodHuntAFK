"""Read-only, deterministic wave/Rune state advisor.

This module has no screen capture, keyboard/mouse input, Windows calls, or bot
integration. An external detector must produce observations from recorded
frames. Suggestions are *not* instructions to press buttons automatically.

Most importantly, cancelling Awakening Rune may incur a cooldown; the intended
cancel/restart strategy has not yet been verified against gameplay mechanics.
"""

from dataclasses import dataclass
from enum import Enum


class Phase(str, Enum):
    UNKNOWN = "unknown"
    MATCH_ENDING = "match_ending"  # countdown/results transition; no ability advice
    PREPARATION = "preparation"  # 'Vampires Incoming' or '<Boss> Incoming'
    COMBAT = "combat"
    POST_MATCH = "post_match"


class Rune(str, Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    READY = "ready"  # confirmed inactive AND available
    COOLDOWN = "cooldown"  # not active and not yet ready


class Suggestion(str, Enum):
    CANCEL_RUNE = "consider_cancel_rune"
    ACTIVATE_RUNE = "consider_activate_rune"
    LONG_WAVE_ACTIVATION = "consider_long_wave_activation"
    MATCH_COMPLETE = "match_complete"


@dataclass(frozen=True)
class Observation:
    """A detector's timestamped observation of one frame or sampled moment.

    The detector must only report READY when both inactive and ready are
    positively confirmed; an unclear or hidden HUD is UNKNOWN, not READY.
    """
    seconds: float
    phase: Phase
    rune: Rune = Rune.UNKNOWN


@dataclass(frozen=True)
class Result:
    confirmed_phase: Phase
    suggestions: tuple[Suggestion, ...]
    transition_confirmed: bool


class WaveAdvisor:
    """Debounced one-shot advice for a manually observed Blood Hunt match.

    Unknown/conflicting frames never generate suggestions. A new phase must be
    seen on stable_frames consecutive observations before any suggestions
    are made. A new phase epoch resets one-shot gates, but merely losing sight
    of the HUD does not count as a new phase.
    """

    def __init__(self, stable_frames: int = 2, long_wave_seconds: float = 75.0):
        if stable_frames < 2:
            raise ValueError("stable_frames must be at least 2")
        if long_wave_seconds <= 0:
            raise ValueError("long_wave_seconds must be positive")
        self.stable_frames = stable_frames
        self.long_wave_seconds = long_wave_seconds
        self.confirmed_phase = Phase.UNKNOWN
        self._candidate = Phase.UNKNOWN
        self._streak = 0
        self._phase_since: float | None = None
        self._last_seconds: float | None = None
        self._cancel_suggested = False
        self._initial_suggested = False
        self._extra_suggested = False
        self._active_after_initial = False
        self._ending_seen = False  # suppress Rune advice after match-ending transition

    def observe(self, observation: Observation) -> Result:
        now = observation.seconds
        if self._last_seconds is not None and now < self._last_seconds:
            raise ValueError("observations must be ordered by timestamp")
        self._last_seconds = now

        if observation.phase is Phase.UNKNOWN:
            self._candidate = Phase.UNKNOWN
            self._streak = 0
            return Result(self.confirmed_phase, (), False)

        if observation.phase is self._candidate:
            self._streak += 1
        else:
            self._candidate = observation.phase
            self._streak = 1

        if self._streak < self.stable_frames:
            return Result(self.confirmed_phase, (), False)

        previous_phase = self.confirmed_phase
        changed = observation.phase is not previous_phase
        if changed:
            if previous_phase is Phase.POST_MATCH and observation.phase in (Phase.COMBAT, Phase.PREPARATION):
                self._ending_seen = False  # a subsequent match has started
            if observation.phase is Phase.MATCH_ENDING:
                self._ending_seen = True
            self.confirmed_phase = observation.phase
            self._phase_since = now
            self._cancel_suggested = False
            self._initial_suggested = False
            self._extra_suggested = False
            self._active_after_initial = False

        if self.confirmed_phase is Phase.POST_MATCH:
            return Result(self.confirmed_phase,
                          (Suggestion.MATCH_COMPLETE,) if changed else (), changed)

        # An ending transition must never be mistaken for another wave. Keep
        # suppressing advice through brief unknown frames or cinematic overlays.
        if self.confirmed_phase is Phase.MATCH_ENDING or self._ending_seen:
            return Result(self.confirmed_phase, (), changed)

        if self.confirmed_phase is Phase.PREPARATION:
            # Never suggest canceling if already inactive, ready state unknown,
            # or while in cooldown. One suggestion per preparation interval.
            if observation.rune is Rune.ACTIVE and not self._cancel_suggested:
                self._cancel_suggested = True
                return Result(self.confirmed_phase, (Suggestion.CANCEL_RUNE,), changed)
            return Result(self.confirmed_phase, (), changed)

        # COMBAT. Only a positively observed READY state permits a suggestion.
        if observation.rune is Rune.ACTIVE and self._initial_suggested:
            self._active_after_initial = True

        if observation.rune is Rune.READY:
            if not self._initial_suggested:
                self._initial_suggested = True
                return Result(self.confirmed_phase, (Suggestion.ACTIVATE_RUNE,), changed)
            if (self._active_after_initial and not self._extra_suggested
                    and self._phase_since is not None
                    and now - self._phase_since >= self.long_wave_seconds):
                self._extra_suggested = True
                return Result(self.confirmed_phase,
                              (Suggestion.LONG_WAVE_ACTIVATION,), changed)
        return Result(self.confirmed_phase, (), changed)
