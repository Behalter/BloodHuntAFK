import unittest
from types import SimpleNamespace
from scripts.chrono_flow import ChronoFlow, RewardLatch


def obs(event='absent', lobby=False, popup=False):
    return SimpleNamespace(event=event, lobby=lobby, reward_popup=popup)


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.f = ChronoFlow(0)
        self.t = 0

    def feed(self, o=None, n=2, **kw):
        actions = []
        for _ in range(n):
            self.t += .5
            a = self.f.observe(self.t, o or obs(), **kw)
            if a:
                actions.append(a)
        return actions

    def to_claim(self):
        self.assertEqual(self.feed(summary=True), ['leave_summary'])
        self.assertEqual(self.feed(obs(lobby=True), solo_verified=True), ['open_chrono'])

    def to_verify(self):
        self.to_claim()
        self.assertEqual(self.feed(obs('claim_candidate')), ['claim_tokens'])

    def test_full_flow(self):
        self.to_verify()
        self.assertEqual(self.feed(obs('empty', popup=True)), [])
        self.assertTrue(self.f.claim_verified)
        self.assertEqual(self.feed(obs('empty', popup=True), n=4), [])
        self.assertEqual(self.feed(obs('empty')), ['leave_chrono'])
        self.assertEqual(self.feed(obs(lobby=True), solo_verified=True), ['start_match'])
        self.assertEqual(self.feed(next_match=True), [])
        self.assertEqual(self.f.stage, 'done')

    def test_latch(self):
        l = RewardLatch()
        self.assertFalse(l.observe('available', False))
        self.assertFalse(l.observe('available', True))
        self.assertFalse(l.observe('absent', True))
        self.assertFalse(l.observe('available', True))
        self.assertTrue(l.observe('available', True))
        self.assertTrue(l.observe('absent', False))

    def test_summary_requires_stability(self):
        self.assertEqual(self.feed(summary=True, n=1), [])
        self.assertEqual(self.feed(), [])
        self.assertEqual(self.feed(summary=True, n=1), [])
        self.assertEqual(self.feed(summary=True, n=1), ['leave_summary'])

    def test_solo_gate(self):
        self.to_verify()
        self.feed(obs('empty', popup=True))
        self.feed(obs('empty'))
        self.assertEqual(self.feed(obs(lobby=True), n=5), [])
        self.assertEqual(self.feed(obs(lobby=True), solo_verified=True), ['start_match'])

    def test_zero_during_load_never_claims(self):
        self.to_claim()
        self.assertEqual(self.feed(obs('empty'), n=5), [])
        self.assertEqual(self.feed(obs('uncertain'), n=5), [])
        self.assertEqual(self.feed(obs('claim_candidate')), ['claim_tokens'])

    def test_no_repeat_claim(self):
        self.to_verify()
        self.assertEqual(self.feed(obs('claim_candidate'), n=10), [])
        self.assertFalse(self.f.claim_verified)

    def test_zero_without_popup_not_verified(self):
        self.to_verify()
        self.assertEqual(self.feed(obs('empty'), n=8), [])
        self.assertFalse(self.f.claim_verified)

    def test_conflicting_lobby(self):
        self.to_claim()
        self.assertEqual(self.feed(obs('claim_candidate', lobby=True), n=4), [])

    def test_timeout(self):
        self.to_verify()
        self.assertEqual(self.feed(obs('claim_candidate'), n=61), [])
        self.assertEqual(self.f.stage, 'stopped')
        self.assertIn('timeout', self.f.error)

    def test_storage_warning(self):
        self.to_claim()
        self.assertEqual(self.feed(storage_warning=True), [])
        self.assertEqual(self.f.stage, 'stopped')

    def test_duplicate_timestamp_does_not_advance(self):
        self.assertIsNone(self.f.observe(.5, obs(), summary=True))
        self.assertIsNone(self.f.observe(.5, obs(), summary=True))
        self.assertEqual(self.f.observe(1, obs(), summary=True), "leave_summary")

    def test_gap(self):
        self.f.observe(3, obs(), summary=True)
        self.assertEqual(self.f.error, 'observation gap')

    def test_unexpected_match(self):
        self.feed(next_match=True)
        self.assertEqual(self.f.error, 'unexpected next match')

    def test_abort_terminal(self):
        self.f.abort('preflight')
        self.assertEqual(self.feed(summary=True, n=4), [])
        self.assertEqual(self.f.error, 'preflight')


if __name__ == '__main__':
    unittest.main()
