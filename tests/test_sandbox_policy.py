"""P3 sandbox policy seam (AGENT_LAB_SANDBOX_POLICY, default off).

Covers AC7-AC12 + OFF-parity return-shape (Critic N1).
"""

from __future__ import annotations

from pathlib import Path

from agent_lab import sandbox_policy as sp
from agent_lab import worktree_hooks as wh


# --- resolver (pure) --------------------------------------------------------


def test_ac7_off_returns_worktree(monkeypatch):
    monkeypatch.delenv("AGENT_LAB_SANDBOX_POLICY", raising=False)
    pol = sp.resolve_sandbox_policy()
    assert pol == {"runtime": "worktree", "image": None, "limits": None}


def test_ac8_on_docker_returns_typed_policy(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_SANDBOX_POLICY", "1")
    monkeypatch.setenv("AGENT_LAB_SANDBOX_RUNTIME", "docker")
    monkeypatch.setenv("AGENT_LAB_SANDBOX_IMAGE", "python:3.13-slim")
    pol = sp.resolve_sandbox_policy()
    assert pol["runtime"] == "docker"
    assert pol["image"] == "python:3.13-slim"
    assert pol["limits"] is None


def test_on_worktree_runtime(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_SANDBOX_POLICY", "1")
    monkeypatch.setenv("AGENT_LAB_SANDBOX_RUNTIME", "worktree")
    assert sp.resolve_sandbox_policy()["runtime"] == "worktree"


def test_unknown_runtime_normalized(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_SANDBOX_POLICY", "1")
    monkeypatch.setenv("AGENT_LAB_SANDBOX_RUNTIME", "qemu")
    assert sp.resolve_sandbox_policy()["runtime"] == "worktree"


def test_ac11_resolver_is_pure(monkeypatch):
    # No IO/subprocess: calling twice with same env yields identical dict.
    monkeypatch.setenv("AGENT_LAB_SANDBOX_POLICY", "1")
    monkeypatch.setenv("AGENT_LAB_SANDBOX_RUNTIME", "docker")
    monkeypatch.delenv("AGENT_LAB_SANDBOX_IMAGE", raising=False)
    assert sp.resolve_sandbox_policy() == sp.resolve_sandbox_policy()


def test_enabled_helper(monkeypatch):
    monkeypatch.delenv("AGENT_LAB_SANDBOX_POLICY", raising=False)
    assert sp.sandbox_policy_enabled() is False
    monkeypatch.setenv("AGENT_LAB_SANDBOX_POLICY", "yes")
    assert sp.sandbox_policy_enabled() is True


# --- _run_command seam (AC9/AC10 + OFF-parity) ------------------------------


def _run(tmp_path: Path) -> dict:
    return wh._run_command("printf ok", cwd=tmp_path)


def test_ac7_off_parity_result_shape(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_LAB_SANDBOX_POLICY", raising=False)
    row = _run(tmp_path)
    assert "sandbox_intent" not in row  # byte-identical existing shape
    assert set(row) == {"cmd", "exit", "ok", "detail", "stdout", "stderr"}
    assert row["ok"] is True


def test_n1_on_worktree_shape_equals_off(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_LAB_SANDBOX_POLICY", raising=False)
    off_keys = set(_run(tmp_path))
    monkeypatch.setenv("AGENT_LAB_SANDBOX_POLICY", "1")
    monkeypatch.setenv("AGENT_LAB_SANDBOX_RUNTIME", "worktree")
    on_keys = set(_run(tmp_path))
    assert on_keys == off_keys  # on+worktree adds no key


def test_ac9_ac10_on_docker_fallback_records_intent(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_SANDBOX_POLICY", "1")
    monkeypatch.setenv("AGENT_LAB_SANDBOX_RUNTIME", "docker")
    row = _run(tmp_path)
    # AC9: verify actually ran in the worktree subprocess (real exit/stdout), no container
    assert row["ok"] is True
    assert row["exit"] == 0
    # AC10: additive intent key, no raise
    assert row["sandbox_intent"] == "docker"


def test_intent_helper_off_returns_none(monkeypatch):
    monkeypatch.delenv("AGENT_LAB_SANDBOX_POLICY", raising=False)
    assert wh._sandbox_intent() is None


def test_intent_helper_docker(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_SANDBOX_POLICY", "1")
    monkeypatch.setenv("AGENT_LAB_SANDBOX_RUNTIME", "docker")
    assert wh._sandbox_intent() == "docker"
