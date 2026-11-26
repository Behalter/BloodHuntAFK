"""Side-effect-free bridge between recorded/live frames and the wave advisor.

Accepts BGR frames and elapsed timestamps, then returns observable phase/rune
states and *recommendations only*. No game capture, window management, imports
from bloodhunt.inputs, key presses, clicks, or file output happen here.
"""
from __future__ import annotations

from dataclasses import dataclass

from bloodhunt.wave_state import Observation, Phase, Rune, WaveAdvisor
from scripts.analyze_video import Detection, detect


@dataclass(frozen=True)
class ShadowEvent:
    seconds: float
    kind: str
    phase: str
    rune: str
    details: str

    def csv_row(self):
        return {
            "seconds": f"{self.seconds:.2f}",
            "kind": self.kind,
            "phase": self.phase,
            "rune": self.rune,
            "details": self.details,
        }


@dataclass(frozen=True)
class ShadowSample:
    seconds: float
    detection: Detection
    confirmed_phase: Phase
    events: tuple[ShadowEvent, ...]

    def csv_row(self):
        d = self.detection
        return {
            "seconds": f"{self.seconds:.2f}",
            "detected_phase": d.phase.value,
            "rune": d.rune.value,
            "incoming_score": f"{d.incoming_score:.3f}",
            "combat_score": f"{d.combat_score:.3f}",
            "victory_score": f"{d.victory_score:.3f}",
            "boss_objective_score": f"{d.boss_objective_score:.3f}",
            "ending_score": f"{d.ending_score:.3f}",
            "boss_bar_run": d.boss_bar_run,
            "phase_header_score": f"{d.phase_header_score:.3f}",
            "confirmed_phase": self.confirmed_phase.value,
            "suggestions": ";".join(e.details for e in self.events if e.kind == "suggestion"),
        }


EVENT_FIELDS = ("seconds", "kind", "phase", "rune", "details")
SAMPLE_FIELDS = ("seconds", "detected_phase", "rune", "incoming_score",
                 "combat_score", "victory_score", "boss_objective_score",
                 "ending_score", "boss_bar_run", "phase_header_score",
                 "confirmed_phase", "suggestions")


class ShadowMonitor:
    """Observe frames without ever interacting with the game.

    `detector` may be injected for tests. A phase transition needs two
    consecutive matching observations; Rune icon changes need two consecutive
    known observations, as in the offline analyzer.
    """

    def __init__(self, calibration, *, detector=detect, stable_frames=2,
                 long_wave_seconds=75):
        self.calibration = calibration
        self.detector = detector
        self.advisor = WaveAdvisor(stable_frames=stable_frames,
                                   long_wave_seconds=long_wave_seconds)
        self._seen_rune = Rune.UNKNOWN
        self._pending_rune = Rune.UNKNOWN
        self._pending_count = 0

    def feed(self, seconds: float, bgr_frame) -> ShadowSample:
        detection = self.detector(bgr_frame, self.calibration)
        decision = self.advisor.observe(
            Observation(seconds, detection.phase, detection.rune))
        events = []

        rune = detection.rune
        if rune is Rune.UNKNOWN:
            self._pending_rune, self._pending_count = Rune.UNKNOWN, 0
        elif rune is self._pending_rune:
            self._pending_count += 1
        else:
            self._pending_rune, self._pending_count = rune, 1

        if self._pending_count >= 2 and rune is not self._seen_rune:
            previous, self._seen_rune = self._seen_rune, rune
            events.append(ShadowEvent(seconds, "rune", detection.phase.value,
                                      rune.value,
                                      f"F icon: {previous.value} -> {rune.value}"))
        if decision.transition_confirmed:
            events.append(ShadowEvent(seconds, "phase",
                                      decision.confirmed_phase.value,
                                      rune.value, "phase confirmed"))
        for suggestion in decision.suggestions:
            events.append(ShadowEvent(seconds, "suggestion",
                                      decision.confirmed_phase.value,
                                      rune.value, suggestion.value))
        return ShadowSample(seconds, detection, decision.confirmed_phase,
                            tuple(events))
