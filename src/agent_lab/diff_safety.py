"""Pre-merge diff safety scanner (G6).

Scans the *added* lines of an execution's unified diff for hard-coded secrets
and dangerous shell commands before the change can be merged. Findings are
cached on ``execution['safety_scan']`` at dry-run time and surfaced through
``merge_checks.build_merge_checks`` (which gates the merge button + auto-merge).

Design notes:
- Only added lines (``+`` but not the ``+++`` header) are scanned — context and
  removed lines are pre-existing and not introduced by this change.
- Matched secret values are *redacted* in stored snippets so run.json / logs
  never persist the plaintext secret.
- A line carrying the ``agent-lab: allow-secret`` marker is skipped (human
  override for known-safe fixtures). Findings under ``tests/`` / ``fixtures/``
  are downgraded to non-blocking ``warn`` severity.
"""

from __future__ import annotations

import re
from typing import Any

from agent_lab.env_flags import env_bool

ALLOW_MARKER = "agent-lab: allow-secret"

# (rule name, compiled pattern, optional value-capture group index)
_SECRET_RULES: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}"), 0),
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"), 0),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), 0),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), 0),
    (
        "jwt",
        re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        0,
    ),
    (
        "generic_secret",
        re.compile(
            r"(?i)(?:api[_-]?key|secret|token|passwd|password|access[_-]?key)"
            r"\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{16,})"
        ),
        1,
    ),
)

_DANGER_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("rm_rf_root", re.compile(r"\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+(?:/|~|\$HOME|/\*)")),
    ("force_push", re.compile(r"\bgit\s+push\b[^\n]*\s(?:-f|--force)(?!-with-lease)\b")),
    ("curl_pipe_shell", re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh)\b")),
    ("fork_bomb", re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")),
)


def diff_safety_enabled() -> bool:
    return env_bool("AGENT_LAB_DIFF_SAFETY", default=True)


def _is_lenient_path(path: str) -> bool:
    p = path.lower()
    return (
        "tests/" in p
        or "/test/" in p
        or p.startswith("test")
        or "fixtures/" in p
        or "__fixtures__" in p
        or "/testdata/" in p
    )


def _redact(value: str) -> str:
    value = value.strip()
    if len(value) <= 4:
        return "***"
    return value[:4] + "***"


def _redact_line(line: str, matched: str) -> str:
    snippet = line.replace(matched, _redact(matched))
    snippet = snippet.strip()
    return snippet[:120]


def scan_diff(diff_text: str | None) -> dict[str, Any]:
    """Scan a unified diff's added lines. Returns a cacheable result dict.

    ``ok`` is False only when at least one *blocking* (non-``warn``) finding
    exists, so test/fixture secrets and danger patterns inform without hard
    gating low-risk paths.
    """
    findings: list[dict[str, Any]] = []
    current_file = ""
    new_line_no = 0
    for raw in (diff_text or "").splitlines():
        if raw.startswith("+++ "):
            current_file = raw[4:].strip()
            if current_file.startswith("b/"):
                current_file = current_file[2:]
            continue
        if raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            new_line_no = int(m.group(1)) if m else 0
            continue
        if raw.startswith("-") or raw.startswith("---"):
            continue
        if not raw.startswith("+"):
            # context line — advances the new-file line counter
            new_line_no += 1
            continue
        # added line
        content = raw[1:]
        line_no = new_line_no
        new_line_no += 1
        lenient = _is_lenient_path(current_file)
        marker = ALLOW_MARKER in content
        if not marker:
            for name, pattern, group in _SECRET_RULES:
                match = pattern.search(content)
                if not match:
                    continue
                value = match.group(group) if group and match.groups() else match.group(0)
                findings.append(
                    {
                        "kind": "secret",
                        "rule": name,
                        "file": current_file,
                        "line": line_no,
                        "snippet": _redact_line(content, value),
                        "severity": "warn" if lenient else "block",
                    }
                )
        for name, pattern in _DANGER_RULES:
            match = pattern.search(content)
            if not match:
                continue
            findings.append(
                {
                    "kind": "danger",
                    "rule": name,
                    "file": current_file,
                    "line": line_no,
                    "snippet": content.strip()[:120],
                    "severity": "warn" if lenient else "block",
                }
            )
    blocking = [f for f in findings if f.get("severity") == "block"]
    counts = {
        "secret": sum(1 for f in findings if f["kind"] == "secret"),
        "danger": sum(1 for f in findings if f["kind"] == "danger"),
        "blocking": len(blocking),
    }
    return {"ok": not blocking, "findings": findings, "counts": counts}


def scan_summary(scan: dict[str, Any] | None) -> str:
    """One-line human summary for a scan result (merge-checks detail)."""
    if not isinstance(scan, dict):
        return "not scanned"
    counts = scan.get("counts") or {}
    return f"{counts.get('secret', 0)} secret(s), {counts.get('danger', 0)} danger(s)"
