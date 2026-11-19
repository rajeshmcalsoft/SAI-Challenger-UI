"""Checks against the real SAI-Challenger checkout and its reports. Read-only.

Skipped when the checkout isn't there (e.g. on a vendor machine). summarize.py is imported with
bytecode writing off, so no __pycache__ lands in the checkout.
"""
import importlib.util
import sys
import unittest

from sai_challenger_ui import settings
from sai_challenger_ui.core import catalog, explain, profiles, reports
from sai_challenger_ui.core.vocab import SUMMARIZE_OUTCOME

S = settings.load()
HAVE = S.poc_dir.is_dir() and S.reports_dir.is_dir()


def _summarize():
    path = S.poc_dir / "summarize.py"
    spec = importlib.util.spec_from_file_location("_sai_challenger_ui_summarize", path)
    module = importlib.util.module_from_spec(spec)
    before = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = before
    return module


@unittest.skipUnless(HAVE, "no SAI-Challenger checkout")
class RealDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = profiles.load_all(S.targets_dir)
        cls.index = reports.RunIndex(S.reports_dir, cls.profiles)
        cls.runs = cls.index.refresh()

    def test_every_report_parses(self):
        self.assertEqual(self.index.problems, {})
        self.assertGreater(len(self.runs), 0)

    def test_counts_match_summarize(self):
        """Per-run outcome counts equal summarize.py's, with Setup/Cleanup error counted as its 'failed'."""
        summ = _summarize()
        for run in self.runs:
            theirs = summ.count(summ.parse_report(str(run.xml)))
            ours = dict.fromkeys(theirs, 0)
            for t in run.tests:
                ours[SUMMARIZE_OUTCOME[t.result]] += 1
            self.assertEqual(ours, theirs, run.id)

    def test_conftest_gap_rule_unchanged(self):
        """profiles.gap_matches copies the conftest's rule; fail loudly if the conftest changes it."""
        source = (S.poc_dir / "conftest.py").read_text()
        self.assertIn('fnmatch.fnmatchcase(item.name, pattern.replace("[", "[[]"))', source)

    def test_catalogue_covers_latest_runs(self):
        cat = catalog.build(S.poc_dir)
        catalog.merge_history(cat, self.runs)
        self.assertEqual(cat.problems, [])
        names = set(cat.all_names())
        for name in self.profiles:
            run = self.index.latest(name)
            if run is None:
                continue
            ran = {t.name for t in run.tests if not t.upstream and t.name != "(collection)"}
            # Tests removed or renamed since that run are allowed; most must be known.
            self.assertGreater(len(ran & names) / max(len(ran), 1), 0.8, run.id)

    def test_hints_on_real_messages(self):
        """No hint may fire on a result it doesn't fit; print which signatures real data exercises."""
        hints = explain.Hints()
        fired = {}
        for run in self.runs:
            for t in run.tests:
                h = hints.match(t.result, t.message, t.detail)
                if h:
                    fired.setdefault(h.id, set()).add(t.base)
        self.assertNotIn("test_poc_l2_vlan_duplicate_rejected", fired.get("left-over-objects", set()))
        print("\nhints fired on real data:", {k: len(v) for k, v in sorted(fired.items())})


if __name__ == "__main__":
    unittest.main()
