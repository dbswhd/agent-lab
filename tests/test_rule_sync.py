"""N10b — Rule Sync unit tests (mock-only; codex target always redirected to tmp_path).

docs/N10-USER-LOOP-WISDOM-DRAFT.md §2 (N10b).
"""

from __future__ import annotations

from pathlib import Path

from agent_lab.rule_sync import (
    apply_rule_sync,
    parse_correction_rules,
    preview_rule_sync,
    render_claude_rules,
    render_codex_agents_md,
    render_cursor_rules,
    rule_sync_enabled,
)

_SSOT_ONE_RULE = """# Correction Rules (N10a — Human-approved)

## 항상 한국어로 응답 (`language_reminder`)

항상 한국어로 응답할 것. 코드/변수명은 영어 유지.

- 근거: 3개 세션에서 반복 관측
- 승인일: 2026-07-06T21:04:12+00:00

"""

_SSOT_TWO_RULES = _SSOT_ONE_RULE + (
    "## 진단 없는 재시도 (`retry_reflex`)\n\n"
    "실패 직후 재시도 전에 실패 원인을 먼저 한 줄로 설명할 것.\n\n"
    "- 근거: 4개 세션에서 반복 관측\n"
    "- 승인일: 2026-07-06T22:00:00+00:00\n\n"
)


def _write_ssot(root: Path, content: str) -> None:
    path = root / ".agent-lab" / "wisdom" / "correction_rules.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# --- flag ---


def test_rule_sync_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AGENT_LAB_RULE_SYNC", raising=False)
    assert rule_sync_enabled() is False


def test_rule_sync_enabled_via_env(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_RULE_SYNC", "1")
    assert rule_sync_enabled() is True


# --- parse ---


def test_parse_correction_rules_empty_without_ssot(tmp_path):
    assert parse_correction_rules(tmp_path) == []


def test_parse_correction_rules_single(tmp_path):
    _write_ssot(tmp_path, _SSOT_ONE_RULE)
    rows = parse_correction_rules(tmp_path)
    assert len(rows) == 1
    assert rows[0]["key"] == "language_reminder"
    assert rows[0]["label"] == "항상 한국어로 응답"
    assert "한국어로 응답할 것" in rows[0]["text"]
    assert rows[0]["evidence"] == "3개 세션에서 반복 관측"


def test_parse_correction_rules_multiple(tmp_path):
    _write_ssot(tmp_path, _SSOT_TWO_RULES)
    rows = parse_correction_rules(tmp_path)
    assert [r["key"] for r in rows] == ["language_reminder", "retry_reflex"]


# --- render ---


def test_render_claude_rules_contains_marker_and_rule(tmp_path):
    _write_ssot(tmp_path, _SSOT_ONE_RULE)
    rules = parse_correction_rules(tmp_path)
    out = render_claude_rules(rules)
    assert "agent-lab:correction-rules:start" in out
    assert "language_reminder" in out
    assert "항상 한국어로 응답할 것" in out


def test_render_cursor_rules_has_mdc_frontmatter(tmp_path):
    _write_ssot(tmp_path, _SSOT_ONE_RULE)
    rules = parse_correction_rules(tmp_path)
    out = render_cursor_rules(rules)
    assert out.startswith("---\ndescription:")
    assert "alwaysApply: true" in out
    assert "language_reminder" in out


def test_render_preserves_hand_written_content_outside_markers(tmp_path):
    _write_ssot(tmp_path, _SSOT_ONE_RULE)
    rules = parse_correction_rules(tmp_path)
    existing = "# My Hand-Written Rules\n\nAlways do X.\n"
    out = render_claude_rules(rules, existing=existing)
    assert "Always do X." in out
    assert "language_reminder" in out


def test_render_idempotent_resync_replaces_only_managed_section(tmp_path):
    _write_ssot(tmp_path, _SSOT_ONE_RULE)
    rules_v1 = parse_correction_rules(tmp_path)
    first = render_claude_rules(rules_v1, existing="# Hand-written\n\nKeep me.\n")

    _write_ssot(tmp_path, _SSOT_TWO_RULES)
    rules_v2 = parse_correction_rules(tmp_path)
    second = render_claude_rules(rules_v2, existing=first)

    assert "Keep me." in second
    assert second.count("Keep me.") == 1  # not duplicated across re-syncs
    assert "retry_reflex" in second
    assert "language_reminder" in second


def test_render_codex_agents_md_never_touches_existing_body(tmp_path):
    _write_ssot(tmp_path, _SSOT_ONE_RULE)
    rules = parse_correction_rules(tmp_path)
    existing = "# Personal Codex instructions\n\nAlways be concise.\n"
    out = render_codex_agents_md(rules, existing=existing)
    assert "Always be concise." in out
    assert "language_reminder" in out


# --- preview / apply ---


def test_preview_rule_sync_is_pure_no_writes(tmp_path):
    _write_ssot(tmp_path, _SSOT_ONE_RULE)
    codex_home = tmp_path / "fake-codex-home"
    plan = preview_rule_sync(tmp_path, codex_home=codex_home)
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".cursor").exists()
    assert not codex_home.exists()
    assert set(plan["targets"]) == {"claude", "cursor", "codex"}
    assert plan["targets"]["codex"]["path"] == str(codex_home / "AGENTS.md")


def test_apply_rule_sync_writes_all_targets(tmp_path):
    _write_ssot(tmp_path, _SSOT_ONE_RULE)
    codex_home = tmp_path / "fake-codex-home"
    result = apply_rule_sync(tmp_path, codex_home=codex_home)

    claude_file = tmp_path / ".claude" / "rules" / "correction-rules.md"
    cursor_file = tmp_path / ".cursor" / "rules" / "correction-rules.mdc"
    codex_file = codex_home / "AGENTS.md"
    assert claude_file.is_file()
    assert cursor_file.is_file()
    assert codex_file.is_file()
    assert "language_reminder" in claude_file.read_text(encoding="utf-8")
    assert "language_reminder" in cursor_file.read_text(encoding="utf-8")
    assert "language_reminder" in codex_file.read_text(encoding="utf-8")
    assert set(result["written"]) == {str(claude_file), str(cursor_file), str(codex_file)}


def test_apply_rule_sync_can_scope_to_single_target(tmp_path):
    _write_ssot(tmp_path, _SSOT_ONE_RULE)
    codex_home = tmp_path / "fake-codex-home"
    result = apply_rule_sync(tmp_path, targets=["claude"], codex_home=codex_home)
    assert result["written"] == [str(tmp_path / ".claude" / "rules" / "correction-rules.md")]
    assert not codex_home.exists()


def test_apply_rule_sync_never_writes_outside_provided_codex_home(tmp_path, monkeypatch):
    """Guards against ever falling back to the real ~/.codex during tests."""
    monkeypatch.setenv("AGENT_LAB_CODEX_HOME", str(tmp_path / "env-codex-home"))
    _write_ssot(tmp_path, _SSOT_ONE_RULE)
    apply_rule_sync(tmp_path, targets=["codex"])
    assert (tmp_path / "env-codex-home" / "AGENTS.md").is_file()
