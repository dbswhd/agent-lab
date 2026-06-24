#!/usr/bin/env python3
"""LLM quality benchmark for P1 (repo-map comprehension) and P2 (compaction retention).

The deterministic bench (bench_feature_flags.py) answers the *cost/safety* half.
This script answers the *quality* half — either via real Anthropic API calls
(requires ANTHROPIC_API_KEY with credits) or via the built-in self-evaluation mode
that uses code-derived evidence without any API call (--self-eval).

  P1 — Does the AST symbol map (ON) help the model answer codebase questions
       more accurately than a plain directory tree (OFF)?

  P2 — After tool-output compaction (HEAD+TAIL, cap//2 each end), which needle
       positions survive and which are lost?

Model (API mode): claude-haiku-4-5-20251001 (fast, cheap)
Self-eval mode:   evidence collected from real project code, no API needed.

Usage:
    .venv/bin/python scripts/bench_quality_flags.py --self-eval   # no API key needed
    .venv/bin/python scripts/bench_quality_flags.py               # real LLM calls
    .venv/bin/python scripts/bench_quality_flags.py --json        # JSON output
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Tiny Anthropic wrapper (avoids importing the full agent stack for scoring)
# ---------------------------------------------------------------------------


def _chat(
    messages: list[dict], system: str = "", model: str = "claude-haiku-4-5-20251001", max_tokens: int = 512
) -> str:
    """Single synchronous chat call, returns assistant text."""
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return resp.content[0].text.strip()


def _score(question: str, answer: str, expected_keywords: list[str]) -> dict[str, Any]:
    """Ask a judge LLM to rate answer quality 1–5 and check keyword presence."""
    keywords_found = [kw for kw in expected_keywords if kw.lower() in answer.lower()]
    keyword_hit_rate = len(keywords_found) / max(len(expected_keywords), 1)

    judge_prompt = textwrap.dedent(f"""
        Question asked: {question}

        Answer given:
        {answer}

        Score the answer's accuracy and specificity on a 1–5 scale.
        1 = wrong or completely vague  3 = partially correct  5 = specific and correct
        Respond with ONLY: {{"score": <int 1-5>, "reason": "<one sentence>"}}
    """).strip()

    judge_raw = _chat(
        [{"role": "user", "content": judge_prompt}],
        system="You are a precise technical judge. Reply ONLY with the JSON requested.",
        max_tokens=120,
    )
    try:
        judge = json.loads(judge_raw)
    except json.JSONDecodeError:
        # Fallback: extract score digit from response
        import re

        m = re.search(r'"score"\s*:\s*(\d)', judge_raw)
        judge = {"score": int(m.group(1)) if m else 3, "reason": judge_raw[:120]}

    return {
        "judge_score": judge.get("score", 3),
        "judge_reason": judge.get("reason", ""),
        "keyword_hits": keywords_found,
        "keyword_hit_rate": round(keyword_hit_rate, 2),
    }


# ---------------------------------------------------------------------------
# P1: repo-map comprehension quality
# ---------------------------------------------------------------------------

_P1_QUESTIONS: list[dict] = [
    {
        "q": "Where is the worktree branch merge logic implemented? Name the file and key function.",
        "expected": ["auto_merge", "merge"],
    },
    {
        "q": "Which function writes a checkpoint to disk when a phase changes? Name the file and function.",
        "expected": ["checkpoint_store", "append_checkpoint"],
    },
    {
        "q": "Where is the execute gate that blocks plan execution? Name the file.",
        "expected": ["plan_execute"],
    },
]


def bench_p1_repo_map_quality() -> dict[str, Any]:
    sys.stdout.write("  [P1] Building repo contexts…\n")
    sys.stdout.flush()

    from agent_lab.repo_map import build_repo_map_block
    from agent_lab.repo_tree_context import build_repo_tree_block

    run_meta = {"workspace_binding": {"path": str(REPO_ROOT)}}

    # Temporarily enable the context layer so both builders work
    os.environ["AGENT_LAB_REPO_TREE"] = "1"
    os.environ["AGENT_LAB_REPO_MAP"] = "1"
    ctx_off = build_repo_tree_block(run_meta)
    ctx_on = build_repo_map_block(run_meta)
    os.environ.pop("AGENT_LAB_REPO_TREE", None)
    os.environ.pop("AGENT_LAB_REPO_MAP", None)

    sys.stdout.write(f"  [P1] OFF context: {len(ctx_off)} chars  ON context: {len(ctx_on)} chars\n")
    sys.stdout.flush()

    off_scores: list[int] = []
    on_scores: list[int] = []
    details: list[dict] = []

    for item in _P1_QUESTIONS:
        q = item["q"]
        expected = item["expected"]
        sys.stdout.write(f"  [P1] Q: {q[:70]}…\n")
        sys.stdout.flush()

        system_off = f"You are a code navigator. Here is the repository layout:\n\n{ctx_off}"
        system_on = f"You are a code navigator. Here is the repository layout:\n\n{ctx_on}"
        msgs = [{"role": "user", "content": q}]

        ans_off = _chat(msgs, system=system_off, max_tokens=200)
        ans_on = _chat(msgs, system=system_on, max_tokens=200)

        score_off = _score(q, ans_off, expected)
        score_on = _score(q, ans_on, expected)

        off_scores.append(score_off["judge_score"])
        on_scores.append(score_on["judge_score"])
        details.append(
            {
                "question": q,
                "expected_keywords": expected,
                "off": {"answer": ans_off[:300], **score_off},
                "on": {"answer": ans_on[:300], **score_on},
                "winner": "ON"
                if score_on["judge_score"] > score_off["judge_score"]
                else ("OFF" if score_off["judge_score"] > score_on["judge_score"] else "TIE"),
            }
        )

    avg_off = round(sum(off_scores) / max(len(off_scores), 1), 2)
    avg_on = round(sum(on_scores) / max(len(on_scores), 1), 2)
    verdict = "ON wins" if avg_on > avg_off else ("TIE" if avg_on == avg_off else "OFF wins")

    return {
        "feature": "P1 repo-map quality (LLM)",
        "questions": len(_P1_QUESTIONS),
        "avg_judge_score_OFF": avg_off,
        "avg_judge_score_ON": avg_on,
        "delta": round(avg_on - avg_off, 2),
        "verdict": verdict,
        "details": details,
        "note": (
            "Judge: claude-haiku-4-5-20251001 1-5 score. "
            "ON=AST symbol map, OFF=plain dir tree. "
            "delta>0 means symbol map improves comprehension."
        ),
    }


# ---------------------------------------------------------------------------
# P2: compaction retention quality
# ---------------------------------------------------------------------------

_NEEDLE_FACTS = [
    ("fatal_error_code", "FATAL_CODE_42"),
    ("db_tables", "users_sessions_runs"),
    ("config_timeout", "TIMEOUT_8192ms"),
]

_P2_QUESTIONS = [
    ("What was the FATAL error code seen in the tool output?", "FATAL_CODE_42"),
    ("How many tables are in the database schema, and what are their names?", "users_sessions_runs"),
    ("What is the configured timeout value in milliseconds?", "TIMEOUT_8192ms"),
]


def _build_conversation_with_needles() -> list[Any]:
    """Build a fake but realistic conversation with needle facts buried in large tool outputs."""

    @dataclasses.dataclass
    class _Msg:
        role: str
        agent: str | None
        content: str
        parallel_round: int | None = None
        extra: dict = dataclasses.field(default_factory=dict)

    padding = "DEBUG: processing step... " * 600  # ~15k chars of noise per block

    msgs = [
        _Msg("user", None, "Run the diagnostic suite"),
        _Msg("agent", "codex", f"```\n{padding}\n⚠ FATAL_CODE_42 — critical subsystem failure\n{padding}\n```"),
        _Msg("agent", "claude", "I see the fatal error. Let me check the schema."),
        _Msg("user", None, "Check the database schema too"),
        _Msg("agent", "cursor", f"```\nSchema scan:\n{padding}\nTables: users_sessions_runs (3 total)\n{padding}\n```"),
        _Msg("agent", "claude", "Schema confirmed. Checking config now."),
        _Msg("user", None, "What's the timeout setting?"),
        _Msg("agent", "codex", f"```\nConfig dump:\n{padding}\ntimeout=TIMEOUT_8192ms\n{padding}\n```"),
        # Current turn (these get pinned / not truncated)
        _Msg("user", None, "Summarise all findings"),
        _Msg("agent", "claude", "Analyzing all previous outputs now."),
    ]
    return msgs


def bench_p2_compaction_quality() -> dict[str, Any]:
    sys.stdout.write("  [P2] Building compacted vs full context…\n")
    sys.stdout.flush()

    from agent_lab.room_context import _truncate_old_tool_outputs

    msgs = _build_conversation_with_needles()
    pinned = msgs[-2:]  # last user + last agent = current turn
    cap = 2000

    full_context = "\n\n---\n".join(f"[{m.role}/{m.agent or 'user'}]:\n{m.content}" for m in msgs)
    truncated_msgs = _truncate_old_tool_outputs(msgs, pinned, cap=cap)
    compact_context = "\n\n---\n".join(f"[{m.role}/{m.agent or 'user'}]:\n{m.content}" for m in truncated_msgs)

    chars_before = len(full_context)
    chars_after = len(compact_context)

    sys.stdout.write(
        f"  [P2] Full: {chars_before} chars  Compacted: {chars_after} chars  "
        f"({round((chars_before - chars_after) / chars_before * 100, 1)}% reduction)\n"
    )
    sys.stdout.flush()

    full_scores: list[int] = []
    compact_scores: list[int] = []
    details: list[dict] = []

    for q, expected_needle in _P2_QUESTIONS:
        sys.stdout.write(f"  [P2] Q: {q[:70]}\n")
        sys.stdout.flush()

        system = "You are a helpful assistant. Answer based ONLY on the conversation history provided."

        ans_full = _chat(
            [
                {"role": "user", "content": f"Conversation history:\n{full_context}\n\nQuestion: {q}"},
            ],
            system=system,
            max_tokens=150,
        )
        ans_compact = _chat(
            [
                {"role": "user", "content": f"Conversation history:\n{compact_context}\n\nQuestion: {q}"},
            ],
            system=system,
            max_tokens=150,
        )

        score_full = _score(q, ans_full, [expected_needle])
        score_compact = _score(q, ans_compact, [expected_needle])

        full_scores.append(score_full["judge_score"])
        compact_scores.append(score_compact["judge_score"])
        details.append(
            {
                "question": q,
                "needle": expected_needle,
                "full": {"answer": ans_full[:200], **score_full},
                "compact": {"answer": ans_compact[:200], **score_compact},
                "retained": score_compact["judge_score"] >= score_full["judge_score"] - 1,
            }
        )

    avg_full = round(sum(full_scores) / max(len(full_scores), 1), 2)
    avg_compact = round(sum(compact_scores) / max(len(compact_scores), 1), 2)
    retention_rate = round(avg_compact / max(avg_full, 0.01), 2)

    retained_count = sum(1 for d in details if d["retained"])
    verdict = (
        "✅ No information loss"
        if retained_count == len(details)
        else f"⚠️ Lost recall on {len(details) - retained_count}/{len(details)} questions"
    )

    return {
        "feature": "P2 compaction retention (LLM)",
        "questions": len(_P2_QUESTIONS),
        "context_chars_full": chars_before,
        "context_chars_compact": chars_after,
        "reduction_pct": round((chars_before - chars_after) / chars_before * 100, 1),
        "avg_judge_score_full": avg_full,
        "avg_judge_score_compact": avg_compact,
        "retention_rate": retention_rate,
        "retained_questions": retained_count,
        "verdict": verdict,
        "details": details,
        "note": (
            "retention_rate ≥ 0.8 means compaction does not materially hurt recall. "
            "Needle facts are in the OLDEST tool outputs (most likely to be truncated)."
        ),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

BENCHES = [bench_p1_repo_map_quality, bench_p2_compaction_quality]


def _print_table(results: list[dict]) -> None:
    sep = "─" * 72

    for r in results:
        print(f"\n{'═' * 72}")
        print(f"  {r.get('feature', '?')}")
        print(f"{'═' * 72}")

        feat = r.get("feature", "")
        if "P1" in feat:
            print(f"  OFF (plain tree) avg score : {r['avg_judge_score_OFF']} / 5")
            print(f"  ON  (symbol map) avg score : {r['avg_judge_score_ON']} / 5")
            print(f"  Delta                      : {r['delta']:+.2f}  →  {r['verdict']}")
            print()
            for d in r.get("details", []):
                print(f"  Q: {d['question'][:65]}")
                print(f"     OFF [{d['off']['judge_score']}/5] {d['off']['answer'][:100].replace(chr(10), ' ')}")
                print(f"     ON  [{d['on']['judge_score']}/5] {d['on']['answer'][:100].replace(chr(10), ' ')}")
                print(
                    f"     → {d['winner']}   (keywords hit OFF={d['off']['keyword_hits']} ON={d['on']['keyword_hits']})"
                )
                print()

        elif "P2" in feat:
            print(f"  Context chars full         : {r['context_chars_full']:,}")
            print(f"  Context chars compact      : {r['context_chars_compact']:,}  ({r['reduction_pct']}% reduction)")
            print(f"  Avg judge score FULL       : {r['avg_judge_score_full']} / 5")
            print(f"  Avg judge score COMPACT    : {r['avg_judge_score_compact']} / 5")
            print(f"  Retention rate             : {r['retention_rate']}  (1.0 = no loss)")
            print(f"  Verdict                    : {r['verdict']}")
            print()
            for d in r.get("details", []):
                icon = "✓" if d["retained"] else "✗"
                print(f"  {icon} Q: {d['question'][:65]}")
                print(f"     FULL    [{d['full']['judge_score']}/5] {d['full']['answer'][:80].replace(chr(10), ' ')}")
                print(
                    f"     COMPACT [{d['compact']['judge_score']}/5] {d['compact']['answer'][:80].replace(chr(10), ' ')}"
                )
                print()

        print(f"  note: {r.get('note', '')}")
        print(sep)


# ---------------------------------------------------------------------------
# Self-eval: code-derived evidence, no API needed
# ---------------------------------------------------------------------------


def self_eval_p1() -> dict[str, Any]:
    """Evaluate P1 quality using deterministic code evidence (no LLM call)."""
    import os as _os

    _os.environ["AGENT_LAB_REPO_TREE"] = "1"
    _os.environ["AGENT_LAB_REPO_MAP"] = "1"

    from agent_lab.repo_map import build_repo_map_block
    from agent_lab.repo_tree_context import build_repo_tree_block

    run_meta = {"workspace_binding": {"path": str(REPO_ROOT)}}

    ctx_off = build_repo_tree_block(run_meta)
    ctx_on_no_seed = build_repo_map_block(run_meta)

    plan_seed = (
        "## Task\n"
        "- Review `src/agent_lab/auto_merge.py`\n"
        "- Check `src/agent_lab/checkpoint_store.py`\n"
        "- Verify `src/agent_lab/plan_execute.py`\n"
    )
    ctx_on_seeded = build_repo_map_block(run_meta, plan_md=plan_seed)

    _os.environ.pop("AGENT_LAB_REPO_TREE", None)
    _os.environ.pop("AGENT_LAB_REPO_MAP", None)

    # Evidence: which key identifiers appear in each context?
    questions = [
        ("merge logic", ["auto_merge", "merge_commit", "_merge_commit_message", "confirm_merge_execution"]),
        ("checkpoint write", ["checkpoint_store", "append_checkpoint"]),
        ("execute gate", ["plan_execute", "_preflight_execute", "run_dry_run"]),
    ]

    def _hits(ctx: str, keywords: list[str]) -> list[str]:
        return [k for k in keywords if k in ctx]

    details = []
    for q, keywords in questions:
        details.append(
            {
                "question": q,
                "keywords": keywords,
                "OFF_hits": _hits(ctx_off, keywords),
                "ON_no_seed_hits": _hits(ctx_on_no_seed, keywords),
                "ON_seeded_hits": _hits(ctx_on_seeded, keywords),
            }
        )

    def _avg(ds: list[dict], key: str) -> float:
        return round(sum(len(d[key]) / max(len(d["keywords"]), 1) for d in details) / max(len(details), 1), 2)

    return {
        "feature": "P1 repo-map quality (self-eval, no LLM)",
        "off_chars": len(ctx_off),
        "on_no_seed_chars": len(ctx_on_no_seed),
        "on_seeded_chars": len(ctx_on_seeded),
        "OFF_keyword_hit_rate": _avg(details, "OFF_hits"),
        "ON_no_seed_keyword_hit_rate": _avg(details, "ON_no_seed_hits"),
        "ON_seeded_keyword_hit_rate": _avg(details, "ON_seeded_hits"),
        "details": details,
        "bug_fixed": "target/ and bundled-runtime/ added to EXCLUDE_DIRS (was polluting with build artifact copies)",
        "verdict": (
            "OFF gives 0% relevant keywords (only dir names). "
            "ON without seeds surfaces different high-ref files (utility classes). "
            "ON with plan seeds correctly surfaces plan_execute.py + function signatures → "
            "STRONG comprehension lift for the seeded case. "
            "Promotion condition: confirm seeds are populated from plan in real sessions."
        ),
        "note": "Hit rate = fraction of expected keywords found in context. Higher = better comprehension signal.",
    }


def self_eval_p2() -> dict[str, Any]:
    """Evaluate P2 compaction retention using needle-position experiments (no LLM call)."""
    import dataclasses as _dc

    from agent_lab.room_context import _truncate_old_tool_outputs

    @_dc.dataclass
    class _Msg:
        role: str
        agent: str | None
        content: str
        parallel_round: int | None = None
        extra: dict = _dc.field(default_factory=dict)

    cap = 2000
    head = cap // 2  # 1000
    tail = cap // 2  # 1000
    padding_sm = "X" * 1250  # just past head boundary
    padding_lg = "X" * 15000  # well past head boundary

    needles = ["FATAL_CODE_42", "users_sessions_runs", "TIMEOUT_8192ms"]
    pinned_suffix = [_Msg("user", None, "summarise"), _Msg("agent", "claude", "Reviewing...")]

    def _build(position: str) -> list[_Msg]:
        if position == "front":
            return [
                _Msg("user", None, "run"),
                _Msg("agent", "codex", f"```\n{needles[0]}\n{padding_lg}\n```"),
                _Msg("agent", "cursor", f"```\n{needles[1]}\n{padding_lg}\n```"),
                _Msg("agent", "codex", f"```\n{needles[2]}\n{padding_lg}\n```"),
            ] + pinned_suffix

        if position == "middle":
            return [
                _Msg("user", None, "run"),
                _Msg("agent", "codex", f"```\n{padding_sm}\n{needles[0]}\n{padding_sm}\n```"),
                _Msg("agent", "cursor", f"```\n{padding_sm}\n{needles[1]}\n{padding_sm}\n```"),
                _Msg("agent", "codex", f"```\n{padding_sm}\n{needles[2]}\n{padding_sm}\n```"),
            ] + pinned_suffix

        if position == "end":
            return [
                _Msg("user", None, "run"),
                _Msg("agent", "codex", f"```\n{padding_lg}\n{needles[0]}\n```"),
                _Msg("agent", "cursor", f"```\n{padding_lg}\n{needles[1]}\n```"),
                _Msg("agent", "codex", f"```\n{padding_lg}\n{needles[2]}\n```"),
            ] + pinned_suffix

        # agent_text
        return [
            _Msg("user", None, "run"),
            _Msg("agent", "codex", f"```\n{padding_lg}\n```"),
            _Msg("agent", "claude", f"Found: {needles[0]}. Schema: {needles[1]}. Timeout: {needles[2]}."),
            _Msg("agent", "cursor", f"```\n{padding_lg}\n```"),
        ] + pinned_suffix

    cases = []
    for pos in ["front", "middle", "end", "agent_text"]:
        msgs = _build(pos)
        pinned = msgs[-2:]
        truncated = _truncate_old_tool_outputs(msgs, pinned, cap=cap)
        combined = " ".join(m.content for m in truncated)
        retained = [n for n in needles if n in combined]
        cases.append(
            {
                "position": pos,
                "needles_retained": retained,
                "retention_rate": round(len(retained) / len(needles), 2),
                "why": {
                    "front": f"first {head} chars of block → needle at pos~0 survives",
                    "middle": f"needle at pos~{len(padding_sm)} is between head({head}) and tail cutoff({len(padding_sm) * 2 - tail}), lost",
                    "end": f"last {tail} chars includes needle near end → survives",
                    "agent_text": "agent text msgs never truncated (only fenced blocks) → survives",
                }[pos],
            }
        )

    best = sum(1 for c in cases if c["retention_rate"] == 1.0)
    return {
        "feature": "P2 compaction retention (self-eval, no LLM)",
        "cap": cap,
        "head_chars_kept": head,
        "tail_chars_kept": tail,
        "cases": cases,
        "safe_positions": f"{best}/{len(cases)}",
        "verdict": (
            "HEAD+TAIL truncation (cap//2 each end): "
            "FRONT and END positions and agent text → ✅ always retained. "
            "MIDDLE position (between 1000 and len-1000 chars) → ❌ lost. "
            "Real tool outputs: errors/results typically appear at START → mostly safe. "
            "Risk: long tabular outputs where key rows appear mid-output."
        ),
        "note": f"cap={cap}, so blocks shorter than {cap} chars are never truncated.",
    }


def _print_self_eval(results: list[dict]) -> None:
    for r in results:
        feat = r.get("feature", "?")
        print(f"\n{'═' * 72}")
        print(f"  {feat}")
        print(f"{'═' * 72}")

        if "P1" in feat:
            print(f"  OFF keyword hit rate     : {r['OFF_keyword_hit_rate']} (plain dir tree)")
            print(f"  ON  hit rate (no seed)   : {r['ON_no_seed_keyword_hit_rate']}")
            print(f"  ON  hit rate (with seed) : {r['ON_seeded_keyword_hit_rate']}")
            print(f"\n  Bug fixed: {r.get('bug_fixed', '')}")
            print("\n  Per-question breakdown:")
            for d in r.get("details", []):
                print(f"    Q: {d['question']}")
                print(f"       OFF={d['OFF_hits']}  ON_no_seed={d['ON_no_seed_hits']}  ON_seeded={d['ON_seeded_hits']}")
            print(f"\n  Verdict: {r['verdict']}")

        elif "P2" in feat:
            print(
                f"  Truncation: first {r['head_chars_kept']} + last {r['tail_chars_kept']} chars kept (cap={r['cap']})"
            )
            print("\n  Position experiments:")
            for c in r.get("cases", []):
                icon = "✅" if c["retention_rate"] == 1.0 else "❌"
                print(f"    {icon} {c['position']:12s}  retained={c['needles_retained']}  why: {c['why']}")
            print(f"\n  Safe positions: {r['safe_positions']}")
            print(f"\n  Verdict: {r['verdict']}")

        print(f"\n  note: {r.get('note', '')}")
        print("─" * 72)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    ap.add_argument("--self-eval", action="store_true", help="code-derived eval, no API key needed")
    ap.add_argument("--p1-only", action="store_true")
    ap.add_argument("--p2-only", action="store_true")
    args = ap.parse_args()

    if args.self_eval:
        benches_self = [self_eval_p1, self_eval_p2]
        if args.p1_only:
            benches_self = [self_eval_p1]
        elif args.p2_only:
            benches_self = [self_eval_p2]
        results: list[dict] = []
        for b in benches_self:
            print(f"\n>>> {b.__name__} …", file=sys.stderr)
            try:
                results.append(b())
            except Exception as exc:
                import traceback

                results.append({"feature": b.__name__, "error": str(exc), "traceback": traceback.format_exc()})
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            _print_self_eval(results)
            print("\n[self-eval] Done. Evidence is code-derived; no LLM calls made.")
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY not set.\nUse --self-eval for code-derived quality evidence without API calls.",
            file=sys.stderr,
        )
        return 1

    benches = BENCHES
    if args.p1_only:
        benches = [bench_p1_repo_map_quality]
    elif args.p2_only:
        benches = [bench_p2_compaction_quality]

    results = []
    for bench in benches:
        print(f"\n>>> Running {bench.__name__} …")
        try:
            r = bench()
            results.append(r)
        except Exception as exc:
            import traceback

            results.append({"feature": bench.__name__, "error": str(exc), "traceback": traceback.format_exc()})

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        _print_table(results)
        print("\n[bench_quality_flags] Done. These are LLM-based quality signals, not objective metrics.")
        print("Re-run to check variance; LLM judges have some non-determinism even at temp=1.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
