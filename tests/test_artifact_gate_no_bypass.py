"""Guard: no script may fabricate its way past the artifact review gate.

Three live drivers used to patch a real session's ``run.json`` so that
``verification_artifacts.ok`` was true and ``needs_artifact_review`` was false,
then approve the execution. Every session they produced was therefore useless
as evidence — the gate they were meant to exercise had been defeated before the
run started, while the resulting sessions were still cited as shipped proof.

Reading these fields is fine. Writing them from ``scripts/`` is not: the gate
is cleared by a human reviewing real verification artifacts, or not at all.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

# Writing either of these from a driver forges the gate's own verdict.
GATE_FIELDS = frozenset({"verification_artifacts", "needs_artifact_review"})

# Fixture builders that author a whole disposable session from scratch (into a
# throwaway ``--sessions-dir``) legitimately spell out these fields as literal
# state. They patch nothing and defeat nothing.
FIXTURE_BUILDERS = frozenset(
    {
        "seed_wave_b_live_sessions.py",
        "seed_phase_b_small_mission_dogfood.py",
    }
)


def _targets(node: ast.Assign) -> list[ast.expr]:
    return list(node.targets)


def _gate_writes(tree: ast.AST) -> list[tuple[str, int]]:
    """Subscript assignments like ``row["verification_artifacts"] = {...}``."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = _targets(node)
        elif isinstance(node, ast.AugAssign | ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if not isinstance(target, ast.Subscript):
                continue
            key = target.slice
            if isinstance(key, ast.Constant) and key.value in GATE_FIELDS:
                found.append((str(key.value), node.lineno))
    return found


def test_no_script_writes_the_artifact_gate_fields() -> None:
    offenders: list[str] = []
    for path in sorted(SCRIPTS.rglob("*.py")):
        if path.name in FIXTURE_BUILDERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for field, lineno in _gate_writes(tree):
            rel = path.relative_to(ROOT)
            offenders.append(f"{rel}:{lineno} writes {field!r}")

    assert not offenders, (
        "scripts must not write artifact-gate fields — a driver that clears the "
        "gate it is measuring produces sessions that cannot be used as evidence:\n  " + "\n  ".join(offenders)
    )


def test_fixture_builder_allowlist_is_accurate() -> None:
    """The allowlist must not outlive the files it exempts."""
    missing = [name for name in FIXTURE_BUILDERS if not (SCRIPTS / name).exists()]
    assert not missing, f"stale FIXTURE_BUILDERS entries: {missing}"
