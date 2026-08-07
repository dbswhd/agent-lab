"""Guard: the Inbox row and the autonomy dial must explain a demotion the same way.

``human_demotion_reason`` (Python, Human Inbox) and ``autonomyWhyStopped``
(TypeScript, autonomy dial) translate the same demotion reason codes for two
surfaces. Two copies of one mapping is exactly the shape that rots: the dial
gets a new branch, the Inbox keeps saying something else, and nobody notices
because each side passes its own tests.

This pins the English sentences to each other. Korean lives only in the dial —
the Inbox prompt is English like every other inbox row — so only the `en` side
is compared.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agent_lab.autonomy_inbox import human_demotion_reason

ROOT = Path(__file__).resolve().parents[1]
LADDER_TS = ROOT / "web" / "src" / "utils" / "autonomyLadder.ts"

# Reason codes that actually reach a demotion transition today.
REASON_CODES = [
    "trust_budget_consumed",
    "budget_consumed",
    "oracle_fail_consecutive",
    "diff_risk_high",
    "high_risk",
    "quarter_budget_usd",
    "cost_ledger_exhausted",
    "risk_pin: risk category 'trading' detected",
    "inbox_restore_ceiling",
]


def _ts_english_sentences() -> set[str]:
    """English return values in autonomyWhyStopped — the ko/en ternary's else arm."""
    src = LADDER_TS.read_text(encoding="utf-8")
    start = src.index("export function autonomyWhyStopped")
    end = src.index("\n}", start)
    body = src[start:end]
    # `: "English sentence";` — the en branch of each ko ? … : … ternary
    return {m for m in re.findall(r':\s*"([A-Z][^"]+\.)"', body)}


def test_python_sentences_exist_in_the_dial_mapping() -> None:
    """Every sentence the Inbox can produce must also be a dial sentence."""
    ts_sentences = _ts_english_sentences()
    assert ts_sentences, "could not parse English sentences out of autonomyWhyStopped"

    mismatched = []
    for code in REASON_CODES:
        produced = human_demotion_reason(code)
        if produced not in ts_sentences:
            mismatched.append(f"{code!r} → {produced!r}")

    assert not mismatched, (
        "Inbox wording drifted from the autonomy dial — update both "
        "human_demotion_reason and autonomyWhyStopped together:\n  " + "\n  ".join(mismatched)
    )


def test_every_dial_branch_has_a_python_counterpart() -> None:
    """The dial must not gain an explanation the Inbox cannot produce."""
    ts_sentences = _ts_english_sentences()
    produced = {human_demotion_reason(code) for code in REASON_CODES}
    # The empty-reason fallback is reachable in both.
    produced.add(human_demotion_reason(""))
    missing = sorted(ts_sentences - produced)
    assert not missing, (
        "the dial explains cases the Inbox cannot — add the branch to "
        "human_demotion_reason (or a reason code to REASON_CODES):\n  " + "\n  ".join(missing)
    )


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("trust_budget_consumed", "The auto-continue budget ran out."),
        ("risk_pin: risk category 'trading' detected", "A risk category (e.g. trading) pinned a more careful mode."),
        ("", "Auto-run was turned down."),
    ],
)
def test_reason_sentences(code: str, expected: str) -> None:
    assert human_demotion_reason(code) == expected


def test_unknown_reason_is_passed_through_not_swallowed() -> None:
    assert human_demotion_reason("something we have not seen") == "something we have not seen"
