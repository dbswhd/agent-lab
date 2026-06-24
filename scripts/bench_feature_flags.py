#!/usr/bin/env python3
"""Deterministic ON-vs-OFF benchmark for the P0–P3 default-off feature flags.

Measures OBJECTIVE metrics only (chars/tokens-approx/bytes/time/accuracy) against
fixed in-process fixtures. NO LLM calls, no network, no real agent session — so it
answers the *cost/safety* half of "should this be default-on", not the *quality*
half (which needs real sessions + human judgment).

Usage:
    .venv/bin/python scripts/bench_feature_flags.py [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent


def _time_ms(fn: Callable[[], Any], repeat: int = 5) -> tuple[Any, float]:
    """Return (last_result, best-of-N milliseconds)."""
    best = float("inf")
    result: Any = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = fn()
        best = min(best, (time.perf_counter() - t0) * 1000.0)
    return result, best


def _approx_tokens(text: str) -> int:
    # Cheap, deterministic token proxy (~4 chars/token). Not a real tokenizer.
    return (len(text) + 3) // 4


# --- P1: repo-map vs plain repo tree ---------------------------------------


def bench_repo_map() -> dict[str, Any]:
    from agent_lab.repo_map import build_repo_map_block
    from agent_lab.repo_tree_context import build_repo_tree_block

    run_meta = {"workspace_binding": {"path": str(REPO_ROOT)}}
    off, off_ms = _time_ms(lambda: build_repo_tree_block(run_meta))
    on, on_ms = _time_ms(lambda: build_repo_map_block(run_meta))
    return {
        "feature": "P1 repo-map",
        "off_chars": len(off),
        "on_chars": len(on),
        "off_tokens_approx": _approx_tokens(off),
        "on_tokens_approx": _approx_tokens(on),
        "delta_tokens_approx": _approx_tokens(on) - _approx_tokens(off),
        "off_ms": round(off_ms, 3),
        "on_ms": round(on_ms, 3),
        "note": "OFF=plain repo tree, ON=ast symbol-map. Quality (better context?) needs a real session.",
    }


# --- P2: tool-output compaction --------------------------------------------


def bench_compaction() -> dict[str, Any]:
    from dataclasses import dataclass, field

    from agent_lab.room_context import _truncate_old_tool_outputs

    @dataclass
    class _Msg:
        role: str
        agent: str | None
        content: str
        parallel_round: int | None = None
        extra: dict = field(default_factory=dict)

    big = "```\n" + ("LOGLINE " * 4000) + "\n```"  # ~32k char fenced block
    recent = [
        _Msg("user", None, "do the thing"),
        _Msg("agent", "codex", big),
        _Msg("agent", "claude", big),
        _Msg("user", None, "follow up"),
        _Msg("agent", "cursor", big),
    ]
    pinned: list[Any] = [recent[-2], recent[-1]]  # current-turn pins
    cap = 2000
    before = sum(len(m.content) for m in recent)
    out, ms = _time_ms(lambda: _truncate_old_tool_outputs(recent, pinned, cap=cap))
    after = sum(len(m.content) for m in out)
    truncated = sum(1 for m in out if "[...truncated" in m.content)
    return {
        "feature": "P2 tool-output compaction",
        "off_chars": before,
        "on_chars": after,
        "chars_saved": before - after,
        "reduction_pct": round((before - after) / before * 100, 1) if before else 0.0,
        "blocks_truncated": truncated,
        "turns_preserved": len(out) == len(recent),
        "on_ms": round(ms, 3),
        "note": "cap=2000. OFF=no change. Pins excluded from truncation by design.",
    }


# --- P0: checkpoint write cost ---------------------------------------------


def bench_checkpoint() -> dict[str, Any]:
    from agent_lab.checkpoint_store import append_checkpoint

    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        n = 50
        prior: tuple[str | None, str | None] = (None, None)
        t0 = time.perf_counter()
        for i in range(n):
            run = {"_session_id": "bench", "mission_loop": {"phase": f"P{i}"}}
            append_checkpoint(folder, prior_signature=prior, updated_run=run)
            prior = (f"P{i}", None)
        total_ms = (time.perf_counter() - t0) * 1000.0
        cp = folder / "checkpoints.jsonl"
        size = cp.stat().st_size if cp.is_file() else 0
        lines = len(cp.read_text().splitlines()) if cp.is_file() else 0
    return {
        "feature": "P0 checkpoint",
        "phase_transitions": n,
        "ms_per_transition": round(total_ms / n, 4),
        "total_ms": round(total_ms, 3),
        "jsonl_bytes": size,
        "bytes_per_transition": round(size / n, 1) if n else 0,
        "records_written": lines,
        "note": "OFF=zero disk writes. ON cost = this much extra I/O per phase change.",
    }


# --- P3: syntax gate accuracy + speed --------------------------------------


def bench_syntax_gate() -> dict[str, Any]:
    from agent_lab.syntax_gate import evaluate_syntax_gate

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # valid files
        for i in range(10):
            (root / f"good_{i}.py").write_text(f"def f{i}():\n    return {i}\n")
        # broken files
        for i in range(10):
            (root / f"bad_{i}.py").write_text(f"def g{i}(:\n    pass\n")
        non_py = root / "data.txt"
        non_py.write_text("def not(: python")

        def _exec(paths: list[str]) -> dict[str, Any]:
            return {
                "isolation_effective": "worktree",
                "worktree_path": str(root),
                "action_verify": "x",
                "source_touched_paths": paths,
            }

        os.environ["AGENT_LAB_SYNTAX_GATE"] = "1"
        # valid-only => should pass (no false block)
        valid_res, valid_ms = _time_ms(lambda: evaluate_syntax_gate(_exec([f"good_{i}.py" for i in range(10)])))
        # broken present => should block
        broken_res, broken_ms = _time_ms(
            lambda: evaluate_syntax_gate(_exec([f"good_{i}.py" for i in range(10)] + ["bad_0.py"]))
        )
        # non-.py only => skipped, pass
        nonpy_res = evaluate_syntax_gate(_exec(["data.txt"]))
        os.environ.pop("AGENT_LAB_SYNTAX_GATE", None)

    false_block = valid_res["ok"] is False  # must be False (no false positive)
    correct_block = broken_res["ok"] is False  # must be True
    return {
        "feature": "P3 syntax gate",
        "valid_files_blocked_false_positive": false_block,
        "broken_file_correctly_blocked": correct_block,
        "non_py_skipped": nonpy_res["ok"] is True,
        "scan_ms_valid_10": round(valid_ms, 3),
        "scan_ms_with_broken": round(broken_ms, 3),
        "accuracy_ok": (not false_block) and correct_block and nonpy_res["ok"],
        "note": "Accuracy: 0 false-blocks on valid, blocks on broken, skips non-.py.",
    }


BENCHES: list[Callable[[], dict[str, Any]]] = [
    bench_repo_map,
    bench_compaction,
    bench_checkpoint,
    bench_syntax_gate,
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args()

    results: list[dict[str, Any]] = []
    for bench in BENCHES:
        try:
            results.append(bench())
        except Exception as exc:  # defensive: a broken metric must not abort the rest
            results.append({"feature": bench.__name__, "error": str(exc)})

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0

    for r in results:
        print(f"\n=== {r.get('feature', '?')} ===")
        for k, v in r.items():
            if k == "feature":
                continue
            print(f"  {k}: {v}")
    print(
        "\nNOTE: objective cost/safety metrics only (no LLM). "
        "Output-quality promotion still needs real sessions + human review."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
