from __future__ import annotations

import hashlib
import json
import re
import stat
import tarfile
from pathlib import Path
from pathlib import PurePosixPath


ALLOWLIST_ARCHIVE_PATH = "code-config/docs/redesign-2026-07/m6-compatibility-consumer-allowlist-2026-07-14.json"
PACKET_SIDECARS = (
    "m6-final-retire.tar.gz",
    "archive.sha256",
    "archive-manifest.json",
    "deletion-manifest.json",
    "decision.json",
    "coverage.json",
    "README.md",
    "baseline.txt",
    "sessions-journals-index.json",
    "packet-index.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(data: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(data)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a JSON object")
    return value


def validate_allowlist_payload(payload: object) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeError("compatibility allowlist schema is invalid")
    scope = payload.get("scope")
    entries = payload.get("entries")
    references = payload.get("references")
    if not isinstance(scope, dict) or not isinstance(entries, list) or not isinstance(references, list):
        raise RuntimeError("compatibility allowlist shape is invalid")
    target_files = scope.get("target_files")
    if (
        not isinstance(target_files, list)
        or not target_files
        or not all(isinstance(item, str) and item for item in target_files)
    ):
        raise RuntimeError("compatibility allowlist target_files are invalid")
    if len(set(target_files)) != len(target_files):
        raise RuntimeError("compatibility allowlist target_files contain duplicates")
    entry_paths: set[str] = set()
    required_entry_fields = ("id", "path", "owner", "operation", "retirement_checkpoint")
    for entry in entries:
        if not isinstance(entry, dict) or any(not entry.get(field) for field in required_entry_fields):
            raise RuntimeError("compatibility allowlist entry is invalid")
        path = entry.get("path")
        if not isinstance(path, str):
            raise RuntimeError("compatibility allowlist entry path is invalid")
        entry_paths.add(path)
    if entry_paths != set(target_files):
        raise RuntimeError("compatibility allowlist entries do not cover target_files")
    if not references or not all(isinstance(item, str) and item for item in references):
        raise RuntimeError("compatibility allowlist references are invalid")
    if len(set(references)) != len(references):
        raise RuntimeError("compatibility allowlist references contain duplicates")
    target_set = set(target_files)
    for reference in references:
        path, line, kind = reference.rsplit(":", 2) if reference.count(":") >= 2 else ("", "", "")
        if path not in target_set or not re.fullmatch(r"[1-9][0-9]*", line) or not kind:
            raise RuntimeError("compatibility allowlist reference is invalid")


def _validate_member_name(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or path.as_posix() != name or ".." in path.parts or not name:
        raise RuntimeError(f"archive member path is unsafe: {name!r}")


def verify_packet(packet: Path, candidates: tuple[str, ...], protected: tuple[str, ...]) -> None:
    if not packet.is_dir():
        raise RuntimeError("packet directory is missing")
    files = {path.name for path in packet.iterdir() if path.is_file()}
    if files != set(PACKET_SIDECARS):
        raise RuntimeError("packet sidecars are incomplete or contain extras")
    for name in PACKET_SIDECARS:
        if stat.S_IMODE((packet / name).stat().st_mode) != 0o444:
            raise RuntimeError(f"packet sidecar is not read-only (0444): {name}")
    archive = packet / "m6-final-retire.tar.gz"
    actual = _sha256(archive)
    recorded = (packet / "archive.sha256").read_text(encoding="utf-8").split()[0]
    if actual != recorded:
        raise RuntimeError("archive checksum mismatch")
    if stat.S_IMODE(archive.stat().st_mode) != 0o444:
        raise RuntimeError("archive is not read-only (0444)")
    index = _json_object((packet / "packet-index.json").read_bytes(), "packet index")
    if index.get("archive") != archive.name or index.get("archive_sha256") != actual:
        raise RuntimeError("packet index does not match archive")
    if index.get("status") != "NO-GO" or index.get("archive_mode") != "0444":
        raise RuntimeError("packet index decision or mode is invalid")
    deletion_path = packet / "deletion-manifest.json"
    if index.get("deletion_manifest_sha256") != _sha256(deletion_path):
        raise RuntimeError("packet index deletion manifest hash mismatch")
    deletion = _json_object(deletion_path.read_bytes(), "deletion manifest")
    if (
        deletion.get("schema_version") != 1
        or deletion.get("decision") != "NO-GO"
        or deletion.get("approval_required") != {"separate_human": True, "two_person_confirmation": True}
        or deletion.get("candidates") != list(candidates)
        or deletion.get("protected_never_delete_in_m6") != list(protected)
    ):
        raise RuntimeError("deletion manifest is invalid")
    decision = _json_object((packet / "decision.json").read_bytes(), "decision")
    approval = index.get("approval")
    approval_fields = ("owner", "approver_one", "approver_two", "approved_at")
    if decision.get("status") != "NO-GO" or any(decision.get(field) is not None for field in approval_fields):
        raise RuntimeError("decision approval fields are invalid")
    if not isinstance(approval, dict) or any(approval.get(field) != decision.get(field) for field in approval_fields):
        raise RuntimeError("packet index approval fields are invalid")
    manifest_path = packet / "archive-manifest.json"
    manifest = _json_object(manifest_path.read_bytes(), "archive manifest")
    files = manifest.get("files")
    if manifest.get("schema_version") != 1 or not isinstance(files, dict):
        raise RuntimeError("archive manifest is invalid")
    with tarfile.open(archive) as tar:
        all_members = tar.getmembers()
        names = [member.name for member in all_members]
        if len(names) != len(set(names)):
            raise RuntimeError("archive contains duplicate members")
        for member in all_members:
            _validate_member_name(member.name)
            if not member.isfile():
                raise RuntimeError(f"archive contains non-regular member: {member.name}")
        members = {member.name: member for member in all_members}
        if set(members) != set(files) | {"archive-manifest.json"}:
            raise RuntimeError("archive contents do not match archive manifest")
        for name, expected_hash in files.items():
            stream = tar.extractfile(members[name])
            if stream is None or hashlib.sha256(stream.read()).hexdigest() != expected_hash:
                raise RuntimeError(f"archive manifest hash mismatch: {name}")
        sidecars = (
            "archive-manifest.json",
            "deletion-manifest.json",
            "decision.json",
            "coverage.json",
            "README.md",
            "baseline.txt",
            "sessions-journals-index.json",
        )
        for name in sidecars:
            stream = tar.extractfile(members[name])
            if stream is None or stream.read() != (packet / name).read_bytes():
                raise RuntimeError(f"packet sidecar differs from archive: {name}")
        allowlist_stream = tar.extractfile(members[ALLOWLIST_ARCHIVE_PATH])
        if allowlist_stream is None:
            raise RuntimeError("compatibility allowlist is missing from archive")
        allowlist_bytes = allowlist_stream.read()
        allowlist = _json_object(allowlist_bytes, "compatibility allowlist")
        validate_allowlist_payload(allowlist)
        allowlist_hash = hashlib.sha256(allowlist_bytes).hexdigest()
        if index.get("consumer_allowlist_sha256") != allowlist_hash:
            raise RuntimeError("packet index compatibility allowlist hash mismatch")
