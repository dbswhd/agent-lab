# Track 2.2 native micro-bench gate — CLOSED RECORD

> **STATUS: CLOSED 2026-06-28.** Native rejected. `crates/agent_lab_native`, the
> micro-bench script, and the baseline JSON were **deleted**; this file is the
> durable record so the result is not re-litigated. Code preserved in git history.
>
> ADR: [HYBRID-RUST-PYTHON-ADR.md](./HYBRID-RUST-PYTHON-ADR.md) (see AMENDMENT 2026-06-28)

## Outcome

`agent_lab_native` (PyO3 `syntax_gate_core`) was evaluated for graduation from dev-only POC to **bundled `.app` runtime**. **Rejected** — it cannot beat CPython `compile()` (a C fast path), and even a hypothetical free Rust win cannot clear the relief gate (syntax_gate is ~25 ms of a ~32 s mock turn).

## Gates (both required)

| Gate | Rule | Track 2.0 N |
|------|------|-------------|
| **Speed** | Rust best-of ≤ Python best-of × 0.8 | 20% faster |
| **Mock-turn relief** | `(python_ms − rust_ms) / mock_turn_denominator × 100` | ≥ **5%** |

Denominator: `context_build_total_ms + python_syntax_ms + agent_stub_ms` from profile baseline.

## Latest result (agent-lab repo, 2026-06-28)

| Metric | Value |
|--------|-------|
| Python `compile()` scan (~40 files) | ~25 ms |
| Rust `rustpython-parser` scan | ~190 ms |
| Speed gate | **FAIL** (~660% slower) |
| Mock-turn relief | **FAIL** (negative — Rust adds cost) |
| **Decision** | **FAIL** — do **not** bundle native; keep Python SSOT |

## Interpretation

1. **CPython `compile()` is already a C fast path** — a pure-Rust parser does not beat it for merge-gate syntax checks.
2. **`syntax_gate` is ~29 ms** vs ~30 s agent stub — even a hypothetical 20× Rust win would not clear 5% mock-turn relief.
3. **`AGENT_LAB_SYNTAX_GATE_RUST`** flag, the Rust shim, and the bundle guard were **removed** — Python `compile()` is the only path.
4. **repo_map** was the other native candidate. Its apparent cost (~800 ms / ~98% of context build, Phase 2.0) turned out to be a **Python over-scan bug** (`bound_python_files` only pruned above `MAX_FILES=2000`). Fixed in Python — seed + import-hop-1 bounding: **780 ms → 134 ms (5.8×)**. No native ROI; candidate closed.

## Why this is permanent

Both Track 2 native candidates are closed for structural, not incidental, reasons:

- **syntax_gate**: replacing a C fast path (`compile()`) with Rust has no inherent win, and Amdahl caps relief at ~0.078% of a turn.
- **repo_map**: the cost was a Python algorithm bug; the fix is Python, and the fixed path leaves nothing for Rust to win.

**Re-open trigger (only):** repo scan volume grows ≥100× (e.g. giant monorepo merge scanning 10k+ files), where parallel no-GIL parsing could matter — and even then, re-measure the Python path first.
