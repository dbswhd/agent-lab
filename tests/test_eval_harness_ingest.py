"""Tests for eval_harness pytest JUnit ingestion."""

from __future__ import annotations

from agent_lab.eval_harness import aggregate
from agent_lab.eval_harness_ingest import parse_junit_xml, score_pytest_junit


JUNIT_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="2" failures="1" errors="0" skipped="0">
  <testcase classname="tests.test_foo" name="test_passes" time="0.01"/>
  <testcase classname="tests.test_foo" name="test_fails" time="0.02">
    <failure message="assert False"/>
  </testcase>
</testsuite>
"""


def test_parse_junit_xml_maps_pass_fail():
    result = parse_junit_xml(JUNIT_SAMPLE)
    assert result["test_passes"] == "pass"
    assert result["test_fails"] == "fail"


def test_score_pytest_junit_resolves_when_f2p_passes(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text(JUNIT_SAMPLE, encoding="utf-8")
    payload = score_pytest_junit(
        path,
        f2p_ids=["test_passes"],
        p2p_ids=[],
    )
    assert payload["score"]["resolved"] is True
    assert payload["score"]["attribution"] == "model"


def test_score_pytest_junit_aggregate():
    path_content = """<?xml version="1.0"?><testsuite><testcase name="a"/><testcase name="b"><failure/></testcase></testsuite>"""
    r1 = parse_junit_xml(path_content.replace("b", "a").replace("<failure/>", ""))
    scored_ok = __import__("agent_lab.eval_harness", fromlist=["score_instance"]).score_instance(
        r1, ["a"], [], status="ok"
    )
    r2 = parse_junit_xml(path_content)
    scored_bad = __import__("agent_lab.eval_harness", fromlist=["score_instance"]).score_instance(
        r2, ["b"], [], status="ok"
    )
    report = aggregate([scored_ok, scored_bad])
    assert report["total"] == 2
    assert report["resolved"] == 1
