"""Fast static tests for the code-memory MCP contract."""

from __future__ import annotations

from pathlib import Path

from agent_lab.code_memory_mcp_server import code_memory_search_payload
from agent_lab.mcp_tool_contract import (
    FORBIDDEN_TOOLS_GLOBAL,
    _SERVER_SPECS,
    validate_code_memory_hit,
    validate_code_memory_search_payload,
    validate_mcp_tool_surface,
)


def test_code_memory_contract_registered() -> None:
    spec = _SERVER_SPECS["agent-lab-code-memory"]

    assert spec["allowed"] == {"code_memory_search", "code_memory_status"}
    assert spec["required"] == {"code_memory_search"}


def test_forbidden_globals_include_write_execute() -> None:
    assert FORBIDDEN_TOOLS_GLOBAL >= {
        "write_file",
        "execute",
        "read_full_file",
        "read_full_json",
    }


def test_validate_surface_flags_forbidden_and_unexpected() -> None:
    ok_report = validate_mcp_tool_surface(
        ["code_memory_search", "code_memory_status"],
        server="agent-lab-code-memory",
    )
    assert ok_report["ok"] is True

    forbidden_report = validate_mcp_tool_surface(
        ["code_memory_search", "write_file"],
        server="agent-lab-code-memory",
    )
    assert forbidden_report["ok"] is False
    assert any("forbidden tools exposed: write_file" in issue for issue in forbidden_report["issues"])

    unexpected_report = validate_mcp_tool_surface(
        ["code_memory_search", "unknown_tool"],
        server="agent-lab-code-memory",
    )
    assert unexpected_report["ok"] is False
    assert any("unexpected tools: unknown_tool" in issue for issue in unexpected_report["issues"])


def test_cross_exclusive_generalizes_to_all_servers() -> None:
    report = validate_mcp_tool_surface(
        ["code_memory_search", "wisdom_search"],
        server="agent-lab-code-memory",
    )

    assert report["ok"] is False
    assert "tools belong on agent-lab-research: wisdom_search" in report["issues"]


def test_hit_validator_requires_source_refs() -> None:
    valid_hit = {
        "path": "src/example.py",
        "start_line": 3,
        "end_line": 5,
        "source_ref": "src/example.py:3-5",
        "snippet": "def example(): pass",
        "fresh": True,
    }
    assert validate_code_memory_hit(valid_hit) == []

    for key in ("path", "start_line", "end_line", "source_ref", "snippet", "fresh"):
        invalid_hit = dict(valid_hit)
        invalid_hit.pop(key)
        assert validate_code_memory_hit(invalid_hit)

    mismatched = dict(valid_hit, source_ref="src/example.py:4-5")
    assert any("source_ref must equal src/example.py:3-5" in issue for issue in validate_code_memory_hit(mismatched))


def test_search_payload_validator_runs_over_all_hits(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CODE_MEMORY_MCP", "1")
    payload = code_memory_search_payload(tmp_path, "contract", mode="mock")

    assert validate_code_memory_search_payload(payload)["ok"] is True

    corrupt_payload = dict(payload)
    corrupt_hits = [dict(hit) for hit in payload["hits"]]
    corrupt_hits[0]["source_ref"] = "wrong:1-1"
    corrupt_payload["hits"] = corrupt_hits

    result = validate_code_memory_search_payload(corrupt_payload)
    assert result["ok"] is False
    assert result["issues"]
