"""Parse pytest JUnit XML into eval_harness result maps."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def _normalize_status(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in {"pass", "passed", "ok", "success"}:
        return "pass"
    return "fail"


def parse_junit_xml(text: str) -> dict[str, str]:
    """Return ``{testcase_name: "pass"|"fail"}`` from JUnit XML."""
    root = ET.fromstring(text)
    result: dict[str, str] = {}
    for case in root.iter("testcase"):
        name = (case.get("name") or "").strip()
        if not name:
            continue
        status = "pass"
        if case.find("failure") is not None or case.find("error") is not None:
            status = "fail"
        elif (case.get("status") or "").strip():
            status = _normalize_status(case.get("status"))
        result[name] = status
    return result


def parse_junit_xml_path(path: Path | str) -> dict[str, str]:
    return parse_junit_xml(Path(path).read_text(encoding="utf-8"))


def score_pytest_junit(
    junit_path: Path | str,
    *,
    f2p_ids: list[str],
    p2p_ids: list[str],
    status: str = "ok",
) -> dict[str, Any]:
    """First eval_harness call site: pytest XML → score_instance."""
    from agent_lab.eval_harness import score_instance

    result_map = parse_junit_xml_path(junit_path)
    scored = score_instance(result_map, f2p_ids, p2p_ids, status=status)
    return {"result_map": result_map, "score": scored}


def score_execute_outcome(verdict: str) -> dict[str, Any]:
    from agent_lab.eval_harness import score_outcome_verdict

    return score_outcome_verdict(verdict)
