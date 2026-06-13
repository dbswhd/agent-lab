"""CLI: python -m agent_lab.trading_mission [verify|ingest] ..."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_lab.trading_mission.ingest_bridge import ingest_proposal_batch
from agent_lab.trading_mission.verify import check_artifacts, trading_mission_goal_ok


def _cmd_verify(args: argparse.Namespace) -> int:
    folder = args.session_folder.expanduser().resolve()
    if not folder.is_dir():
        print(f"session folder not found: {folder}", file=sys.stderr)
        return 2

    if args.check == "goal":
        result = trading_mission_goal_ok(folder)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    report = check_artifacts(folder, check=args.check)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


def _cmd_ingest(args: argparse.Namespace) -> int:
    folder = args.session_folder.expanduser().resolve()
    if not folder.is_dir():
        print(f"session folder not found: {folder}", file=sys.stderr)
        return 2
    report = ingest_proposal_batch(
        folder,
        db_path=args.db,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trading Mission CLI")
    sub = parser.add_subparsers(dest="command", required=False)

    verify_p = sub.add_parser("verify", help="Verify session artifacts")
    verify_p.add_argument("session_folder", type=Path, help="Path to session folder")
    verify_p.add_argument(
        "--check",
        default="all",
        choices=("all", "snapshot", "batch", "playbook", "goal"),
    )
    verify_p.set_defaults(func=_cmd_verify)

    ingest_p = sub.add_parser("ingest", help="Ingest proposal_batch to control plane")
    ingest_p.add_argument("session_folder", type=Path, help="Path to session folder")
    ingest_p.add_argument("--db", type=Path, default=None, help="Control plane SQLite path")
    ingest_p.add_argument("--dry-run", action="store_true", help="Validate only, no write")
    ingest_p.add_argument("--force", action="store_true", help="Re-ingest even if mission exists")
    ingest_p.set_defaults(func=_cmd_ingest)

    # Back-compat: `python -m agent_lab.trading_mission <folder> [--check goal]`
    parser.add_argument("session_folder", nargs="?", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--check", default="all", choices=("all", "snapshot", "batch", "playbook", "goal"))

    args = parser.parse_args(argv)
    if args.command:
        return int(args.func(args))
    if args.session_folder is None:
        parser.print_help()
        return 2
    return _cmd_verify(args)


if __name__ == "__main__":
    raise SystemExit(main())
