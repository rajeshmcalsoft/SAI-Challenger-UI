"""Starting runs: the planner, the console reader and the job runner.

Host only. The runner tests use a fake scripts/poc/run_poc.sh inside a temporary tree, so no target, container,
exec.sh or real lock file is ever touched.
"""
import fcntl
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from unittest import mock

from sai_challenger_ui.core import catalog, console, selection
from sai_challenger_ui.core.vocab import Result
from sai_challenger_ui.settings import Settings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

    from sai_challenger_ui.api.app import create_app

L2 = '''import pytest
pytestmark = pytest.mark.l2

def test_poc_l2_vlan_readback(npu):
    """The test VLAN reads back."""

@pytest.mark.parametrize("bad_id", ["0", "4095"])
def test_poc_l2_vlan_invalid_id_rejected(npu, bad_id):
    pass

@pytest.mark.traffic
def test_poc_l2_broadcast_flood(npu, dataplane):
    pass
'''

ACL = '''import pytest
pytestmark = pytest.mark.acl

class TestPocAclDrop:
    @step("l2")
    def test_poc_acl_drop_01_l2_configured(self, npu, st):
        pass

    @step("table")
    def test_poc_acl_drop_02_table_created(self, npu, st):
        pass

    @step("entries", needs=["table"])
    def test_poc_acl_drop_03_entries_created(self, npu, st):
        pass

    @step("bound", needs=["entries", "l2"])
    def test_poc_acl_drop_04_bound(self, npu, st):
        pass
'''

PROFILE = ('{"name": "%s", "testbed": "%s_standalone", "exec_args": %s, "lock": "%s",'
           ' "expected_gaps": {"test_poc_l2_vlan_invalid_id_rejected[4095]": "Target accepts VLAN ID 4095"}}')

CONSOLE = """Waiting for the saivpp lock...
============================= test session starts ==============================
platform linux -- Python 3.11.2, pytest-9.1.1, pluggy-1.6.0 -- /usr/bin/python3
poc target profile: saivpp | mld filter: on
collecting ... collected 9 items / 1 deselected / 8 selected

poc_rajesh/test_poc_acl.py::TestPocAclDrop::test_poc_acl_drop_01_l2_configured PASSED [ 12%]
poc_rajesh/test_poc_acl.py::TestPocAclDrop::test_poc_acl_drop_01_l2_configured ERROR [ 12%]
poc_rajesh/test_poc_acl.py::TestPocAclDrop::test_poc_acl_drop_02_table_created SKIPPED (needs step(s) that did not pass: l2) [ 25%]
poc_rajesh/test_poc_l2.py::test_poc_l2_vlan_readback PASSED                [ 37%]
poc_rajesh/test_poc_l2.py::test_poc_l2_vlan_invalid_id_rejected[0] FAILED  [ 50%]
poc_rajesh/test_poc_l2.py::test_poc_l2_vlan_invalid_id_rejected[4095] PASSED (Target accepts VLAN ID 4095 (returned SUCCESS)) [ 62%]
poc_rajesh/test_poc_l2.py::test_poc_l2_vlan_invalid_id_rejected[4096] PASSED [ 75%]
poc_rajesh/test_poc_counters.py::test_poc_counters_clear_read ERROR        [ 87%]
poc_rajesh/test_poc_l2_traffic.py::test_poc_l2_access_to_trunk_tag_push """


class ConsoleTest(unittest.TestCase):
    def setUp(self):
        gaps = {"test_poc_l2_vlan_invalid_id_rejected[0]": "Target accepts VLAN ID 0",
                "test_poc_l2_vlan_invalid_id_rejected[4096]": "Target accepts VLAN ID 4096"}
        self.p = console.parse(CONSOLE, gaps)
        self.by_name = {t.name: t for t in self.p.tests}

    def test_progress(self):
        p = self.p
        self.assertFalse(p.waiting)
        self.assertTrue(p.started)
        self.assertEqual((p.collected, p.done), (8, 7))
        self.assertEqual(p.current, "poc_rajesh/test_poc_l2_traffic.py::test_poc_l2_access_to_trunk_tag_push")
        self.assertEqual(p.profile_line, "poc target profile: saivpp | mld filter: on")

    def test_words(self):
        b = self.by_name
        self.assertIs(b["test_poc_l2_vlan_readback"].result, Result.PASS)
        self.assertIs(b["test_poc_l2_vlan_invalid_id_rejected[0]"].result, Result.GAP_PASSES)  # strict XPASS
        gap = b["test_poc_l2_vlan_invalid_id_rejected[4095]"]  # printed as PASSED by the conftest, with its reason
        self.assertEqual((gap.result, gap.message), (Result.EXPECTED_GAP, "Target accepts VLAN ID 4095 (returned SUCCESS)"))
        self.assertIs(b["test_poc_l2_vlan_invalid_id_rejected[4096]"].result, Result.EXPECTED_GAP)  # reason cut off
        self.assertIs(b["test_poc_counters_clear_read"].result, Result.SETUP_ERROR)
        teardown = b["test_poc_acl_drop_01_l2_configured"]
        self.assertEqual((teardown.result, teardown.cleanup_failed), (Result.CLEANUP_ERROR, True))
        skipped = b["test_poc_acl_drop_02_table_created"]
        self.assertEqual((skipped.result, skipped.message), (Result.SKIPPED, "needs step(s) that did not pass: l2"))
        self.assertEqual((teardown.module, teardown.cls, teardown.upstream), ("test_poc_acl", "TestPocAclDrop", False))

    def test_waiting_and_end(self):
        self.assertTrue(console.parse("Waiting for the saivs lock...\n").waiting)
        end = console.parse(CONSOLE + "PASSED [100%]\n== 8 passed ==\n"
                            "report: /home/u/SAI-Challenger/tests/poc/reports/saivpp-1118-101500.{html,xml}  exit=1\n")
        self.assertEqual((end.report, end.exit_code, end.current), ("saivpp-1118-101500", 1, None))

    def test_upstream_node(self):
        p = console.parse("ut/test_vlan_ut.py::TestVlan::test_vlan_create PASSED [ 50%]\n",
                          {"test_vlan_create": "never applies upstream"})
        t = p.tests[0]
        self.assertEqual((t.module, t.cls, t.upstream, t.result), ("ut/test_vlan_ut", "TestVlan", True, Result.PASS))


def _tree(root):
    poc = root / "tests" / "poc"
    (poc / "targets").mkdir(parents=True)
    (poc / "reports").mkdir()
    (poc / "test_poc_acl.py").write_text(ACL)
    (poc / "test_poc_l2.py").write_text(L2)
    for name, args in (("saivpp", '["-a", "vpp", "-t", "saivpp"]'), ("saivs", '["-t", "saivs"]')):
        (poc / "targets" / f"{name}.json").write_text(PROFILE % (name, name, args, name))
    return poc


class SelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        poc = _tree(Path(cls.tmp.name))
        cls.cat = catalog.build(poc)
        from sai_challenger_ui.core import profiles
        cls.profs = profiles.load_all(poc / "targets")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def plan(self, **kw):
        req = selection.Request.from_json({"targets": ["saivpp", "saivs"], **kw})
        fwd = {"saivpp": True, "saivs": False}
        return selection.plan(req, self.cat, self.profs, fwd.get, lambda name: None, [], "rajesh")

    def test_full_suite(self):
        vpp, vs = self.plan()
        self.assertEqual(vpp.command, "scripts/poc/run_poc.sh saivpp poc_rajesh --traffic")
        self.assertEqual(vs.command, "scripts/poc/run_poc.sh saivs poc_rajesh")
        self.assertEqual((vpp.count, vpp.gaps, vpp.traffic_tests), (8, 1, 1))
        self.assertEqual(vs.traffic_note, "saivs doesn't forward packets: its 1 traffic test will be skipped.")
        self.assertTrue(vpp.mld_relevant)
        self.assertEqual(vpp.expected[:2], ["test_poc_acl::TestPocAclDrop::test_poc_acl_drop_01_l2_configured",
                                            "test_poc_acl::TestPocAclDrop::test_poc_acl_drop_02_table_created"])

    def test_tracks_use_fixed_markers(self):
        vpp, _ = self.plan(what="tracks", tracks=["l2"], mld="off")
        self.assertEqual(vpp.args, ["poc_rajesh", "-m", "l2", "--traffic", "--mld-filter", "off"])
        self.assertEqual((vpp.what, vpp.count), ("Tracks: L2", 4))
        with self.assertRaises(selection.BadRequest):
            self.plan(what="tracks", tracks=["l2 or not l3"])

    def test_pick_sorts_into_file_order_and_adds_needs(self):
        vpp, _ = self.plan(what="pick", traffic=False, tests=[
            "test_poc_l2::test_poc_l2_vlan_invalid_id_rejected[4095]",
            "test_poc_acl::TestPocAclDrop::test_poc_acl_drop_03_entries_created",
        ])
        self.assertEqual(vpp.args, [
            "poc_rajesh/test_poc_acl.py::TestPocAclDrop::test_poc_acl_drop_02_table_created",
            "poc_rajesh/test_poc_acl.py::TestPocAclDrop::test_poc_acl_drop_03_entries_created",
            "poc_rajesh/test_poc_l2.py::test_poc_l2_vlan_invalid_id_rejected[4095]",
        ])
        self.assertEqual(vpp.warnings, ["ACL drop scenario: added step 02, which the picked steps need."])
        self.assertEqual((vpp.count, vpp.gaps), (3, 1))
        # Step 04 needs 01, 02 and 03 (through 03's needs): that is the whole file, so the file is passed.
        vpp, _ = self.plan(what="pick", traffic=False, tests=["test_poc_acl::TestPocAclDrop::test_poc_acl_drop_04_bound"])
        self.assertEqual(vpp.args, ["poc_rajesh/test_poc_acl.py"])
        self.assertEqual(vpp.warnings, ["ACL drop scenario: added steps 01, 02 and 03, which the picked steps need."])

    def test_pick_whole_file_folds(self):
        vpp, _ = self.plan(what="pick", traffic=False, tests=[
            "test_poc_l2::test_poc_l2_vlan_readback", "test_poc_l2::test_poc_l2_vlan_invalid_id_rejected",
            "test_poc_l2::test_poc_l2_broadcast_flood"])
        self.assertEqual(vpp.args, ["poc_rajesh/test_poc_l2.py"])

    def test_refuses_what_it_doesnt_know(self):
        for bad in ({"what": "pick", "tests": ["test_poc_l2::test_nope"]},
                    {"what": "pick", "tests": ["test_poc_l2::test_poc_l2_vlan_invalid_id_rejected[9]"]},
                    {"what": "pick", "tests": ["test_poc_l2::test_poc_l2_vlan_readback; rm -rf ~"]},
                    {"targets": ["../../etc"]}, {"mld": "maybe"}, {"repeat": 9}, {"what": "shell"}):
            with self.assertRaises(selection.BadRequest, msg=bad):
                req = selection.Request.from_json({"targets": ["saivs"], **bad})
                selection.plan(req, self.cat, self.profs, lambda n: False, lambda n: None, [], "rajesh")


FAKE_RUN_POC = r'''#!/usr/bin/env bash
# Stand-in for scripts/poc/run_poc.sh in unit tests: prints what the real one prints and writes a JUnit file.
set -u
TARGET=$1; shift
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
STAMP=$(date +%m%d-%H%M%S)
OUT=$ROOT/tests/poc/reports/$TARGET-$STAMP
echo "$@" > "$ROOT/args-$TARGET.txt"
echo "Waiting for the $TARGET lock..."
echo "============================= test session starts =============================="
echo "poc target profile: $TARGET | mld filter: off"
echo "collecting ... collected 2 items"
echo
printf 'poc_rajesh/test_poc_l2.py::test_poc_l2_vlan_readback '
sleep 0.3
echo "PASSED [ 50%]"
echo "poc_rajesh/test_poc_l2.py::test_poc_l2_vlan_invalid_id_rejected[4095] PASSED (Target accepts VLAN ID 4095) [100%]"
cat > "$OUT.xml" <<EOF
<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" time="0.4"
 timestamp="2026-11-18T10:00:00+00:00" hostname="fake">
<testcase classname="poc_rajesh.test_poc_l2" name="test_poc_l2_vlan_readback" time="0.3"/>
<testcase classname="poc_rajesh.test_poc_l2" name="test_poc_l2_vlan_invalid_id_rejected[4095]" time="0.1">
<skipped type="pytest.xfail" message="Target accepts VLAN ID 4095"/></testcase>
</testsuite></testsuites>
EOF
echo "report: $OUT.{html,xml}  exit=0"
exit 0
'''

HEADERS = {"X-SAI-Challenger-UI": "1", "Content-Type": "application/json"}


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _tree(self.root)
        script = self.root / "scripts" / "poc" / "run_poc.sh"
        script.parent.mkdir(parents=True)
        script.write_text(FAKE_RUN_POC)
        script.chmod(0o755)
        (self.root / "locks").mkdir()
        self.settings = Settings(sc_root=self.root, lock_dir=self.root / "locks", config_dir=self.root / "cfg",
                                 state_dir=self.root / "state", facts={"saivpp": {"forwards_traffic": True}},
                                 user="rajesh")
        self.docker = mock.patch("sai_challenger_ui.core.testbed.containers", return_value={
            "sc-vpp-saivpp-run": {"state": "running", "status": "Up"},
            "sc-trident2-saivs-run": {"state": "exited", "status": "Exited (0)"}})
        self.docker.start()
        self.git = mock.patch("sai_challenger_ui.core.jobs.git_state", return_value=("7828109", "poc/integration", []))
        self.git.start()

    def tearDown(self):
        self.git.stop()
        self.docker.stop()
        self.tmp.cleanup()

    def client(self):
        return TestClient(create_app(self.settings, dist=self.root / "nodist"), base_url="http://127.0.0.1:8770")

    def wait_for(self, client, job_id, states, timeout=10.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["state"] in states:
                return job
            time.sleep(0.1)
        self.fail(f"{job_id} never reached {states}: {job}")

    def test_run_end_to_end(self):
        with self.client() as client:
            plan = client.post("/api/plan", json={"targets": ["saivpp", "saivs"]}).json()["targets"]
            self.assertEqual(plan[1]["blocked"], "Container stopped (ask the testbed admin)")
            r = client.post("/api/jobs", json={"targets": ["saivpp", "saivs"], "what": "tracks", "tracks": ["l2"]},
                            headers=HEADERS)
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertEqual(body["skipped"], [{"target": "saivs", "why": "Container stopped (ask the testbed admin)"}])
            (job_id,) = body["jobs"]
            job = self.wait_for(client, job_id, ("done",))
            self.assertEqual((job["exitCode"], job["note"], job["commit"]), (0, "", "7828109"))
            self.assertEqual((self.root / "args-saivpp.txt").read_text().split(), ["poc_rajesh", "-m", "l2", "--traffic"])
            run = client.get(f"/api/runs/{job['runId']}").json()
            self.assertEqual((run["source"], run["headline"]), ("UI", "Pass except 1 expected gap"))
            self.assertEqual(run["job"]["command"], "scripts/poc/run_poc.sh saivpp poc_rajesh -m l2 --traffic")
            con = client.get(f"/api/jobs/{job_id}/console").json()
            self.assertIn("test session starts", con["text"])
            self.assertFalse(con["active"])
            self.assertEqual(client.get("/api/jobs").json()["recent"][0]["id"], job_id)
            # Nothing of the UI's own lands in the checkout: only what run_poc.sh wrote.
            self.assertEqual(sorted(p.suffix for p in (self.root / "tests" / "poc" / "reports").iterdir()), [".xml"])
            self.assertTrue((self.root / "state" / "jobs" / f"{job_id}.log").is_file())

    def test_waits_while_someone_holds_the_lock(self):
        lock = open(self.root / "locks" / "saivpp.lock", "w")  # noqa: SIM115 - held for the whole test
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with self.client() as client:
                plan = client.post("/api/plan", json={"targets": ["saivpp"]}).json()["targets"][0]
                self.assertIn("This run will queue", plan["queue"])
                (job_id,) = client.post("/api/jobs", json={"targets": ["saivpp"]}, headers=HEADERS).json()["jobs"]
                time.sleep(0.5)
                job = client.get(f"/api/jobs/{job_id}").json()
                self.assertEqual(job["state"], "queued")
                self.assertEqual(job["waiting"]["kind"], "lock")
                self.assertIn("holds the lock", job["waiting"]["text"])
                self.assertEqual(client.delete(f"/api/jobs/{job_id}", headers=HEADERS).status_code, 200)
                self.assertEqual(client.get(f"/api/jobs/{job_id}").json()["state"], "removed")
                self.assertFalse((self.root / "args-saivpp.txt").exists())  # run_poc.sh never started
        finally:
            lock.close()

    def test_guard(self):
        with self.client() as client:
            body = {"targets": ["saivpp"]}
            self.assertEqual(client.post("/api/jobs", json=body).status_code, 403)  # no header
            self.assertEqual(client.post("/api/jobs", json=body, headers={**HEADERS, "Origin": "https://evil.example"})
                             .status_code, 403)
            self.assertEqual(client.post("/api/jobs", json=body, headers={**HEADERS, "Host": "evil.example"})
                             .status_code, 403)
            self.assertEqual(client.post("/api/jobs", content="targets=saivpp",
                                         headers={"X-SAI-Challenger-UI": "1", "Content-Type": "text/plain"}).status_code, 415)
            self.assertEqual(client.post("/api/jobs", json={"targets": ["saivs"]}, headers=HEADERS).status_code, 409)
            self.assertFalse((self.root / "args-saivpp.txt").exists())

    def test_one_server_owns_the_runs(self):
        with self.client() as first, self.client() as second:
            self.assertTrue(first.get("/api/health").json()["canRun"])
            self.assertFalse(second.get("/api/health").json()["canRun"])
            r = second.post("/api/jobs", json={"targets": ["saivpp"]}, headers=HEADERS)
            self.assertEqual(r.status_code, 409)
            (job_id,) = first.post("/api/jobs", json={"targets": ["saivpp"]}, headers=HEADERS).json()["jobs"]
            self.wait_for(first, job_id, ("done",))
            self.assertEqual(second.get(f"/api/jobs/{job_id}").json()["state"], "done")  # the other one can show it

    def test_restart_drops_queued_runs(self):
        from sai_challenger_ui.core import jobs
        store = jobs.Store(self.root / "state" / "jobs")
        store.save(jobs.Job(id="saivpp-20261118-100000-ui1", target="saivpp", lock="saivpp", args=["poc_rajesh"],
                            command="x", what="Full PoC suite", expected=[], count=0, traffic=False, mld="auto",
                            who="rajesh", created=jobs.now_iso()))
        with self.client() as client:
            job = client.get("/api/jobs/saivpp-20261118-100000-ui1").json()
            self.assertEqual(job["state"], "removed")
            self.assertIn("stopped before this run started", job["note"])
            self.assertFalse((self.root / "args-saivpp.txt").exists())


if __name__ == "__main__":
    unittest.main()
