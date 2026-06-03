"""Session artifacts[] harvest and context blocks (Phase G1)."""

from __future__ import annotations

from pathlib import Path

from agent_lab.room_artifacts import (
    append_artifact,
    artifacts_public_payload,
    build_artifacts_block,
    harvest_artifacts_from_turn,
    list_artifacts,
)


class _Msg:
    def __init__(
        self,
        role: str,
        agent: str | None = None,
        content: str = "",
        parallel_round: int | None = 1,
    ):
        self.role = role
        self.agent = agent
        self.content = content
        self.parallel_round = parallel_round


def test_append_and_public_payload():
    meta: dict = {"turn_profile": "specialist"}
    row = append_artifact(
        meta,
        producer="codex",
        kind="log",
        summary="verify output",
        body="x" * 200,
    )
    assert row["id"].startswith("art-")
    payload = artifacts_public_payload(meta)
    assert payload["artifact_count"] == 1
    assert payload["artifacts"][0]["producer"] == "codex"


def test_harvest_specialist_turn(tmp_path: Path):
    meta: dict = {"turn_profile": "specialist", "research_mode": True}
    body = "line one\n" + ("detail " * 40)
    msgs = [
        _Msg("user", content="go"),
        _Msg("agent", agent="codex", content=body, parallel_round=1),
    ]
    created = harvest_artifacts_from_turn(
        meta,
        msgs,
        human_turn=1,
        session_folder=tmp_path,
        turn_profile="specialist",
        mode="discuss",
    )
    assert len(created) == 1
    assert list_artifacts(meta)[0]["producer"] == "codex"


def test_build_artifacts_block_for_cursor_r2():
    meta: dict = {"turn_profile": "specialist"}
    append_artifact(
        meta,
        producer="codex",
        kind="log",
        summary="R1 finding",
        body="finding body",
    )
    block = build_artifacts_block(meta, "cursor", parallel_round=2)
    assert "artifacts" in block
    assert "codex" in block


def test_build_artifacts_block_artifact_only_inlines_body(tmp_path: Path):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    body_path = artifact_dir / "codex.txt"
    body_path.write_text("inline body\n" + ("x" * 2200), encoding="utf-8")
    meta: dict = {
        "_session_folder": str(tmp_path),
        "turn_profile": "specialist",
        "artifacts": [
            {
                "producer": "codex",
                "kind": "log",
                "summary": "R1 finding",
                "path": "artifacts/codex.txt",
                "parallel_round": 1,
            }
        ],
    }

    block = build_artifacts_block(
        meta,
        "cursor",
        parallel_round=2,
        artifact_only=True,
        body_cap_chars=200,
    )

    assert "[artifact-only R2" in block
    assert "path: artifacts/codex.txt" in block
    assert "inline body" in block
    assert len(block) < 700
