"""100+ dual-write 합성 cohort — 격리 디렉터리에서 route cohort를 반복 실행."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--repos", type=Path, required=True)
    parser.add_argument("--loops", type=int, default=10, help="each loop ≈10 mirrored route ops")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    args.sessions.mkdir(parents=True, exist_ok=True)
    args.repos.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(ROOT / "scripts"))
    from mission_dual_write_route_cohort import run_cohort

    loop_reports: list[dict[str, object]] = []
    all_pass = True
    for index in range(1, args.loops + 1):
        prefix = f"syn{index:02d}-route"
        report = run_cohort(args.sessions, args.repos / f"loop-{index:02d}", prefix=prefix)
        loop_reports.append({"loop": index, "prefix": prefix, **report})
        if not (report["cohort_parity_pass"] and report["rollback_pass"] and report["extended_pass"]):
            all_pass = False

    verify = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mission_dual_write_verify.py"), "--sessions", str(args.sessions)],
        capture_output=True,
        text=True,
        check=False,
    )
    verify_report = json.loads(verify.stdout) if verify.stdout.strip() else {"error": verify.stderr[:500]}

    out = {
        "kind": "synthetic_cohort",
        "loops": args.loops,
        "approx_dual_write_ops": args.loops * 10,
        "all_pass": all_pass,
        "verify_exit_code": verify.returncode,
        "verify_hard_mismatch_count": verify_report.get("hard_mismatch_count"),
        "migrated_count": verify_report.get("migrated_count"),
        "loops_detail": loop_reports,
    }
    text = json.dumps(out, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        args.report.write_text(text + "\n", encoding="utf-8")
    return 0 if all_pass and verify.returncode == 0 and verify_report.get("hard_mismatch_count", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
