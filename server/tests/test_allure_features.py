"""The Allure-inspired additions: history marks, causes, gates, gap kinds, diff extraction, exports, the new API
endpoints and "Retry failures". Host only: no target, container or lock; runs use a fake run_poc.sh."""
import json
import tempfile
import time
import unittest
import warnings
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest import mock

from test_api import SOURCE
from test_core import JUNIT
from test_runs import ACL, HEADERS, L2, PROFILE

from sai_challenger_ui.core import causes, explain, exports, gapnotes, gates, history, junit, profiles, reports
from sai_challenger_ui.core.vocab import Result
from sai_challenger_ui.settings import Settings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

    from sai_challenger_ui.api.app import create_app

R = Result


def run_of(target, started, results, rid=None):
    """A Run with one PoC test per (name, result)."""
    tests = [junit.TestResult(f"test_poc_l2::{n}", "test_poc_l2", None, n, r, 0.1, "msg") for n, r in results.items()]
    return reports.Run(rid or f"{target}-{started:%m%d-%H%M%S}", target, started, 1.0, Path("x.xml"), None, None, "", tests)


class FakeIndex:
    def __init__(self, runs):
        self._runs = runs

    def runs(self, target=None):
        return sorted((r for r in self._runs if target in (None, r.target)), key=lambda r: (r.started, r.id), reverse=True)


T0 = datetime(2026, 11, 1, tzinfo=UTC)


def series(name, outcomes, target="saivs"):
    return [run_of(target, T0 + timedelta(hours=i), {name: r}) for i, r in enumerate(outcomes)]


class HistoryTest(unittest.TestCase):
    def marks(self, outcomes, name="test_a"):
        runs = series(name, outcomes)
        return history.marks(FakeIndex(runs), history.Results(), runs[-1])[f"test_poc_l2::{name}"]

    def test_transitions(self):
        self.assertEqual(self.marks([R.PASS]).transition, "new")
        self.assertEqual(self.marks([R.PASS, R.FAIL]).transition, "regressed")
        self.assertEqual(self.marks([R.EXPECTED_GAP, R.FAIL]).transition, "regressed")
        self.assertEqual(self.marks([R.PASS, R.SETUP_ERROR]).transition, "new_error")
        self.assertEqual(self.marks([R.FAIL, R.PASS]).transition, "fixed")
        self.assertEqual(self.marks([R.EXPECTED_GAP, R.PASS]).transition, "fixed")
        self.assertIsNone(self.marks([R.GAP_PASSES, R.PASS]).transition)  # it already passed
        self.assertEqual(self.marks([R.FAIL, R.SKIPPED, R.PASS]).transition, "fixed")  # skipped results are looked past
        self.assertIsNone(self.marks([R.PASS, R.PASS]).transition)

    def test_flaky_follows_allures_rule(self):
        self.assertTrue(self.marks([R.FAIL, R.PASS, R.FAIL]).flaky)  # two changes, failing now
        self.assertFalse(self.marks([R.PASS, R.PASS, R.FAIL]).flaky)  # one change is not enough
        self.assertFalse(self.marks([R.FAIL, R.PASS, R.PASS]).flaky)  # passing now: never flaky
        self.assertFalse(self.marks([R.FAIL, R.PASS] + [R.FAIL] * 5).flaky)  # 5 alike in a row: earlier changes drop
        self.assertTrue(self.marks([R.EXPECTED_GAP, R.GAP_PASSES, R.EXPECTED_GAP]).flaky)  # a gap that flips counts too

    def test_age(self):
        m = self.marks([R.PASS, R.FAIL, R.FAIL, R.FAIL])
        self.assertEqual((m.age_runs, m.previous), (3, R.FAIL))
        self.assertEqual(m.age_since, (T0 + timedelta(hours=1)).isoformat(timespec="seconds"))

    def test_rows_rate_and_targets(self):
        runs = series("test_a", [R.PASS, R.FAIL, R.SKIPPED, R.PASS]) + series("test_a", [R.EXPECTED_GAP], target="saivpp")
        idx, res = FakeIndex(runs), history.Results()
        current = idx.runs("saivs")[0]
        rows = history.test_history(idx, res, current, "test_poc_l2::test_a")
        self.assertEqual([r.result for r in rows], [R.PASS, R.SKIPPED, R.FAIL, R.PASS])
        self.assertEqual(history.success_rate(rows), (2, 3))
        other = history.across_targets(idx, res, "test_poc_l2::test_a", ["saivs", "saivpp", "nowhere"])
        self.assertEqual({k: v[1].result for k, v in other.items()}, {"saivs": R.PASS, "saivpp": R.EXPECTED_GAP})
        dyn = history.dynamics(idx, res, current)
        self.assertEqual([(d["fixed"], d["regressed"]) for d in dyn], [(0, 0), (0, 1), (0, 0), (0, 0)])


class Hint:
    def __init__(self, hid, title):
        self.id, self.title, self.text = hid, title, title


class Hints:
    def match(self, result, message, detail=""):
        return Hint("poc-ports-factory", "poc_ports used as a list") if "subscriptable" in message else None


class CausesAndDiffTest(unittest.TestCase):
    def test_causes_group_by_status_family(self):
        tests = [
            junit.TestResult("a", "m", None, "a", R.EXPECTED_GAP, 0, "Duplicate VLAN returns INVALID_PARAMETER, expected X"),
            junit.TestResult("b", "m", None, "b", R.FAIL, 0, "AssertionError: duplicate VLAN 20 returned SAI_STATUS_INVALID_PARAMETER"),
            junit.TestResult("c", "m", None, "c", R.EXPECTED_GAP, 0, "Target accepts VLAN ID 0"),
            junit.TestResult("d", "m", None, "d", R.SETUP_ERROR, 0, "TypeError: 'function' object is not subscriptable"),
            junit.TestResult("e", "m", None, "e", R.FAIL, 0, "AssertionError: Received packet that we expected not to receive on device 0, port 2."),
            junit.TestResult("f", "m", None, "f", R.PASS, 0, ""),
        ]
        run = reports.Run("r", "saivs", T0, 1, Path("x"), None, None, "", tests)
        found = {c.id: (c.family, c.title, c.keys) for c in causes.build(run, Hints())}
        self.assertEqual(found["status:SAI_STATUS_INVALID_PARAMETER"], ("target", "SAI_STATUS_INVALID_PARAMETER", ["a", "b"]))
        self.assertEqual(found["accepts"][2], ["c"])
        self.assertEqual(found["hint:poc-ports-factory"], ("setup", "poc_ports used as a list", ["d"]))
        self.assertEqual(found["packet:unexpected"][2], ["e"])
        self.assertEqual(list(found)[-1], "hint:poc-ports-factory")  # setup problems after target behaviour

    def test_expected_actual(self):
        detail = ("E           AssertionError: assert '20' == '21'\nE             \nE             - 21\nE             + 20\n")
        self.assertEqual(explain.expected_actual("AssertionError: assert '20' == '21'", detail), ("21", "20"))
        self.assertEqual(explain.expected_actual("Duplicate VLAN returns INVALID_PARAMETER, expected ITEM_ALREADY_EXISTS"),
                         ("SAI_STATUS_ITEM_ALREADY_EXISTS", "SAI_STATUS_INVALID_PARAMETER"))
        self.assertIsNone(explain.expected_actual("assert 'SAI_VLAN_TAG...MODE_UNTAGGED' == 'x'"))  # cut short: no diff
        self.assertIsNone(explain.expected_actual("Target accepts VLAN ID 0"))


class GatesAndNotesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_rules(self):
        report = junit.parse(self._junit())
        run = reports.Run("r", "saivpp", T0, 12.5, Path("x"), None, None, "", report.tests)
        from sai_challenger_ui.core import catalog
        (self.dir / "test_poc_l2.py").write_text(SOURCE)
        cat = catalog.build(self.dir)
        prof = profiles.Profile("saivpp", Path("p"), {"expected_gaps": {"test_poc_l2_vlan_invalid_id_rejected[*]": "x"}})
        rules, note = gates.load_rules(self.dir)
        self.assertEqual(note, "")
        v = {r.id: r for r in gates.check(run, cat, prof, rules).rules}
        self.assertFalse(v["no-fail"].passed)
        self.assertEqual(v["no-fail"].keys, ["test_poc_l2::test_poc_l2_vlan_duplicate_rejected"])
        self.assertFalse(v["no-stale-gap"].passed)
        self.assertFalse(v["no-errors"].passed)
        self.assertTrue(v["gaps-in-profile"].passed)
        self.assertTrue(v["max-duration"].passed)

    def test_rules_file_and_bad_file(self):
        (self.dir / "gates.toml").write_text('[[rule]]\nid = "rate"\ntype = "min_pass_rate"\nmin = 0.5\ntitle = "Half pass"\n')
        rules, note = gates.load_rules(self.dir)
        self.assertEqual(([r["id"] for r in rules], note), (["rate"], ""))
        (self.dir / "gates.toml").write_text("not = [toml")
        rules, note = gates.load_rules(self.dir)
        self.assertEqual(rules, gates.DEFAULT_RULES)
        self.assertIn("can't be read", note)

    def test_gap_notes(self):
        self.assertEqual(gapnotes.get({}, "saivs", "p").kind, "limitation")
        gapnotes.save(self.dir, "saivs", "p", "bug", "https://example.com/1")
        gapnotes.save(self.dir, "saivs", "q", "temporary", until="2026-01-31")
        notes = gapnotes.load(self.dir)
        self.assertEqual((gapnotes.get(notes, "saivs", "p").link, gapnotes.get(notes, "saivs", "p").recorded),
                         ("https://example.com/1", True))
        q = gapnotes.get(notes, "saivs", "q")
        self.assertEqual(q.state(date(2026, 2, 1)), "overdue")
        self.assertEqual(q.state(date(2026, 1, 1)), "ok")
        for bad in ({"kind": "muted"}, {"kind": "bug", "link": "javascript:alert(1)"}, {"kind": "temporary", "until": "31/01"}):
            with self.assertRaises(gapnotes.BadNote):
                gapnotes.save(self.dir, "saivs", "p", bad["kind"], bad.get("link", ""), bad.get("until", ""))

    def _junit(self):
        p = self.dir / "r.xml"
        p.write_text(JUNIT)
        return p


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        poc = root / "tests" / "poc"
        (poc / "targets").mkdir(parents=True)
        (poc / "reports").mkdir()
        (poc / "targets" / "saivpp.json").write_text(
            '{"name": "saivpp", "testbed": "saivpp_standalone", "exec_args": ["-a", "vpp", "-t", "saivpp"],'
            ' "lock": "saivpp", "expected_gaps": {"test_poc_l2_vlan_invalid_id_rejected[*]": "accepts bad IDs"}}')
        (poc / "reports" / "saivpp-1117-103309.xml").write_text(JUNIT)
        (poc / "test_poc_l2.py").write_text(SOURCE)
        cls.root = root
        settings = Settings(sc_root=root, lock_dir=root / "locks", config_dir=root / "cfg", state_dir=root / "state",
                            facts={"saivpp": {"forwards_traffic": True}})
        cls.patch = mock.patch("sai_challenger_ui.core.testbed.containers",
                               return_value={"sc-vpp-saivpp-run": {"state": "running", "status": "Up 2 days"}})
        cls.patch.start()
        cls.client = TestClient(create_app(settings, dist=root / "nodist"), base_url="http://127.0.0.1:8770")

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        cls.tmp.cleanup()

    def get(self, path, **params):
        r = self.client.get(path, params=params)
        self.assertEqual(r.status_code, 200, (path, r.text[:300]))
        return r

    def test_run_page_has_marks_causes_gate(self):
        run = self.get("/api/runs/saivpp-1117-103309").json()
        self.assertEqual(run["marks"]["new"], sum(1 for t in run["tests"] if not t["upstream"] and t["result"] != "skipped"))
        self.assertFalse(run["gate"]["passed"])
        self.assertTrue(any(c["family"] == "setup" for c in run["causes"]))
        gap = next(t for t in run["tests"] if t["result"] == "gap_passes")
        self.assertEqual(gap["gap"]["pattern"], "test_poc_l2_vlan_invalid_id_rejected[*]")
        self.assertIn(gap["gap"]["note"]["kind"], gapnotes.KINDS)  # "bug" once the gap-note test has run

    def test_test_page_and_charts(self):
        page = self.get("/api/runs/saivpp-1117-103309/detail", key="test_poc_l2::test_poc_l2_vlan_duplicate_rejected").json()
        self.assertEqual(page["diff"], {"expected": "SAI_STATUS_ITEM_ALREADY_EXISTS", "actual": "SAI_STATUS_INVALID_PARAMETER"})
        self.assertTrue(any(k == "File" and v.startswith("test_poc_l2.py:") for k, v in page["labels"]))
        self.assertEqual(page["history"]["counted"], 1)
        self.assertEqual(page["targets"][0]["target"], "saivpp")
        charts = self.get("/api/runs/saivpp-1117-103309/charts").json()
        self.assertEqual(len(charts["dynamics"]), 1)

    def test_exports(self):
        md = self.get("/api/runs/saivpp-1117-103309/summary.md").text
        self.assertIn("# Run saivpp-1117-103309 on saivpp", md)
        self.assertIn("FAIL: VLAN duplicate rejected", md)
        self.assertIn("Expected: `SAI_STATUS_ITEM_ALREADY_EXISTS`", md)
        html = self.get("/api/runs/saivpp-1117-103309/export.html").text
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("Conformance gate", html)
        self.assertNotIn("<script", html)
        self.assertEqual(exports.pass_rate({"pass": 3, "fail": 1, "skipped": 4}), (3, 4))

    def test_gap_note_endpoint(self):
        body = {"target": "saivpp", "pattern": "test_poc_l2_vlan_invalid_id_rejected[*]", "kind": "bug", "link": "https://x.example/1"}
        self.assertEqual(self.client.post("/api/gaps/note", json=body).status_code, 403)  # no header
        r = self.client.post("/api/gaps/note", json=body, headers=HEADERS)
        self.assertEqual((r.status_code, r.json()["kind"]), (200, "bug"))
        self.assertEqual(self.client.post("/api/gaps/note", json={**body, "pattern": "nope"}, headers=HEADERS).status_code, 404)
        self.assertEqual(self.client.post("/api/gaps/note", json={**body, "kind": "muted"}, headers=HEADERS).status_code, 400)
        saved = json.loads((self.root / "cfg" / "gap_notes.json").read_text())
        self.assertEqual(saved["saivpp"]["test_poc_l2_vlan_invalid_id_rejected[*]"]["kind"], "bug")
        # The profile itself is never written.
        self.assertNotIn("bug", (self.root / "tests" / "poc" / "targets" / "saivpp.json").read_text())


FAKE_FLAKY_RUN_POC = r'''#!/usr/bin/env bash
# Stand-in for run_poc.sh: the first run fails test_poc_l2_vlan_readback, later runs pass it.
set -u
TARGET=$1; shift
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
N=$(cat "$ROOT/calls" 2>/dev/null || echo 0); N=$((N + 1)); echo $N > "$ROOT/calls"
echo "$@" > "$ROOT/args-$N.txt"
STAMP=$(date +%m%d-%H%M)$(printf %02d $N)
OUT=$ROOT/tests/poc/reports/$TARGET-$STAMP
if [ "$N" = 1 ]; then RES='<failure message="AssertionError: assert 1 == 2"/>'; else RES=''; fi
echo "collecting ... collected 1 items"
echo "poc_rajesh/test_poc_l2.py::test_poc_l2_vlan_readback PASSED [100%]"
cat > "$OUT.xml" <<EOF
<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" time="0.4"
 timestamp="2026-11-18T10:00:0${N}+00:00" hostname="fake">
<testcase classname="poc_rajesh.test_poc_l2" name="test_poc_l2_vlan_readback" time="0.3">$RES</testcase>
</testsuite></testsuites>
EOF
echo "report: $OUT.{html,xml}  exit=0"
exit 0
'''


class RetryTest(unittest.TestCase):
    def test_failing_tests_are_retried_until_they_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            poc = root / "tests" / "poc"
            (poc / "targets").mkdir(parents=True)
            (poc / "reports").mkdir()
            (poc / "test_poc_l2.py").write_text(L2)
            (poc / "test_poc_acl.py").write_text(ACL)
            (poc / "targets" / "saivpp.json").write_text(PROFILE % ("saivpp", "saivpp", '["-a", "vpp", "-t", "saivpp"]', "saivpp"))
            script = root / "scripts" / "poc" / "run_poc.sh"
            script.parent.mkdir(parents=True)
            script.write_text(FAKE_FLAKY_RUN_POC)
            script.chmod(0o755)
            (root / "locks").mkdir()
            settings = Settings(sc_root=root, lock_dir=root / "locks", config_dir=root / "cfg", state_dir=root / "state",
                                facts={"saivpp": {"forwards_traffic": True}}, user="rajesh")
            docker = {"sc-vpp-saivpp-run": {"state": "running", "status": "Up"}}
            with mock.patch("sai_challenger_ui.core.testbed.containers", return_value=docker), \
                    mock.patch("sai_challenger_ui.core.jobs.git_state", return_value=("abc1234", "main", [])), \
                    TestClient(create_app(settings, dist=root / "nodist"), base_url="http://127.0.0.1:8770") as client:
                r = client.post("/api/jobs", json={"targets": ["saivpp"], "what": "pick", "traffic": False, "retries": 2,
                                                   "tests": ["test_poc_l2::test_poc_l2_vlan_readback"]}, headers=HEADERS)
                self.assertEqual(r.status_code, 200, r.text)
                end = time.monotonic() + 15
                while time.monotonic() < end:
                    jobs = client.get("/api/jobs").json()
                    done = [j for j in jobs["recent"] if j["state"] == "done" and j["runId"]]
                    if len(done) == 2 and not jobs["active"]:
                        break
                    time.sleep(0.2)
                self.assertEqual(len(done), 2, jobs)
                second = next(j for j in done if j["attempt"] == 2)
                self.assertEqual(second["retryOf"], r.json()["jobs"][0])
                self.assertEqual((root / "args-2.txt").read_text().split(), ["poc_rajesh/test_poc_l2.py::test_poc_l2_vlan_readback"])
                first_run = next(j for j in done if j["attempt"] == 1)["runId"]
                run = client.get(f"/api/runs/{first_run}").json()
                self.assertEqual([a["attempt"] for a in run["retries"]["attempts"]], [1, 2])
                self.assertEqual([a["result"] for a in run["retries"]["tests"]["test_poc_l2::test_poc_l2_vlan_readback"]],
                                 ["fail", "pass"])
                time.sleep(0.5)
                self.assertEqual((root / "calls").read_text().strip(), "2")  # passed on retry 1: no third run
                self.assertEqual(client.post("/api/plan", json={"targets": ["saivpp"], "retries": 9}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
