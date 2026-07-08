"""HS2 PLAYBOOK — wisdom/playbook.py unit tests (mock-only)."""

from __future__ import annotations

from agent_lab.wisdom.playbook import (
    HARNESS_REV_UNSET,
    add_bullet,
    load_bullets,
    playbook_bullets_for_topic,
    playbook_enabled,
)


def test_playbook_enabled_default_off(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_PLAYBOOK", raising=False)
    assert playbook_enabled() is False
    monkeypatch.setenv("AGENT_LAB_PLAYBOOK", "1")
    assert playbook_enabled() is True
    monkeypatch.setenv("AGENT_LAB_PLAYBOOK", "0")
    assert playbook_enabled() is False


# ---------------------------------------------------------------------------
# add_bullet / load_bullets — curator semantics
# ---------------------------------------------------------------------------


def test_add_bullet_creates_new_active_entry(tmp_path) -> None:
    path = tmp_path / "playbook.jsonl"
    bullet = add_bullet("항상 한국어로 응답할 것", "fp:user_correction:language_reminder", path=path)
    assert bullet.evidence_count == 1
    assert bullet.status == "active"
    assert bullet.harness_rev == HARNESS_REV_UNSET
    assert bullet.description == "항상 한국어로 응답할 것"


def test_add_bullet_recurring_pattern_bumps_evidence_only(tmp_path) -> None:
    path = tmp_path / "playbook.jsonl"
    first = add_bullet("항상 한국어로 응답할 것", "fp:user_correction:language_reminder", path=path)
    second = add_bullet("다른 문구로 재작성", "fp:user_correction:language_reminder", path=path)

    assert second.id == first.id
    assert second.evidence_count == 2
    # Curator rule: description pinned to first write, not overwritten.
    assert second.description == "항상 한국어로 응답할 것"


def test_add_bullet_harness_rev_pinned_to_creation(tmp_path) -> None:
    path = tmp_path / "playbook.jsonl"
    add_bullet("x", "fp:a", harness_rev="manifest@sha:abc123", path=path)
    second = add_bullet("y", "fp:a", harness_rev="manifest@sha:different", path=path)
    assert second.harness_rev == "manifest@sha:abc123"


def test_add_bullet_rejects_empty_fields(tmp_path) -> None:
    path = tmp_path / "playbook.jsonl"
    try:
        add_bullet("", "fp:a", path=path)
        assert False, "expected ValueError"
    except ValueError:
        pass
    try:
        add_bullet("desc", "", path=path)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_load_bullets_is_append_only_and_folds_to_latest(tmp_path) -> None:
    path = tmp_path / "playbook.jsonl"
    add_bullet("a", "fp:a", path=path)
    add_bullet("a-again", "fp:a", path=path)
    add_bullet("b", "fp:b", path=path)

    # Append-only: 3 physical lines on disk...
    assert path.read_text(encoding="utf-8").count("\n") == 3
    # ...but the folded view has only 2 current bullets (one per pattern_id).
    bullets = load_bullets(path=path)
    assert len(bullets) == 2
    by_pattern = {b.pattern_id: b for b in bullets}
    assert by_pattern["fp:a"].evidence_count == 2
    assert by_pattern["fp:b"].evidence_count == 1


def test_load_bullets_empty_when_missing(tmp_path) -> None:
    assert load_bullets(path=tmp_path / "missing.jsonl") == []


def test_load_bullets_filters_by_status(tmp_path) -> None:
    path = tmp_path / "playbook.jsonl"
    add_bullet("a", "fp:a", path=path)
    assert len(load_bullets(status="active", path=path)) == 1
    assert load_bullets(status="quarantined", path=path) == []


def test_load_bullets_sorted_most_recent_first(tmp_path, monkeypatch) -> None:
    path = tmp_path / "playbook.jsonl"
    timestamps = iter(["2026-07-08T10:00:00+00:00", "2026-07-08T10:00:01+00:00"])
    monkeypatch.setattr("agent_lab.wisdom.playbook._now_iso", lambda: next(timestamps))
    add_bullet("a", "fp:a", path=path)
    add_bullet("b", "fp:b", path=path)
    bullets = load_bullets(path=path)
    assert [b.pattern_id for b in bullets] == ["fp:b", "fp:a"]


# ---------------------------------------------------------------------------
# playbook_bullets_for_topic — HS2-2
# ---------------------------------------------------------------------------


def test_playbook_bullets_for_topic_flag_gated(tmp_path, monkeypatch) -> None:
    path = tmp_path / "playbook.jsonl"
    add_bullet("execute 전에 plan.md diff 확인 필수", "fp:a", path=path)
    monkeypatch.delenv("AGENT_LAB_PLAYBOOK", raising=False)
    assert playbook_bullets_for_topic("execute 전에 plan.md diff 확인 필요", path=path) == []


def test_playbook_bullets_for_topic_matches_keyword_overlap(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAYBOOK", "1")
    path = tmp_path / "playbook.jsonl"
    add_bullet("execute 전에 plan.md diff 확인 필수", "fp:a", path=path)
    add_bullet("한국어 응답 필수", "fp:b", path=path)

    hits = playbook_bullets_for_topic("execute 전에 plan.md diff 확인 필요", path=path)
    assert len(hits) == 1
    assert hits[0].pattern_id == "fp:a"


def test_playbook_bullets_for_topic_no_match_returns_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAYBOOK", "1")
    path = tmp_path / "playbook.jsonl"
    add_bullet("한국어 응답 필수", "fp:b", path=path)
    assert playbook_bullets_for_topic("completely unrelated zzzqux blorp", path=path) == []


def test_playbook_bullets_for_topic_respects_k(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAYBOOK", "1")
    path = tmp_path / "playbook.jsonl"
    for i in range(5):
        add_bullet(f"widget widget widget {i} 확인할 것", f"fp:{i}", path=path)
    hits = playbook_bullets_for_topic("widget 확인", k=2, path=path)
    assert len(hits) == 2
