"""Turn profile bandit (E1 human feedback)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent_lab.turn_profile_bandit import (
    infer_turn_profile,
    load_bandit_store,
    recommend_profile,
    record_turn_feedback,
    patch_session_turn_feedback,
)


def test_infer_turn_profile_from_flags():
    assert infer_turn_profile({"consensus_mode": True}) == "free"
    assert infer_turn_profile({"review_mode": True}) == "review"
    assert infer_turn_profile({"agent_parallel_rounds": 1, "agents": ["cursor"]}) == "quick"
    assert infer_turn_profile({"turn_profile": "discuss"}) == "discuss"


def test_ucb_recommendation_explores_unseen():
    store = load_bandit_store(Path("/nonexistent/path.json"))
    rec = recommend_profile(store)
    assert rec["recommended"] in ("quick", "discuss", "review", "free")
    assert rec["total_feedback"] == 0


def test_record_feedback_updates_stats(tmp_path: Path):
    path = tmp_path / "bandit.json"
    record_turn_feedback(profile="discuss", vote="up", session_id="s1", path=path)
    record_turn_feedback(profile="discuss", vote="up", session_id="s2", path=path)
    record_turn_feedback(profile="free", vote="down", session_id="s3", path=path)
    data = load_bandit_store(path)
    assert data["profiles"]["discuss"]["up"] == 2
    assert data["profiles"]["free"]["down"] == 1
    rec = recommend_profile(data)
    assert rec["recommended"] == "discuss"


def test_patch_session_turn_feedback(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    run = {
        "turns": [
            {
                "mode": "discuss",
                "turn_profile": "review",
                "review_mode": True,
                "agent_parallel_rounds": 2,
                "agents": ["claude", "codex", "cursor"],
            }
        ]
    }
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    fb = patch_session_turn_feedback(folder, vote="up")
    assert fb["vote"] == "up"
    assert fb["profile"] == "review"
    saved = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert saved["turns"][0]["feedback"]["vote"] == "up"
