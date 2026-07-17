#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import tarfile
import tempfile
import time
from types import FrameType
from pathlib import Path
from m6_packet_verify import validate_allowlist_payload, verify_packet
from typing import Final

PACKET_NAME: Final = "m6-final-retire-2026-07-14"
ALLOWLIST_RELATIVE: Final = "docs/redesign-2026-07/m6-compatibility-consumer-allowlist-2026-07-14.json"
REQUIRED_EVIDENCE: Final = tuple([f"task-{number}.json" for number in range(1, 11)] + ["live-clean-restart.json"])
CODE_CONFIG_PATHS: Final = (
    "src/agent_lab/mission/tick.py",
    "src/agent_lab/mission/advance.py",
    "src/agent_lab/runtime/transitions.py",
    "src/agent_lab/runtime/orchestration.py",
    "src/agent_lab/clarity.py",
    "app/server/routers/room.py",
    "src/agent_lab/mission/dual_write.py",
    "src/agent_lab/run/profile.py",
    "src/agent_lab/runtime_flags.py",
    "src/agent_lab/plan/workflow_approval.py",
    "web/src/components/ComposerEventStack.tsx",
    "web/src/components/WorkToolPanel.tsx",
    "web/src/components/HumanInboxPanel.tsx",
    "web/src/hooks/useRoomSseHandler.ts",
    "web/src/hooks/useRoomChatInteractions.ts",
    "web/src/utils/workStatusPhase.ts",
    "web/src/utils/missionReadModel.ts",
    "docs/redesign-2026-07/m6-compatibility-consumer-allowlist-2026-07-14.json",
)
DELETE_CANDIDATES: Final = tuple(CODE_CONFIG_PATHS[:6])
PROTECTED_PATHS: Final = (
    "src/agent_lab/human_inbox.py",
    "app/server/routers/human_inbox.py",
    "app/server/routers/plan_execute.py",
    "src/agent_lab/merge_gate.py",
    "src/agent_lab/oracle_core.py",
    "src/agent_lab/plan/execute_merge.py",
    "src/agent_lab/plan/execute_verify.py",
    "src/agent_lab/mission/dual_write.py",
    "src/agent_lab/run/profile.py",
    "src/agent_lab/runtime_flags.py",
    "src/agent_lab/plan/workflow_approval.py",
    "src/agent_lab/mission/read_model.py",
)
REDACTIONS: Final = (
    (re.compile(r"/Users/[^\s\"']+"), "<REDACTED_PATH>"),
    (re.compile(r"/private/var/[^\s\"']+"), "<REDACTED_TMP>"),
    (re.compile(r"/tmp/[^\s\"']+"), "<REDACTED_TMP>"),
    (re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"), "<REDACTED_EMAIL>"),
)


class PacketBuildInterrupted(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _redact(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_allowlist(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("compatibility allowlist is missing or not a regular file")
    data = path.read_bytes()
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise RuntimeError("compatibility allowlist is not valid JSON") from exc
    validate_allowlist_payload(payload)
    return data


def _validate_coverage(coverage: dict[str, object], staging: Path) -> None:
    required = {
        "wave_a_projection",
        "wave_b_parity",
        "bounded_ui_soak",
        "rollback_recovery",
        "m6_8_duplicate_patch_stop",
        "m6_9_bridge_flag_retire",
        "consumer_scan",
        "consumer_inventory",
        "final_verification",
        "redaction",
    }
    if set(coverage) != required:
        raise RuntimeError("coverage entries are incomplete")

    def walk(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and (
            value.startswith("evidence/") or value.startswith("reports/") or value.startswith("code-config/")
        ):
            if not (staging / value).is_file():
                raise RuntimeError(f"coverage references missing evidence: {value}")

    walk(coverage)


def _session_index(root: Path) -> list[dict[str, object]]:
    sessions = root / "sessions"
    if not sessions.is_dir():
        return []
    rows: list[dict[str, object]] = []
    for source in sorted(path for path in sessions.rglob("*") if path.is_file()):
        relative = source.relative_to(sessions).as_posix()
        rows.append(
            {
                "path_token": hashlib.sha256(relative.encode()).hexdigest(),
                "kind": "journal" if source.suffix == ".jsonl" else "session_metadata",
                "size": source.stat().st_size,
                "sha256": _sha256(source),
            }
        )
    return rows


def _copy_redacted(root: Path, source_name: str, destination: Path) -> None:
    source = root / source_name
    if not source.is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_redact(source.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")


def _file_hashes(folder: Path) -> dict[str, str]:
    return {
        path.relative_to(folder).as_posix(): _sha256(path)
        for path in sorted(path for path in folder.rglob("*") if path.is_file())
    }


def build_packet(root: Path, output: Path) -> Path:
    if output.exists():
        raise FileExistsError(f"immutable packet already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.parent / f".{output.name}.partial-{os.getpid()}"
    if partial.exists():
        raise FileExistsError(f"partial packet already exists: {partial}")
    old_term = signal.getsignal(signal.SIGTERM)
    old_int = signal.getsignal(signal.SIGINT)

    def interrupt(_signum: int, _frame: FrameType | None) -> None:
        raise PacketBuildInterrupted("packet build interrupted")

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    committed = False
    try:
        with tempfile.TemporaryDirectory(prefix="m6-retire-staging-") as staging_name:
            staging = Path(staging_name)
            (staging / "code-config").mkdir()
            allowlist_source = root / ALLOWLIST_RELATIVE
            _load_allowlist(allowlist_source)
            for relative in CODE_CONFIG_PATHS:
                _copy_redacted(root, relative, staging / "code-config" / relative)
            evidence = staging / "evidence"
            evidence_root = root / ".omo/evidence/wave-b-m6-retire"
            for filename in REQUIRED_EVIDENCE:
                source = evidence_root / filename
                if source.is_symlink() or not source.is_file():
                    raise RuntimeError(f"required evidence is missing: {filename}")
                try:
                    payload = json.loads(source.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"required evidence is not valid JSON: {filename}") from exc
                if not isinstance(payload, dict):
                    raise RuntimeError(f"required evidence must be a JSON object: {filename}")
                _copy_redacted(root, source.relative_to(root).as_posix(), evidence / source.name)
            _copy_redacted(
                root,
                "docs/redesign-2026-07/evidence/m6-precheck-retire-scope-2026-07-14.md",
                staging / "reports/m6-precheck.md",
            )
            _copy_redacted(
                root,
                "docs/redesign-2026-07/evidence/dual-write-ui-read-model-bounded-cutover-evidence-2026-07-14.md",
                staging / "reports/ui-soak.md",
            )
            baseline = Path("/tmp/m6-baseline.txt")
            (staging / "baseline.txt").write_text(
                _redact(baseline.read_text(encoding="utf-8"))
                if baseline.is_file()
                else "baseline capture unavailable\n",
                encoding="utf-8",
            )
            _write_json(
                staging / "sessions-journals-index.json",
                {
                    "policy": "checksum-only; raw session/journal content is not copied to avoid secrets or PII",
                    "entries": _session_index(root),
                },
            )
            _write_json(
                staging / "deletion-manifest.json",
                {
                    "schema_version": 1,
                    "decision": "NO-GO",
                    "approval_required": {"separate_human": True, "two_person_confirmation": True},
                    "candidates": list(DELETE_CANDIDATES),
                    "protected_never_delete_in_m6": list(PROTECTED_PATHS),
                },
            )
            _write_json(
                staging / "decision.json",
                {
                    "status": "NO-GO",
                    "reason": "separate Human approval for irreversible deletion is absent",
                    "manifest_scope_note": "Deletion manifest retains 6 candidates and 12 protected paths; the authoritative compatibility inventory is 18 scoped files and 275 references, superseding the pre-Todo-5 12-file/251-reference baseline.",
                    "owner": None,
                    "approver_one": None,
                    "approver_two": None,
                    "approved_at": None,
                    "approval_artifact": None,
                },
            )
            _write_json(
                staging / "coverage.json",
                {
                    "wave_a_projection": [f"evidence/task-{number}.json" for number in range(1, 5)],
                    "wave_b_parity": ["evidence/task-5.json", "evidence/task-6.json"],
                    "bounded_ui_soak": ["evidence/task-7.json", "reports/ui-soak.md"],
                    "rollback_recovery": ["evidence/task-7.json", "evidence/task-8.json", "evidence/task-9.json"],
                    "m6_8_duplicate_patch_stop": "evidence/task-8.json",
                    "m6_9_bridge_flag_retire": "evidence/task-9.json",
                    "consumer_scan": [
                        "evidence/task-4.json",
                        "code-config/docs/redesign-2026-07/m6-compatibility-consumer-allowlist-2026-07-14.json",
                    ],
                    "consumer_inventory": {
                        "target_files": 18,
                        "references": 275,
                        "baseline_target_files": 12,
                        "baseline_references": 251,
                    },
                    "final_verification": ["evidence/task-10.json", "evidence/live-clean-restart.json"],
                    "redaction": "evidence and reports redact user/temp paths and email-like values; session/journal content is checksum-only",
                },
            )
            _validate_coverage(json.loads((staging / "coverage.json").read_text(encoding="utf-8")), staging)
            (staging / "README.md").write_text(
                "# M6 final retire packet\n\nStatus: **NO-GO**. This packet archives redacted evidence and checksums only. "
                "No product, writer, implementer, bridge, flag, session, or journal was deleted.\n\n"
                "The deletion manifest remains authoritative for 6 candidates and 12 protected paths. The compatibility inventory is "
                "authoritatively 18 scoped files and 275 references; the earlier 12-file/251-reference values are retained only as the pre-Todo-5 baseline.\n\n"
                "Session/journal material is checksum-only; raw content remains in place. A separate Human "
                "two-person approval artifact is required before any irreversible deletion.\n",
                encoding="utf-8",
            )
            _write_json(staging / "archive-manifest.json", {"schema_version": 1, "files": _file_hashes(staging)})
            partial.mkdir()
            pause_seconds = float(os.environ.get("M6_PACKET_BUILD_DELAY_SECONDS", "0"))
            if pause_seconds > 0:
                time.sleep(pause_seconds)
            archive = partial / "m6-final-retire.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                for path in sorted(path for path in staging.rglob("*") if path.is_file()):
                    info = tar.gettarinfo(path, arcname=path.relative_to(staging).as_posix())
                    info.mtime = 0
                    with path.open("rb") as stream:
                        tar.addfile(info, stream)
            archive.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            (partial / "archive.sha256").write_text(f"{_sha256(archive)}  {archive.name}\n", encoding="utf-8")
            (partial / "archive.sha256").chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            for name in (
                "README.md",
                "archive-manifest.json",
                "baseline.txt",
                "coverage.json",
                "deletion-manifest.json",
                "decision.json",
                "sessions-journals-index.json",
            ):
                (partial / name).write_bytes((staging / name).read_bytes())
            _write_json(
                partial / "packet-index.json",
                {
                    "packet": PACKET_NAME,
                    "status": "NO-GO",
                    "archive": archive.name,
                    "archive_sha256": _sha256(archive),
                    "archive_mode": "0444",
                    "manifest_scope": {"candidates": 6, "protected": 12, "source": "current consumer scan"},
                    "consumer_inventory": {
                        "target_files": 18,
                        "references": 275,
                        "baseline_target_files": 12,
                        "baseline_references": 251,
                    },
                    "consumer_allowlist_sha256": _sha256(staging / "code-config" / ALLOWLIST_RELATIVE),
                    "approval": {"owner": None, "approver_one": None, "approver_two": None, "approved_at": None},
                    "deletion_manifest_sha256": _sha256(partial / "deletion-manifest.json"),
                    "redaction": "paths, temporary paths, and email-like values redacted; sessions/journals checksum-only",
                },
            )
            for sidecar in partial.iterdir():
                if sidecar.is_file():
                    sidecar.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        if output.exists():
            raise FileExistsError(f"immutable packet appeared during build: {output}")
        os.replace(partial, output)
        committed = True
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)
        if not committed and partial.exists():
            shutil.rmtree(partial)
    return output


def deletion_guard(root: Path, manifest: Path, approval: Path | None) -> int:
    if approval is None or not approval.is_file():
        print("NO-GO: separate Human approval artifact is absent; no mutation performed")
        return 2
    try:
        record = json.loads(approval.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("NO-GO: approval artifact is not valid JSON; no mutation performed")
        return 2
    if not isinstance(record, dict):
        print("NO-GO: approval artifact must be a JSON object; no mutation performed")
        return 2
    required = ("decision", "owner", "approver_one", "approver_two", "approved_at", "manifest_sha256")
    if record.get("decision") != "GO" or any(not record.get(key) for key in required[1:]):
        print("NO-GO: approval must contain GO, owner, two approvers, timestamp, and manifest hash")
        return 2
    if _sha256(manifest) != record["manifest_sha256"]:
        print("NO-GO: approval manifest hash does not match; no mutation performed")
        return 2
    print("GO approval recorded, but this evidence-only runner never executes deletion")
    return 3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--delete", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args()
    packet = args.output or args.root / "docs/redesign-2026-07/evidence" / PACKET_NAME
    if args.build:
        build_packet(args.root, packet)
        print(f"BUILT: {packet}")
    if args.verify:
        verify_packet(packet, DELETE_CANDIDATES, PROTECTED_PATHS)
        print("VERIFIED: immutable archive checksum and mode")
    if args.delete:
        manifest = args.manifest or packet / "deletion-manifest.json"
        return deletion_guard(args.root, manifest, args.approval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
