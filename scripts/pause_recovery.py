"""Pure conservative recovery gate for an intentional observation pause.

A repeated phase label does not prove that it is the same wave. Suppress
Rune actions until a different phase has been observed twice. This module
does not capture frames, send input, or alter match counters.
"""


class ResumeGate:
    def __init__(self, previous_phase):
        self.previous_phase = previous_phase if previous_phase in ("preparation", "combat") else None
        self.candidate = None
        self.streak = 0

    def observe(self, phase, valid):
        """Return True only on a fresh, stable, different gameplay phase."""
        if not valid or phase not in ("preparation", "combat"):
            self.candidate = None
            self.streak = 0
            return False
        if phase == self.candidate:
            self.streak += 1
        else:
            self.candidate, self.streak = phase, 1
        if self.streak < 2:
            return False
        if self.previous_phase is None:
            self.previous_phase = phase
        return phase != self.previous_phase
