from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from agent_lab.mission.scheduler_shadow import enqueue_scheduler_shadow_candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True)
    args = parser.parse_args()
    report = enqueue_scheduler_shadow_candidates(args.sessions, now=datetime.now(timezone.utc))
    print(
        " ".join(
            (
                f"checked={report.checked}",
                f"candidates={len(report.candidate_ids)}",
                f"translation_parity={report.translation_parity}",
                f"queue_parity={report.queue_parity}",
                f"missing={len(report.missing_queue_ids)}",
                f"unexpected={len(report.unexpected_queue_ids)}",
            )
        )
    )
    return 0 if report.translation_parity and report.queue_parity else 1


if __name__ == "__main__":
    raise SystemExit(main())
