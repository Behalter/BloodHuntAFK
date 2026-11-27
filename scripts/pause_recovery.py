"""Input-free recovery gate for an intentional observation pause.

Require three fresh, consecutive observations of the same gameplay phase
and Rune state. The phase may be identical to the pre-pause phase.
"""

class ResumeGate:
    def __init__(self):
        self.candidate = None
        self.streak = 0

    def observe(self, phase, rune):
        if phase not in ("preparation", "combat") or rune not in ("ready", "active", "cooldown"):
            self.candidate = None
            self.streak = 0
            return False
        signature = (phase, rune)
        if signature == self.candidate:
            self.streak += 1
        else:
            self.candidate, self.streak = signature, 1
        return self.streak >= 3


def pending_reconciled(phase, rune, pending_phase, expected):
    """Check observed state, not causation; never authorize a retry."""
    return phase == pending_phase and rune in expected
