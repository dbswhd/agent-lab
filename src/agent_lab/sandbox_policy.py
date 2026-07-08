"""Sandbox policy seam (G4) — typed runtime policy for the verify subprocess.

Pure stdlib, no IO, no subprocess. Default OFF via AGENT_LAB_SANDBOX_POLICY: when
off, callers must not invoke the resolver, keeping the verify subprocess path
byte-identical (OFF-parity). When on, ``resolve_sandbox_policy`` returns a typed
policy; ``runtime="docker"`` is DEFERRED — the caller falls back to the worktree
subprocess and records ``sandbox_intent="docker"`` without launching any container.
"""

from __future__ import annotations

import os
from typing import Any

from agent_lab.env_flags import env_bool

# Typed sandbox policy: a plain dict so it is trivially serializable and testable.
# Shape: {"runtime": "worktree"|"docker", "image": str|None, "limits": dict|None}
SandboxPolicy = dict[str, Any]

_VALID_RUNTIMES = frozenset({"worktree", "docker"})


def sandbox_policy_enabled() -> bool:
    """AGENT_LAB_SANDBOX_POLICY (default ON): resolve a sandbox policy at the verify seam. Opt-out via =0."""
    return env_bool("AGENT_LAB_SANDBOX_POLICY", default=True)


def _configured_runtime() -> str:
    raw = (os.getenv("AGENT_LAB_SANDBOX_RUNTIME") or "worktree").strip().lower()
    return raw if raw in _VALID_RUNTIMES else "worktree"


def resolve_sandbox_policy() -> SandboxPolicy:
    """Return the typed sandbox policy.

    Pure: reads only env, performs no IO/subprocess. Flag-off => worktree policy
    (current behavior). Flag-on => runtime from AGENT_LAB_SANDBOX_RUNTIME, with
    unknown values normalized to "worktree".
    """
    if not sandbox_policy_enabled():
        return {"runtime": "worktree", "image": None, "limits": None}
    runtime = _configured_runtime()
    if runtime == "docker":
        image = (os.getenv("AGENT_LAB_SANDBOX_IMAGE") or "").strip() or None
        return {"runtime": "docker", "image": image, "limits": None}
    return {"runtime": "worktree", "image": None, "limits": None}
