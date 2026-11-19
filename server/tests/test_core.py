"""Unit tests for the core model on synthetic input. Host only: no target, no container, no lock."""
import os
import re
import tempfile
import textwrap
import unittest
from pathlib import Path

from sai_challenger_ui.core import catalog, explain, junit, profiles, reports, testbed
from sai_challenger_ui.core.vocab import Result, count_line, empty_counts, headline

R = Result


def counts(**kw):
    c = empty_counts()
    for k, v in kw.items():
        c[Result(k)] = v
    return c


class VocabTest(unittest.TestCase):
    def test_headline_attention_order(self):
        self.assertEqual(headline(counts(fail=1, setup_error=1, gap_passes=2, **{"pass": 3})),
                         "1 test fails · 1 setup error · 2 expected gaps now pass")
        self.assertEqual(headline(counts(fail=3)), "3 tests fail")
        self.assertEqual(headline(counts(gap_passes=1)), "1 expected gap now passes")

    def test_headline_clean(self):
        self.assertEqual(headline(counts(**{"pass": 41}, expected_gap=6, skipped=14)), "Pass except 6 expected gaps")
        self.assertEqual(headline(counts(**{"pass": 2})), "Pass")
        self.assertEqual(headline(counts(skipped=4)), "Nothing ran · 4 skipped")
        self.assertEqual(headline(empty_counts()), "No tests ran")

    def test_count_line(self):
        self.assertEqual(count_line(counts(**{"pass": 41}, expected_gap=6, fail=1, skipped=14)),
                         "41 pass · 6 expected gaps · 1 fail · 14 skipped")
        self.assertEqual(count_line(counts(fail=2)), "0 pass · 2 fail")


JUNIT = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" time="12.5"
 timestamp="2026-11-17T10:33:12.574965+00:00" hostname="h1">
<testcase classname="poc_rajesh.test_poc_l2" name="test_poc_l2_vlan_readback" time="0.5"/>
<testcase classname="poc_rajesh.test_poc_l2" name="test_poc_l2_vlan_duplicate_rejected" time="0.4">
  <failure message="AssertionError: assert 'SAI_STATUS_INVALID_PARAMETER' == 'SAI_STATUS_I...LREADY_EXISTS'">
  - SAI_STATUS_ITEM_ALREADY_EXISTS
  + SAI_STATUS_INVALID_PARAMETER</failure></testcase>
<testcase classname="poc_rajesh.test_poc_l2" name="test_poc_l2_vlan_invalid_id_rejected[4095]" time="0.1">
  <skipped type="pytest.xfail" message="Target accepts VLAN ID 4095"/></testcase>
<testcase classname="poc_rajesh.test_poc_l2" name="test_poc_l2_vlan_invalid_id_rejected[0]" time="0.1">
  <failure message="[XPASS(strict)] Target accepts VLAN ID 0"/></testcase>
<testcase classname="poc_rajesh.test_poc_l2_traffic" name="test_poc_l2_broadcast_flood" time="0.0">
  <skipped type="pytest.skip" message="needs --traffic on a forwarding target"/></testcase>
<testcase classname="poc_rajesh.test_poc_counters" name="test_poc_counters_clear_read" time="0.0">
  <error message="failed on setup with &quot;TypeError: 'function' object is not subscriptable&quot;">tb</error></testcase>
<testcase classname="poc_rajesh.test_poc_acl.TestPocAclDrop" name="test_poc_acl_drop_01_l2_configured" time="1.0"/>
<testcase classname="poc_rajesh.test_poc_acl.TestPocAclDrop" name="test_poc_acl_drop_01_l2_configured" time="0.2">
  <error message="failed on teardown with &quot;AssertionError: cleanup left objects behind&quot;"/></testcase>
<testcase classname="ut.test_bridge_ut.TestBridgePort" name="test_bridge_port_create" time="0.3"/>
<testcase classname="" name="poc_rajesh.test_poc_l3" time="0.0"><error message="collection failure">SyntaxError</error></testcase>
</testsuite></testsuites>"""


class JunitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name, "saivpp-1117-103309.xml")
        self.path.write_text(JUNIT)
        self.report = junit.parse(self.path)
        self.by_name = {t.name: t for t in self.report.tests}

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_result(self):
        b = self.by_name
        self.assertIs(b["test_poc_l2_vlan_readback"].result, R.PASS)
        self.assertIs(b["test_poc_l2_vlan_duplicate_rejected"].result, R.FAIL)
        self.assertIs(b["test_poc_l2_vlan_invalid_id_rejected[4095]"].result, R.EXPECTED_GAP)
        self.assertEqual(b["test_poc_l2_vlan_invalid_id_rejected[4095]"].message, "Target accepts VLAN ID 4095")
        self.assertIs(b["test_poc_l2_vlan_invalid_id_rejected[0]"].result, R.GAP_PASSES)
        self.assertEqual(b["test_poc_l2_vlan_invalid_id_rejected[0]"].message, "Target accepts VLAN ID 0")
        self.assertIs(b["test_poc_l2_broadcast_flood"].result, R.SKIPPED)
        setup = b["test_poc_counters_clear_read"]
        self.assertIs(setup.result, R.SETUP_ERROR)
        self.assertEqual(setup.message, "TypeError: 'function' object is not subscriptable")

    def test_pass_then_teardown_error_is_one_cleanup_error(self):
        t = self.by_name["test_poc_acl_drop_01_l2_configured"]
        self.assertIs(t.result, R.CLEANUP_ERROR)
        self.assertTrue(t.cleanup_failed)
        self.assertAlmostEqual(t.seconds, 1.2)
        self.assertEqual(t.cls, "TestPocAclDrop")
        self.assertEqual(t.key, "test_poc_acl::TestPocAclDrop::test_poc_acl_drop_01_l2_configured")

    def test_upstream_and_collection(self):
        up = self.by_name["test_bridge_port_create"]
        self.assertTrue(up.upstream)
        self.assertEqual((up.module, up.cls), ("ut/test_bridge_ut", "TestBridgePort"))
        coll = self.by_name["(collection)"]
        self.assertIs(coll.result, R.SETUP_ERROR)
        self.assertEqual(coll.module, "test_poc_l3")
        self.assertFalse(coll.upstream)

    def test_params_and_report_fields(self):
        t = self.by_name["test_poc_l2_vlan_invalid_id_rejected[4095]"]
        self.assertEqual((t.base, t.param), ("test_poc_l2_vlan_invalid_id_rejected", "4095"))
        self.assertEqual(self.report.hostname, "h1")
        self.assertEqual(len(self.report.tests), 9)  # 10 testcases; the teardown error merges into its test


class ReportsTest(unittest.TestCase):
    def test_parse_stem(self):
        known = ("saivs", "saivs-thrift", "saivpp")
        self.assertEqual(reports.parse_stem("saivs-thrift-1117-103055", known), ("saivs-thrift", "1117-103055"))
        self.assertEqual(reports.parse_stem("saivs-1005-1037", known), ("saivs", "1005-1037"))
        self.assertEqual(reports.parse_stem("saivpp-20261118-140200", known), ("saivpp", "20261118-140200"))
        self.assertEqual(reports.parse_stem("acme-x1-1118-120000", known), ("acme-x1", "1118-120000"))
        for junk in ("tmpgap", "test_poc_l2_mac_learning", "test_scratch_pcap"):
            self.assertIsNone(reports.parse_stem(junk, known))

    def test_stamp_year_from_file_date(self):
        jan_2027 = 1798761600  # 2027-01-01 UTC
        self.assertEqual(reports.stamp_time("1231-235900", jan_2027).year, 2026)
        self.assertEqual(reports.stamp_time("0101-0001", jan_2027).year, 2027)

    def test_index_since_and_previous(self):
        with tempfile.TemporaryDirectory() as d:
            # The day before, the duplicate-VLAN test passed.
            old = re.sub(r'(name="test_poc_l2_vlan_duplicate_rejected" time="0.4">)\s*<failure.*?</failure>', r"\1",
                         JUNIT.replace("2026-11-17T10:33", "2026-11-16T09:00"), flags=re.DOTALL)
            Path(d, "saivpp-1116-090000.xml").write_text(old)
            Path(d, "saivpp-1117-103309.xml").write_text(JUNIT)
            Path(d, "tmpgap.xml").write_text("<not-a-run/>")
            idx = reports.RunIndex(d, ("saivpp",))
            runs = idx.refresh()
            self.assertEqual([r.id for r in runs], ["saivpp-1117-103309", "saivpp-1116-090000"])
            prev = idx.previous(runs[0])
            self.assertEqual(prev.id, "saivpp-1116-090000")
            diff = reports.since(prev, runs[0])
            self.assertIn("test_poc_l2::test_poc_l2_vlan_duplicate_rejected", diff.new_failures)
            self.assertEqual(diff.text, "1 new failure")


class ProfilesTest(unittest.TestCase):
    def test_gap_rule(self):
        m = profiles.gap_matches
        self.assertTrue(m("t_rejected[4095]", "t_rejected[4095]"))
        self.assertFalse(m("t_rejected[4096]", "t_rejected[4095]"))
        self.assertTrue(m("t_rejected[4096]", "t_rejected[*]"))
        self.assertFalse(m("t_rejected", "t_rejected[*]"))
        self.assertTrue(m("test_poc_l2_x", "test_poc_l2_*"))
        self.assertFalse(m("t_rejected[4]", "t_rejected[0-9]"))  # '[' is literal, not a set

    def test_duplicates_and_statuses(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "saivpp.json")
            p.write_text(textwrap.dedent("""\
                {"name": "saivpp", "lock": "saivpp", "expected_gaps": {
                  "a[*]": "accepts bad IDs", "b": "first", "b": "second", "c": "never runs", "zz_*": "nothing"}}"""))
            prof = profiles.load_profile(p)
            self.assertEqual(prof.duplicates, ["b"])
            self.assertEqual(prof.expected_gaps["b"], "second")
            T = junit.TestResult
            run = [T("m::a[0]", "m", None, "a[0]", R.EXPECTED_GAP, 0), T("m::a[1]", "m", None, "a[1]", R.GAP_PASSES, 0),
                   T("m::b", "m", None, "b", R.FAIL, 0), T("m::x", "m", None, "x", R.EXPECTED_GAP, 0)]
            st = {g.pattern: g for g in profiles.gap_statuses(prof, run, ["a[0]", "a[1]", "b", "c", "x"])}
            self.assertEqual(st["a[*]"].status, "now_passes")
            self.assertEqual(st["b"].status, "not_applied")
            self.assertTrue(st["b"].listed_twice)
            self.assertEqual(st["c"].status, "not_run")
            self.assertTrue(st["zz_*"].matches_no_test)
            self.assertEqual([t.name for t in profiles.unrecorded_gaps(prof, run)], ["x"])

    def test_unreadable_profile(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "bad.json")
            p.write_text("{nope")
            self.assertIn("can't read", profiles.load_profile(p).error)


SOURCE = '''\
import pytest
pytestmark = [pytest.mark.l2]

@pytest.mark.negative
@pytest.mark.parametrize("bad_id", ["0", "4095", 7])
def test_poc_l2_vlan_invalid_id_rejected(npu, poc_ports, bad_id):
    """Invalid VLAN IDs are refused."""
    poc_ports(2)

@pytest.mark.traffic
def test_poc_l2_vrf_create_readback(npu, poc_ports):
    poc_ports(3)

@pytest.mark.parametrize("frame", FRAMES)
def test_poc_l2_from_data(frame):
    pass

class TestPocAclDrop:
    @step("l2")
    def test_poc_acl_drop_01_l2_configured(self, st): pass
    @step("baseline", needs=["l2"])
    def test_poc_acl_drop_02_baseline(self, st): pass
'''


class CatalogTest(unittest.TestCase):
    def test_build(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "test_poc_l2.py").write_text(SOURCE)
            Path(d, "test_acl_exp.py").write_text("".join(f"def test_{i:02d}_step_{i}(st): pass\n" for i in range(1, 4)))
            cat = catalog.build(d)
        t = {x.name: x for x in cat.tests}
        bad = t["test_poc_l2_vlan_invalid_id_rejected"]
        self.assertEqual(bad.variants, ["0", "4095", "7"])
        self.assertEqual((bad.kind, bad.level, bad.ports_needed, bad.track), ("negative", "L1", 2, "A · L2 & VLANs"))
        self.assertEqual(bad.purpose, "Invalid VLAN IDs are refused.")
        self.assertEqual(t["test_poc_l2_vrf_create_readback"].level, "L2 traffic")
        self.assertEqual(t["test_poc_l2_vrf_create_readback"].title, "VRF create and read back")
        self.assertEqual(t["test_poc_l2_from_data"].variants, [])  # filled from history later
        self.assertEqual(t["test_poc_acl_drop_02_baseline"].step, {"name": "baseline", "needs": ["l2"]})
        titles = sorted(s.title for s in cat.scenarios)
        self.assertEqual(titles, ["ACL drop scenario", "ACL experiment"])

    def test_readable(self):
        r = catalog.readable
        self.assertEqual(r("test_poc_acl_table_create_remove"), "ACL table create and remove")
        self.assertEqual(r("test_07_drop_port_is_dropped"), "Step 07: drop port is dropped")
        self.assertEqual(r("test_poc_acl_drop_06_drop_port_is_dropped"), "Step 06: drop port is dropped")
        self.assertEqual(r("test_poc_l2_vlan_invalid_id_rejected[4095]"), "VLAN invalid ID rejected")


class ExplainTest(unittest.TestCase):
    def test_what_happened(self):
        w = explain.what_happened
        self.assertEqual(
            w(R.FAIL, "AssertionError: assert 'SAI_STATUS_INVALID_PARAMETER' == 'SAI_STATUS_I...LREADY_EXISTS'",
              "  - SAI_STATUS_ITEM_ALREADY_EXISTS\n  + SAI_STATUS_INVALID_PARAMETER"),
            "The target returned SAI_STATUS_INVALID_PARAMETER. The SAI spec expects SAI_STATUS_ITEM_ALREADY_EXISTS.")
        self.assertEqual(w(R.FAIL, "AssertionError: Operation failed due to SAI_STATUS_ITEM_NOT_FOUND"),
                         "The target returned SAI_STATUS_ITEM_NOT_FOUND.")
        self.assertEqual(w(R.FAIL, "AssertionError: A packet was received on device 0, port 2, but we expected no packets."),
                         "A packet arrived on port 2 where none was expected.")
        self.assertIsNone(w(R.PASS, ""))

    def test_hints(self):
        h = explain.Hints()
        self.assertEqual(h.match(R.SETUP_ERROR, "TypeError: 'function' object is not subscriptable").id, "poc-ports-factory")
        mld = "A packet was received on device 0, port 0, but we expected no packets.\n=== RECEIVED ===\n0000  33 33 00 00 00 16"
        self.assertEqual(h.match(R.FAIL, mld).id, "mld-frame")
        self.assertEqual(h.match(R.GAP_PASSES, "Target accepts VLAN ID 0").id, "gap-now-passes")
        dup = "assert 'SAI_STATUS_INVALID_PARAMETER' == 'SAI_STATUS_I...LREADY_EXISTS'\n - SAI_STATUS_ITEM_ALREADY_EXISTS"
        self.assertIsNone(h.match(R.FAIL, dup))  # a spec check on ALREADY_EXISTS is not left-over objects
        self.assertIsNone(h.match(R.PASS, "anything"))


class TestbedTest(unittest.TestCase):
    def test_container_names(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "npu/broadcom/trident2/saivs").mkdir(parents=True)
            self.assertEqual(testbed.container_name([], d), "sc-trident2-saivs-run")
            self.assertEqual(testbed.container_name(["-s", "thrift"], d), "sc-thrift-trident2-saivs-run")
            self.assertEqual(testbed.container_name(["-a", "vpp", "-t", "saivpp"], d), "sc-vpp-saivpp-run")

    def test_lock_holder_from_proc_locks(self):
        with tempfile.TemporaryDirectory() as d:
            lock = Path(d, "saivs.lock")
            lock.touch()
            st = lock.stat()
            dev = f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}"
            fake = Path(d, "locks")
            fake.write_text(f"1: FLOCK  ADVISORY  WRITE {os.getpid()} {dev} 0 EOF\n"
                            f"1: -> FLOCK  ADVISORY  WRITE 1 {dev} 0 EOF\n"
                            f"2: FLOCK  ADVISORY  WRITE 1 00:00:1 0 EOF\n")
            state = testbed.lock_state(d, "saivs", proc_locks=fake)
            self.assertEqual(state.holder.pid, os.getpid())
            self.assertEqual(state.waiting, 1)
            free = testbed.lock_state(d, "nothere", proc_locks=fake)
            self.assertFalse(free.exists)

    def test_state_merge(self):
        running = {"state": "running", "status": "Up"}
        free = testbed.LockState(Path("x"), True, None, 0)
        held = testbed.LockState(Path("x"), True, testbed.Holder(1, "shantanu", None, [], "saivpp-1", "shantanu"), 2)
        self.assertEqual(testbed.target_state(None, free, me="me").kind, "stopped")
        self.assertEqual(testbed.target_state({"state": "exited"}, free, me="me").kind, "stopped")
        self.assertEqual(testbed.target_state(running, free, me="me").text, "Ready")
        self.assertEqual(testbed.target_state(running, held, me="me").text, "Busy: shantanu's CLI run since ? · 2 waiting")
        self.assertEqual(testbed.target_state(running, held, me="shantanu").kind, "yours")
        self.assertEqual(testbed.target_state(running, free, docker_error="x", me="me").kind, "unknown")


if __name__ == "__main__":
    unittest.main()
