#!/usr/bin/env python3
"""Smoke run: ♾️ consensus mode + envelope verification."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / "sessions"
API = "http://127.0.0.1:8765"


def parse_sse(raw: bytes) -> list[dict]:
    events: list[dict] = []
    for block in raw.decode("utf-8", errors="replace").split("\n\n"):
        data_line = next(
            (ln[5:].strip() for ln in block.splitlines() if ln.startswith("data: ")),
            None,
        )
        if data_line:
            try:
                events.append(json.loads(data_line))
            except json.JSONDecodeError:
                pass
    return events


def main() -> int:
    topic = (
        "envelope 스모크: TypeScript vs JavaScript 중 하나만 고르고 "
        "한 줄 근거만. 120자 이내. consensus R2+에는 agent-envelope fence 사용."
    )
    boundary = "----AgentLabSmoke7x"
    fields = [
        ("topic", topic),
        ("agents", json.dumps(["cursor", "codex", "claude"])),
        ("mode", "discuss"),
        ("synthesize", "false"),
        ("synthesize_only", "false"),
        ("agent_rounds", "1"),
        ("review_mode", "false"),
        ("consensus_mode", "true"),
        ("efficiency_mode", "true"),
        ("permissions", "{}"),
    ]
    body = "".join(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
        f"{v}\r\n"
        for k, v in fields
    ) + f"--{boundary}--\r\n"

    print(f"Starting smoke run: {topic[:60]}…")
    t0 = time.time()
    req = urllib.request.Request(
        f"{API}/api/room/runs",
        data=body.encode("utf-8"),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        print("HTTP error:", e.read().decode()[:500])
        return 1
    except TimeoutError:
        print("Timed out after 900s")
        return 1

    elapsed = time.time() - t0
    events = parse_sse(raw)
    print(f"Done in {elapsed:.0f}s — {len(events)} SSE events")

    session_id = None
    agent_done: list[dict] = []
    consensus_status = None
    for ev in events:
        t = ev.get("type")
        if t == "complete":
            session_id = ev.get("session_id")
        if t == "agent_done":
            agent_done.append(ev)
        if t in ("consensus_reached", "consensus_incomplete"):
            consensus_status = ev

    print(f"session_id: {session_id}")
    print(f"agent_done: {len(agent_done)}")
    with_env = [e for e in agent_done if e.get("envelope")]
    print(f"agent_done with envelope: {len(with_env)}")
    for e in agent_done:
        env = e.get("envelope") or {}
        act = env.get("act", "—")
        rnd = e.get("round", "?")
        agent = e.get("agent", "?")
        no_obj = e.get("no_objection")
        print(
            f"  R{rnd} {agent}: act={act} no_objection={no_obj} "
            f"chars={e.get('chars', 0)}"
        )

    if consensus_status:
        print(f"consensus: {consensus_status.get('type')} — {consensus_status.get('status', consensus_status.get('message', ''))}")

    if not session_id:
        errs = [e for e in events if e.get("type") == "error"]
        if errs:
            print("errors:", errs)
        return 1

    chat_path = SESSIONS / session_id / "chat.jsonl"
    if not chat_path.is_file():
        print("chat.jsonl missing:", chat_path)
        return 1

    lines = [json.loads(ln) for ln in chat_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    env_lines = [i for i, row in enumerate(lines) if row.get("envelope")]
    print(f"chat.jsonl lines: {len(lines)}, with envelope: {len(env_lines)}")
    for i in env_lines:
        row = lines[i]
        print(
            f"  L{i+1} {row.get('agent')} R{row.get('parallel_round')} "
            f"act={row.get('envelope', {}).get('act')}"
        )

    if not with_env:
        print("WARN: no envelope in agent_done — agents may not have used fence yet")
    return 0 if session_id and agent_done else 1


if __name__ == "__main__":
    sys.exit(main())
