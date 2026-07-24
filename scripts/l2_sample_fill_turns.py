#!/usr/bin/env python3
"""C1 / N4-D3 — fill L2 tagged outcome rows via live supervisor turns.

Prefer this after autonomy ceiling persists across room turns
(``SESSION_META_KEYS`` includes ``autonomy`` / ``trust_budget``). Full
execute→Oracle soak remains optional; §1.4.1 only needs n≥10 / level.

Usage:
  eval "$(make -s x2-lift-dogfood-env)"
  export AGENT_LAB_PLAN_INBOX=1 AGENT_LAB_X2_AGENTS=cursor
  make api   # inherit flags
  .venv/bin/python scripts/l2_sample_fill_turns.py --need 9 [--session-id SID]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for _p in (ROOT / "src", SCRIPTS, ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

os.environ.setdefault("AGENT_LAB_X2_AGENTS", "cursor")

import x2_lift_dogfood_live_repeat as x2  # noqa: E402


def _level_counts() -> dict[str, int]:
    spec = importlib.util.spec_from_file_location("dt", SCRIPTS / "dogfood_track.py")
    assert spec and spec.loader
    dt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dt)
    return dt._level_sample_counts()


def _promote_l2(session_id: str) -> str | None:
    body = x2._json_request(
        "PATCH",
        x2._session_path(session_id, "/autonomy"),
        {"level": "L2", "reason": "n4_d3_c1_sample_fill"},
        timeout=60.0,
    )
    aut = body.get("autonomy") or {}
    return aut.get("effective_level") or aut.get("level")


def _topic(i: int, total: int) -> str:
    return (
        f"[N4-D3 L2 sample {i}/{total}] 이 턴은 표본 수집용입니다. "
        "docs/_dogfood / plan.md / artifacts 수정 금지. "
        f"'L2 sample {i} acknowledged' 한 줄만 답하세요."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--need", type=int, default=9)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--room-timeout", type=float, default=900.0)
    parser.add_argument("--target-l2", type=int, default=10)
    args = parser.parse_args()

    before = _level_counts()
    print(f"level_counts before: {before}", flush=True)
    if before.get("L2", 0) >= args.target_l2:
        print(f"L2 already ≥{args.target_l2}", flush=True)
        return 0

    session_id = (args.session_id or "").strip() or None
    if not session_id:
        print("=== bootstrap room ===", flush=True)
        x2._prepare_dogfood()
        session_id, events, elapsed, note = x2._room_run(timeout=args.room_timeout)
        print(
            json.dumps(
                {
                    "session_id": session_id,
                    "room_seconds": round(elapsed, 1),
                    "sse_events": len(events),
                    "note": note,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if not session_id:
            print("no session_id", file=sys.stderr)
            return 1

    level = _promote_l2(session_id)
    print(f"promoted effective_level={level} session={session_id}", flush=True)

    results: list[dict] = []
    need = max(0, args.need)
    for i in range(1, need + 1):
        print(f"\n=== L2 sample turn {i}/{need} ===", flush=True)
        _sid, evs, el, n = x2._room_run(
            session_id=session_id,
            timeout=args.room_timeout,
            topic_override=_topic(i, need),
        )
        run = json.loads((ROOT / "sessions" / session_id / "run.json").read_text(encoding="utf-8"))
        row = {
            "i": i,
            "room_seconds": round(el, 1),
            "sse_events": len(evs),
            "note": n,
            "disk_lvl": (run.get("autonomy") or {}).get("level"),
            "counts": _level_counts(),
        }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if row["disk_lvl"] != "L2":
            print("WARN: autonomy wiped after turn — SESSION_META_KEYS fix missing?", file=sys.stderr)
            return 1
        if row["counts"].get("L2", 0) >= args.target_l2:
            print("L2 target reached", flush=True)
            break
        time.sleep(0.5)

    after = _level_counts()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "before": before,
        "after": after,
        "passes": results,
        "ok": after.get("L2", 0) >= args.target_l2,
    }
    out_path = ROOT / "sessions" / "_benchmark" / "reports" / f"l2-sample-fill-{stamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"after": after, "ok": out["ok"], "path": str(out_path)}, ensure_ascii=False), flush=True)
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
