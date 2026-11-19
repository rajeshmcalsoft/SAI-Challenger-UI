"""Compare model: synthetic cases, plus matrix parity with summarize.py on the real latest runs."""
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sai_challenger_ui import settings
from sai_challenger_ui.core import catalog, compare, profiles, reports
from sai_challenger_ui.core.junit import TestResult
from sai_challenger_ui.core.vocab import SUMMARIZE_OUTCOME, Result

R = Result


def run(target, tests, day=17):
    return reports.Run(f"{target}-11{day}-100000", target, datetime(2026, 11, day, tzinfo=UTC), 1.0,
                       Path(f"/x/{target}.xml"), None, None, "h", tests)


def t(name, result, message="", module="test_poc_l2", cls=None):
    key = "::".join(p for p in (module, cls, name) if p)
    return TestResult(key, module, cls, name, result, 0.1, message)


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / "saivs.json").write_text('{"name": "saivs", "expected_gaps": {"t_gap[*]": "accepts bad IDs", "t_applied": "x"}}')
        (d / "saivpp.json").write_text('{"name": "saivpp", "expected_gaps": {}, "scope_gaps": {"FDB aging": "16 ports"}}')
        self.profiles = profiles.load_all(d)
        self.cat = catalog.Catalogue()

    def tearDown(self):
        self.tmp.cleanup()

    def test_matrix_rows_badges_and_order(self):
        saivs = run("saivs", [t("t_ok", R.PASS), t("t_gap[0]", R.EXPECTED_GAP), t("t_gap[1]", R.GAP_PASSES),
                              t("t_applied", R.FAIL), t("t_new", R.PASS)])
        saivpp = run("saivpp", [t("t_ok", R.PASS), t("t_gap[0]", R.FAIL), t("t_new", R.FAIL)])
        m = compare.build_matrix([saivpp, saivs], self.profiles, self.cat)
        self.assertEqual([c.target for c in m.columns], ["saivs", "saivpp"])  # reference order, not input order
        rows = {r.test_id: r for r in m.rows}
        self.assertFalse(rows["t_ok"].differs)
        self.assertIsNone(rows["t_applied"].cells["saivpp"].result)  # not in that run
        self.assertIn(("stale_gap", "saivs"), rows["t_gap[1]"].badges)
        self.assertIn(("not_applied", "saivs"), rows["t_applied"].badges)
        self.assertIn(("new_gap", "saivpp"), rows["t_new"].badges)
        self.assertEqual(rows["t_gap[0]"].cells["saivs"].gap, ("t_gap[*]", "accepts bad IDs"))
        self.assertEqual(m.attention["saivpp"], ["2 new gaps"])
        self.assertEqual(m.attention["saivs"], ["1 stale gap", "1 gap not applied"])

    def test_run_diff(self):
        a = run("saivs", [t("t1", R.PASS), t("t2", R.FAIL), t("t3", R.PASS), t("t4", R.EXPECTED_GAP, "old"),
                          t("t5", R.SKIPPED), t("only_a", R.PASS)])
        b = run("saivs-thrift", [t("t1", R.FAIL), t("t2", R.PASS), t("t3", R.EXPECTED_GAP), t("t4", R.EXPECTED_GAP, "new"),
                                 t("t5", R.PASS)])
        d = compare.run_diff(a, b)
        names = {k: [x[1].name for x in v] for k, v in d.sections.items() if v}
        self.assertEqual(names, {"New failures": ["t1"], "Fixed": ["t2"], "New expected gaps": ["t3"],
                                 "Reason changed": ["t4"], "No longer skipped": ["t5"]})
        self.assertEqual((d.only_a, d.only_b, d.compared), (1, 0, 5))
        self.assertTrue(d.headline.startswith("saivs-thrift against saivs: 1 new failure, 1 fixed"))

    def test_gap_register(self):
        saivs = run("saivs", [t("t_gap[0]", R.EXPECTED_GAP), t("t_gap[1]", R.GAP_PASSES)])
        reg = compare.gap_register(self.profiles, {"saivs": saivs, "saivpp": None}, ["t_gap[0]", "t_gap[1]", "t_applied"])
        by = {(g.pattern, g.scope): g for g in reg}
        self.assertEqual(by[("t_gap[*]", False)].status, {"saivs": "now_passes"})
        self.assertEqual(by[("t_applied", False)].status, {"saivs": "not_run"})
        self.assertEqual(by[("FDB aging", True)].reasons, {"saivpp": "16 ports"})

    def test_lookup_history(self):
        with tempfile.TemporaryDirectory():
            idx = reports.RunIndex("/nonexistent")
            r1, r2 = run("saivs", [t("v[0]", R.PASS), t("v[1]", R.FAIL)], 16), run("saivs", [t("v[0]", R.PASS)], 17)
            idx._cache = {Path("a"): (0, r1), Path("b"): (0, r2)}
            look = compare.Lookup()
            self.assertEqual(look.worst_in(r1, ("test_poc_l2", None, "v")), R.FAIL)
            self.assertEqual([r for _, r in look.history(idx, "saivs", ("test_poc_l2", None, "v"))], [R.FAIL, R.PASS])


S = settings.load()


@unittest.skipUnless((S.poc_dir / "summarize.py").is_file() and S.reports_dir.is_dir(), "no SAI-Challenger checkout")
class MatrixParityTest(unittest.TestCase):
    def test_matrix_matches_summarize(self):
        """Phase 2 exit check: each cell equals summarize.py's outcome for the same reports (Error counts as failed)."""
        from test_real_data import _summarize

        summ = _summarize()
        profs = profiles.load_all(S.targets_dir)
        index = reports.RunIndex(S.reports_dir, profs)
        index.refresh()
        latest = [r for r in (index.latest(n) for n in profs) if r]
        cat = catalog.build(S.poc_dir)
        m = compare.build_matrix(latest, profs, cat)

        theirs = {}
        for c in latest:
            for test in summ.parse_report(str(c.xml))["tests"].values():
                theirs[(c.target, test["name"])] = test["outcome"]

        checked = 0
        for row in m.rows:
            for target, cell in row.cells.items():
                if cell.steps:
                    pairs = [(name, res) for _, res, _, name in cell.steps]
                    cls = row.test_id if row.test_id[:1].isupper() else None
                    pairs = [((f"{cls}::{n}" if cls else n), r) for n, r in pairs]
                elif cell.result is not None:
                    cls = row.key.split("::")[1] if row.key.count("::") == 2 else None
                    pairs = [((f"{cls}::{row.test_id}" if cls else row.test_id), cell.result)]
                else:
                    continue
                for shown, result in pairs:
                    self.assertEqual(SUMMARIZE_OUTCOME[result], theirs[(target, shown)], (target, shown))
                    checked += 1
        self.assertGreater(checked, 100)


if __name__ == "__main__":
    unittest.main()
