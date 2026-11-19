"""API tests against a small synthetic SAI-Challenger tree (no testbed, no docker)."""
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

from test_core import JUNIT

from sai_challenger_ui.settings import Settings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

    from sai_challenger_ui.api.app import create_app

SOURCE = '''import pytest
pytestmark = pytest.mark.l2

def test_poc_l2_vlan_readback(npu):
    """The test VLAN reads back."""

def test_poc_l2_vlan_duplicate_rejected(npu):
    """Creating the test VLAN twice fails."""
    assert status == "SAI_STATUS_ITEM_ALREADY_EXISTS"

@pytest.mark.parametrize("bad_id", ["0", "4095"])
def test_poc_l2_vlan_invalid_id_rejected(npu, bad_id):
    pass
'''


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
        (poc / "reports" / "saivpp-1117-103309.html").write_text("<html>report</html>")
        (poc / "reports" / "tmpgap.xml").write_text("<x/>")
        (poc / "test_poc_l2.py").write_text(SOURCE)
        settings = Settings(sc_root=root, lock_dir=root / "locks", config_dir=root / "cfg",
                            facts={"saivpp": {"forwards_traffic": True}})
        cls.patch = mock.patch("sai_challenger_ui.core.testbed.containers",
                               return_value={"sc-vpp-saivpp-run": {"state": "running", "status": "Up 2 days"}})
        cls.patch.start()
        cls.client = TestClient(create_app(settings, dist=root / "nodist"))

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        cls.tmp.cleanup()

    def get(self, path, **params):
        r = self.client.get(path, params=params)
        self.assertEqual(r.status_code, 200, (path, r.text[:200]))
        return r.json()

    def test_health_and_targets(self):
        self.assertEqual(self.get("/api/health")["mode"], "local")
        t = self.get("/api/targets")["targets"][0]
        self.assertEqual((t["name"], t["state"]["kind"], t["container"]["status"]), ("saivpp", "ready", "Up 2 days"))
        self.assertEqual((t["forwardsTraffic"], t["forwardsSource"]), (True, "ui"))
        self.assertEqual(t["latest"]["id"], "saivpp-1117-103309")

    def test_runs_and_run_page(self):
        runs = self.get("/api/runs")
        self.assertEqual([r["id"] for r in runs["runs"]], ["saivpp-1117-103309"])  # tmpgap is not a run
        run = self.get("/api/runs/saivpp-1117-103309")
        self.assertEqual(run["headline"], "1 test fails · 2 setup errors · 1 cleanup error · 1 expected gap now passes")
        self.assertEqual([g["result"] for g in run["groups"]],
                         ["fail", "setup_error", "cleanup_error", "gap_passes", "expected_gap", "skipped", "pass"])
        self.assertEqual(sum(g["count"] for g in run["groups"]), 9)
        key = "test_poc_l2::test_poc_l2_vlan_duplicate_rejected"
        d = self.get("/api/runs/saivpp-1117-103309/detail", key=key)
        self.assertEqual(d["purpose"], "Creating the test VLAN twice fails.")
        self.assertIn("SAI_STATUS_ITEM_ALREADY_EXISTS", d["happened"])
        gap = self.get("/api/runs/saivpp-1117-103309/detail", key="test_poc_l2::test_poc_l2_vlan_invalid_id_rejected[4095]")
        self.assertEqual(gap["recorded"], {"pattern": "test_poc_l2_vlan_invalid_id_rejected[*]", "reason": "accepts bad IDs"})

    def test_compare_and_tests(self):
        m = self.get("/api/compare/matrix")
        self.assertEqual([c["target"] for c in m["columns"]], ["saivpp"])
        self.assertTrue(any(b["kind"] == "new_gap" for r in m["rows"] for b in r["badges"]))
        gaps = self.get("/api/compare/gaps")
        self.assertIn("| test_poc_l2_vlan_invalid_id_rejected", gaps["runbookMarkdown"].replace("`", ""))
        cat = self.get("/api/tests")
        names = [t["name"] for tr in cat["tracks"] for t in tr["tests"]]
        self.assertEqual(names, ["test_poc_l2_vlan_readback", "test_poc_l2_vlan_duplicate_rejected",
                                 "test_poc_l2_vlan_invalid_id_rejected"])
        hist = self.get("/api/tests/history", module="test_poc_l2", name="test_poc_l2_vlan_invalid_id_rejected")
        self.assertEqual(hist["saivpp"]["gap"]["pattern"], "test_poc_l2_vlan_invalid_id_rejected[*]")

    def test_refusals(self):
        for path in ("/api/runs/nope", "/api/runs/nope/detail?key=x", "/api/runs/saivpp-1117-103309/report/../../x",
                     "/api/runs/saivpp-1117-103309/report/pdf", "/api/compare/diff"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        self.assertEqual(self.client.get("/api/runs/saivpp-1117-103309/report/html").text, "<html>report</html>")


if __name__ == "__main__":
    unittest.main()
