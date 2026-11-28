"""Input-free, single-use Chrono Rush claim sequence.

The caller supplies fresh game observations and dispatches an emitted intent
at most once, after its own foreground/geometry/input preflight. A failed
preflight or interrupted sequence must stop; never retry an emitted intent.
"""
from math import isfinite


class RewardLatch:
    """Remember a positive claim notification through subsequent screens."""
    def __init__(self):
        self.streak = 0
        self.available = False

    def observe(self, card, victory_results):
        self.streak = self.streak + 1 if victory_results and card == 'available' else 0
        self.available = self.available or self.streak >= 2
        return self.available


class ChronoFlow:
    """One claim attempt per verified match; no input during uncertainty."""
    def __init__(self, now):
        if not isfinite(now):
            raise ValueError('Invalid clock')
        self.started = self.since = self.last = now
        self.stage = 'summary'
        self.streak = 0
        self.popup_seen = False
        self.claim_verified = False
        self.error = None

    def _advance(self, stage, now, intent=None):
        self.stage, self.since, self.streak = stage, now, 0
        return intent

    def abort(self, reason):
        self.error = reason
        self.stage = 'stopped'

    def observe(self, now, observation, *, summary=False, next_match=False,
                storage_warning=False, solo_verified=False):
        if self.stage in ('done', 'stopped'):
            return None
        if not isfinite(now) or now < self.last:
            self.abort('invalid observation clock')
            return None
        if now == self.last:
            return None  # one observation per distinct capture timestamp
        if now - self.last > 2.5:
            self.abort('observation gap')
            return None
        self.last = now
        if now - self.since >= 30 or now - self.started >= 120:
            self.abort('timeout in ' + self.stage)
            return None
        if storage_warning:
            self.abort('storage warning; lobby smelting path not verified')
            return None
        if next_match:
            if self.stage == 'await_match':
                self._advance('done', now)
            else:
                self.abort('unexpected next match')
            return None
        if self.stage == 'summary':
            eligible = summary and not observation.lobby and observation.event == 'absent'
        elif self.stage == 'open_event':
            eligible = observation.lobby and observation.event == 'absent'
        elif self.stage == 'claim':
            eligible = (observation.event == 'claim_candidate' and not observation.reward_popup
                        and not observation.lobby)
        elif self.stage == 'verify':
            self.popup_seen = self.popup_seen or (observation.reward_popup and observation.event == 'empty')
            eligible = self.popup_seen and observation.event == 'empty' and not observation.lobby
        elif self.stage == 'leave_event':
            eligible = observation.event == 'empty' and not observation.reward_popup and not observation.lobby
        elif self.stage == 'start':
            eligible = observation.lobby and solo_verified and observation.event == 'absent'
        else:  # await_match: never retry START
            return None
        self.streak = self.streak + 1 if eligible else 0
        if self.streak < 2:
            return None
        if self.stage == 'summary':
            return self._advance('open_event', now, 'leave_summary')
        if self.stage == 'open_event':
            return self._advance('claim', now, 'open_chrono')
        if self.stage == 'claim':
            return self._advance('verify', now, 'claim_tokens')
        if self.stage == 'verify':
            self.claim_verified = True
            return self._advance('leave_event', now)
        if self.stage == 'leave_event':
            return self._advance('start', now, 'leave_chrono')
        if self.stage == 'start':
            return self._advance('await_match', now, 'start_match')
