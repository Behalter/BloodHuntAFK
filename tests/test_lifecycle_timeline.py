import unittest
from scripts.lifecycle_timeline import combine, segments


class LifecycleTimelineTests(unittest.TestCase):
    def test_gameplay_retains_rune(self):
        for phase in ("preparation", "combat"):
            row = combine(0, phase, "ready", "unknown")
            self.assertEqual((row.screen, row.visible_rune), (phase, "ready"))

    def test_shop_masks_rune_but_preserves_raw(self):
        row = combine(1, "preparation", "active", "blessing_shop", ("shop",))
        self.assertEqual((row.screen, row.visible_rune, row.raw_rune),
                         ("blessing_shop", "unknown", "active"))

    def test_results_refines_post_match(self):
        row = combine(2, "post_match", "unknown", "final_summary")
        self.assertEqual(row.screen, "final_summary")

    def test_match_found_over_results(self):
        self.assertEqual(combine(2, "post_match", "unknown", "match_found").screen,
                         "match_found")

    def test_conflict_is_unknown(self):
        row = combine(3, "combat", "ready", "hero_selection")
        self.assertEqual((row.screen, row.visible_rune, row.reason),
                         ("unknown", "unknown", "classifier_disagreement"))
        self.assertEqual((row.raw_phase, row.raw_screen), ("combat", "hero_selection"))

    def test_unresolved_markers_not_discarded(self):
        row = combine(4, "combat", "ready", "unknown", ("mvp", "shop"))
        self.assertEqual((row.screen, row.markers, row.reason),
                         ("unknown", "mvp;shop", "unresolved_screen_markers"))

    def test_no_rune_outside_gameplay(self):
        for phase in ("unknown", "match_ending", "post_match"):
            self.assertEqual(combine(5, phase, "active", "unknown").visible_rune, "unknown")

    def test_unknown_remains_unknown(self):
        rows = [combine(i, "unknown", "unknown", screen) for i, screen in
                enumerate(("mvp", "unknown", "mvp", "results", "match_found", "results"))]
        self.assertEqual([s.screen for s in segments(rows)],
                         ["mvp", "unknown", "mvp", "results", "match_found", "results"])

    def test_segments_split_sampling_gaps(self):
        rows = [combine(i, "combat", "ready", "unknown") for i in (0, 1, 6, 7)]
        self.assertEqual([(s.first_sample, s.last_sample, s.samples) for s in segments(rows)],
                         [(0, 1, 2), (6, 7, 2)])

    def test_backwards_timestamps_rejected(self):
        rows = [combine(i, "combat", "ready", "unknown") for i in (1, 0)]
        with self.assertRaises(ValueError):
            segments(rows)

    def test_invalid_values_rejected(self):
        for t in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                combine(t, "combat", "ready", "unknown")
        with self.assertRaises(ValueError):
            combine(0, "invalid", "ready", "unknown")
        with self.assertRaises(ValueError):
            segments([], max_gap=0)

    def test_empty_segments(self):
        self.assertEqual(segments([]), [])


if __name__ == "__main__":
    unittest.main()
