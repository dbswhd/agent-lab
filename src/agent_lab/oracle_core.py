"""Shared Oracle prompts, parsing, and evidence policy (execute + goal)."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

OracleKind = Literal["execute", "goal"]

PROMPT_VERSION = "2026-06-26"
_TRUE = {"1", "true", "yes", "on"}
_BACKTICK_LITERAL = re.compile(r"`([^`\n]+)`")
_WORD = re.compile(r"[A-Za-z0-9_가-힣-]{2,}")
_GOAL_STOPWORDS = {
    "goal",
    "session",
    "human",
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "목표",
    "세션",
    "달성",
    "완료",
    "하도록",
    "한다",
    "하기",
}


def _env_true(key: str) -> bool:
    return os.getenv(key, "").strip().lower() in _TRUE


ORACLE_SYSTEM_EXECUTE = (
    "You are the Agent Lab Execute Oracle — an independent verification judge.\n"
    "You are NOT a Room discuss agent, planner, or implementer.\n"
    "Do not propose fixes, rewrite code, or negotiate with agents.\n"
    "Judge only from the evidence bundle in the user message.\n"
    "Reply exactly in the VERDICT / REASON / EVIDENCE format requested."
)

ORACLE_SYSTEM_GOAL = (
    "You are the Agent Lab Session-Goal Oracle — an independent completion judge.\n"
    "You are NOT a Room discuss agent or coach.\n"
    "Decide whether the transcript demonstrates the Human goal is achieved.\n"
    "Prefer concrete backtick literals when the goal specifies them.\n"
    "Reply exactly in the VERDICT / REASON / EVIDENCE format requested."
)


def oracle_system_prompt(kind: OracleKind) -> str:
    return ORACLE_SYSTEM_GOAL if kind == "goal" else ORACLE_SYSTEM_EXECUTE


def resolved_oracle_model(kind: OracleKind) -> str | None:
    """Live oracle model override (falls back to scribe model in ``claude_cli`` when unset)."""
    if kind == "goal":
        raw = (os.getenv("AGENT_LAB_GOAL_ORACLE_MODEL") or os.getenv("AGENT_LAB_ORACLE_MODEL") or "").strip()
    else:
        raw = (os.getenv("AGENT_LAB_ORACLE_MODEL") or "").strip()
    return raw or None


def oracle_live_enabled(*, goal: bool = False) -> bool:
    """Live Claude oracle opt-in. ``AGENT_LAB_ORACLE_LIVE=1`` enables both kinds."""
    if _env_true("AGENT_LAB_ORACLE_LIVE"):
        return True
    if goal and _env_true("AGENT_LAB_GOAL_ORACLE_LIVE"):
        return True
    return False


def parse_oracle_response(raw: str) -> dict[str, Any]:
    """Parse structured or legacy PASS/FAIL oracle output."""
    text = str(raw or "").strip()
    evidence: list[str] = []
    reason = text
    verdict = "fail"

    if not text:
        return {"verdict": "fail", "detail": "empty oracle response", "evidence": evidence}

    upper = text.upper()
    if "EVIDENCE:" in upper:
        head, tail = re.split(r"\bEVIDENCE:\s*", text, maxsplit=1, flags=re.IGNORECASE)
        reason = head.strip()
        for line in tail.splitlines():
            row = line.strip().lstrip("-•*").strip()
            if row:
                evidence.append(row[:240])

    lines = [ln.strip() for ln in reason.splitlines() if ln.strip()]
    first = lines[0].upper() if lines else ""

    if re.search(r"\bVERDICT:\s*PASS\b", upper):
        verdict = "pass"
    elif re.search(r"\bVERDICT:\s*FAIL\b", upper):
        verdict = "fail"
    elif first.startswith("PASS"):
        verdict = "pass"
    elif first.startswith("FAIL"):
        verdict = "fail"
    elif "REASON:" in upper and "VERDICT:" not in upper:
        verdict = "pass" if "PASS" in first else "fail"

    detail = reason
    if lines and lines[0].upper().startswith(("PASS", "FAIL", "VERDICT:")):
        if len(lines) > 1:
            detail = "\n".join(lines[1:]).strip() or lines[0]
        else:
            detail = lines[0]

    return {
        "verdict": verdict,
        "detail": detail[:500],
        "evidence": evidence[:8],
    }


def literal_matches_text(literal: str, text: str) -> bool:
    """True when ``literal`` appears as a standalone token, not a substring (e.g. READY vs NOTREADY)."""
    needle = (literal or "").strip()
    if not needle:
        return False
    pattern = re.compile(
        rf"(?<![\w]){re.escape(needle)}(?![\w])",
        re.IGNORECASE,
    )
    return pattern.search(text) is not None


def verify_literals(verify: str) -> list[str]:
    literals: list[str] = []
    for token in _BACKTICK_LITERAL.findall(verify or ""):
        text = token.strip()
        if not text:
            continue
        if "/" in text or "\\" in text or Path(text).suffix:
            continue
        if text not in literals:
            literals.append(text)
    return literals


def command_hints_from_verify(verify: str) -> list[str]:
    hints: list[str] = []
    for token in _BACKTICK_LITERAL.findall(verify or ""):
        text = token.strip()
        if not text:
            continue
        if text.startswith(("make ", "pytest", "npm ", "python ", "cargo ", "go test")):
            hints.append(text)
    for match in re.finditer(
        r"\b(make\s+[\w.-]+|pytest(?:\s+[\w./-]+)?|npm run \w+)\b",
        verify or "",
        flags=re.IGNORECASE,
    ):
        row = match.group(1).strip()
        if row not in hints:
            hints.append(row)
    return hints[:4]


def session_oracle_context(session_folder: Path | None) -> list[str]:
    """Optional mission notepad + merge hints for live oracle evidence bundle."""
    if session_folder is None:
        return []
    folder = session_folder.expanduser().resolve()
    rows: list[str] = []
    for name in ("verification.md", "learnings.md"):
        path = folder / name
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if body:
            tail = body[-600:] if len(body) > 600 else body
            rows.append(f"[{name} tail]\n{tail}")
    return rows


def build_execute_oracle_prompt(
    verify: str,
    snippets: list[str],
    *,
    extra_evidence: list[str] | None = None,
) -> str:
    files_block = "\n\n".join(snippets) or "(no readable merged file snippets)"
    extras = "\n\n".join(extra_evidence or []) or ""
    commands = command_hints_from_verify(verify)
    cmd_block = ""
    if commands:
        cmd_block = "Suggested commands from criterion:\n" + "\n".join(f"- `{cmd}`" for cmd in commands)
    return (
        f"Verification criterion:\n{verify}\n\n"
        f"Merged file snippets:\n{files_block}\n\n"
        f"{cmd_block}\n\n"
        f"{extras}\n\n"
        "Respond in this format:\n"
        "VERDICT: pass|fail\n"
        "REASON: one or two sentences\n"
        "EVIDENCE:\n"
        "- cite file lines or command outcomes you checked\n"
    ).strip()


def build_goal_oracle_prompt(
    goal_text: str,
    transcript: str,
    *,
    extra_evidence: list[str] | None = None,
) -> str:
    extras = "\n\n".join(extra_evidence or []) or ""
    return (
        f"Goal:\n{goal_text}\n\n"
        f"Transcript (recent):\n{transcript[-12000:] or '(empty)'}\n\n"
        f"{extras}\n\n"
        "Respond in this format:\n"
        "VERDICT: pass|fail\n"
        "REASON: one or two sentences\n"
        "EVIDENCE:\n"
        "- quote or paraphrase transcript lines that support your verdict\n"
    ).strip()


def mock_execute_oracle_response(verify: str, snippets: list[str]) -> str:
    if not snippets:
        return "VERDICT: fail\nREASON: no readable merged files to check\nEVIDENCE:\n- checked_paths empty"
    body = "\n\n".join(snippets)
    literals = verify_literals(verify)
    evidence: list[str] = [f"read {len(snippets)} merged snippet(s)"]
    missing = [literal for literal in literals if not literal_matches_text(literal, body)]
    if missing:
        evidence.append(f"missing literal(s): {', '.join(missing[:5])}")
        return f"VERDICT: fail\nREASON: missing expected literal(s): {', '.join(missing[:5])}\nEVIDENCE:\n" + "\n".join(
            f"- {row}" for row in evidence
        )
    if literals:
        evidence.append(f"found literal(s): {', '.join(literals[:5])}")
        return f"VERDICT: pass\nREASON: found expected literal(s): {', '.join(literals[:5])}\nEVIDENCE:\n" + "\n".join(
            f"- {row}" for row in evidence
        )
    return (
        "VERDICT: pass\n"
        "REASON: mock oracle checked merged files; no explicit literal criterion\n"
        "EVIDENCE:\n- snippets present without backtick literals in criterion"
    )


def mock_goal_oracle_response(goal_text: str, transcript: str) -> str:
    haystack = transcript
    literals = [m.strip() for m in _BACKTICK_LITERAL.findall(goal_text) if m.strip()]
    if literals:
        missing = [literal for literal in literals if not literal_matches_text(literal, haystack)]
        if missing:
            return f"VERDICT: fail\nREASON: missing goal literal(s): {', '.join(missing)}\nEVIDENCE:\n" + "\n".join(
                f"- missing `{lit}` in transcript" for lit in missing[:5]
            )
        return "VERDICT: pass\nREASON: all goal literals appear in the session transcript\nEVIDENCE:\n" + "\n".join(
            f"- found `{lit}` in transcript" for lit in literals[:5]
        )

    keywords = [word for word in dict.fromkeys(_WORD.findall(goal_text)) if word.casefold() not in _GOAL_STOPWORDS][:8]
    if not keywords:
        return (
            "VERDICT: fail\n"
            "REASON: goal needs a backtick literal or concrete keywords\n"
            "EVIDENCE:\n- no literals or keywords to match"
        )
    matched = [word for word in keywords if literal_matches_text(word, haystack)]
    required = max(1, (len(keywords) + 1) // 2)
    if len(matched) >= required:
        return f"VERDICT: pass\nREASON: matched {len(matched)}/{len(keywords)} goal keywords\nEVIDENCE:\n" + "\n".join(
            f"- keyword `{word}` present" for word in matched[:5]
        )
    missing = [word for word in keywords if word not in matched]
    return f"VERDICT: fail\nREASON: missing goal keyword(s): {', '.join(missing[:5])}\nEVIDENCE:\n" + "\n".join(
        f"- keyword `{word}` absent" for word in missing[:5]
    )


def invoke_oracle(
    kind: OracleKind,
    prompt: str,
    *,
    oracle_call: Callable[[str], str] | None = None,
    session_folder: Path | None = None,
) -> tuple[str, str]:
    """Return (raw_response, source)."""
    if oracle_call is not None:
        return str(oracle_call(prompt) or "").strip(), "live"
    if oracle_live_enabled(goal=kind == "goal"):
        from agent_lab.claude import cli as claude_cli
        from agent_lab.sidecar_accounting import tracked_agent_call

        model = resolved_oracle_model(kind)
        system = oracle_system_prompt(kind)

        def _invoke(on_bridge: Callable[[str, dict[str, Any]], None] | None) -> str:
            return claude_cli.invoke(
                system,
                prompt,
                scribe=True,
                room_turn=False,
                model=model,
                on_bridge_event=on_bridge,
                session_folder=session_folder,
            )

        if session_folder is not None and session_folder.is_dir():
            raw = tracked_agent_call(session_folder, "claude", kind="oracle", fn=_invoke)
        else:
            raw = _invoke(None)
        return str(raw or "").strip(), "live"
    if kind == "execute":
        return "", "mock"
    return "", "mock"


def build_oracle_result(
    *,
    raw: str,
    source: str,
    kind: OracleKind,
    verify_criterion: str = "",
    checked_paths: list[str] | None = None,
    goal_text: str = "",
    model: str | None = None,
) -> dict[str, Any]:
    if source == "mock" and not raw.strip():
        if kind == "execute":
            raw = mock_execute_oracle_response(verify_criterion, [])
        else:
            raw = mock_goal_oracle_response(goal_text, "")

    parsed = parse_oracle_response(raw)
    result: dict[str, Any] = {
        "verdict": parsed["verdict"],
        "detail": parsed["detail"],
        "evidence": list(parsed.get("evidence") or []),
        "source": source,
        "prompt_version": PROMPT_VERSION,
    }
    if source == "live":
        live_model = model or resolved_oracle_model(kind)
        if live_model:
            result["model"] = live_model
    if kind == "execute":
        result["verify_criterion"] = verify_criterion
        result["checked_paths"] = list(checked_paths or [])
    return result
