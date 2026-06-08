#!/usr/bin/env python3
"""Measure communicate KPIs for Hook · Communicate reform baseline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _session_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        p for p in root.iterdir() if p.is_dir() and (p / "run.json").is_file()
    )


def measure_session(folder: Path) -> dict:
    run_path = folder / "run.json"
    try:
        run = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    turns = run.get("turns") or []
    guidance_chars: list[int] = []
    legacy_endorse = 0
    parse_errors = 0
    agent_chars: list[int] = []
    for turn in turns:
        meta = turn.get("communicate_meta") or {}
        if meta.get("guidance_chars"):
            guidance_chars.append(int(meta["guidance_chars"]))
        legacy_endorse += int(meta.get("legacy_endorse_count") or 0)
        parse_errors += int(meta.get("envelope_parse_error_count") or 0)
        ctx = turn.get("context") or {}
        for entry in ctx.get("agents") or []:
            layer = entry.get("layer_chars") or {}
            if layer.get("guidance"):
                guidance_chars.append(int(layer["guidance"]))
    chat = folder / "chat.jsonl"
    if chat.is_file():
        for line in chat.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("role") != "agent":
                continue
            body = str(msg.get("content") or "")
            agent_chars.append(len(body))
            from agent_lab.reply_policy import legacy_endorse_enabled

            if (
                legacy_endorse_enabled()
                and "이의 없습니다" in body[:40]
                and not msg.get("envelope")
            ):
                legacy_endorse += 1
    return {
        "session": folder.name,
        "turn_count": len(turns),
        "avg_agent_chars": (
            sum(agent_chars) / len(agent_chars) if agent_chars else 0
        ),
        "median_guidance_chars": sorted(guidance_chars)[len(guidance_chars) // 2]
        if guidance_chars
        else 0,
        "legacy_endorse_count": legacy_endorse,
        "envelope_parse_errors": parse_errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sessions",
        type=Path,
        default=Path("sessions"),
        help="Sessions root directory",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: sessions/_reports/communicate-baseline-DATE.json)",
    )
    args = parser.parse_args()
    rows = [measure_session(p) for p in _session_dirs(args.sessions)]
    rows = [r for r in rows if r]
    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_count": len(rows),
        "avg_agent_chars": (
            sum(r["avg_agent_chars"] for r in rows) / len(rows) if rows else 0
        ),
        "total_legacy_endorse": sum(r["legacy_endorse_count"] for r in rows),
        "total_parse_errors": sum(r["envelope_parse_errors"] for r in rows),
        "sessions": rows,
    }
    out = args.out
    if out is None:
        reports = args.sessions / "_reports"
        reports.mkdir(parents=True, exist_ok=True)
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
        out = reports / f"communicate-baseline-{date}.json"
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
