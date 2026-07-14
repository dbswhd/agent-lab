from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "m6_final_retire_packet.py"
ALLOWLIST = SCRIPT.parents[1] / "docs/redesign-2026-07/m6-compatibility-consumer-allowlist-2026-07-14.json"


def _seed_packet_inputs(root: Path, *, tasks: range = range(1, 11)) -> None:
    evidence = root / ".omo/evidence/wave-b-m6-retire"
    evidence.mkdir(parents=True)
    for task in tasks:
        (evidence / f"task-{task}.json").write_text("{}\n", encoding="utf-8")
    (evidence / "live-clean-restart.json").write_text("{}\n", encoding="utf-8")
    allowlist = root / "docs/redesign-2026-07/m6-compatibility-consumer-allowlist-2026-07-14.json"
    allowlist.parent.mkdir(parents=True)
    allowlist.write_bytes(ALLOWLIST.read_bytes())


def test_deletion_runner_without_approval_is_no_go_and_does_not_mutate(tmp_path: Path) -> None:
    manifest = tmp_path / "deletion-manifest.json"
    candidate = tmp_path / "candidate.txt"
    candidate.write_text("retain me\n", encoding="utf-8")
    manifest.write_text(
        json.dumps({"schema_version": 1, "candidates": ["candidate.txt"]}),
        encoding="utf-8",
    )
    before = hashlib.sha256(candidate.read_bytes()).hexdigest()

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--delete", "--root", str(tmp_path), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "NO-GO" in result.stdout
    assert candidate.exists()
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == before


def test_build_and_verify_packet_is_redacted_and_checksum_backed(tmp_path: Path) -> None:
    _seed_packet_inputs(tmp_path)
    (tmp_path / ".omo/evidence/wave-b-m6-retire/task-1.json").write_text(
        '{"path":"/Users/alice/private","status":"PASS"}\n', encoding="utf-8"
    )
    (tmp_path / "sessions/demo").mkdir(parents=True)
    (tmp_path / "sessions/demo/chat.jsonl").write_text("private prompt\n", encoding="utf-8")
    packet = tmp_path / "packet"

    built = subprocess.run(
        [sys.executable, str(SCRIPT), "--build", "--root", str(tmp_path), "--output", str(packet)],
        capture_output=True, text=True, check=False,
    )
    verified = subprocess.run(
        [sys.executable, str(SCRIPT), "--verify", "--root", str(tmp_path), "--output", str(packet)],
        capture_output=True, text=True, check=False,
    )

    assert built.returncode == 0
    assert verified.returncode == 0
    assert json.loads((packet / "decision.json").read_text(encoding="utf-8"))["status"] == "NO-GO"
    assert (packet / "deletion-manifest.json").is_file()
    assert (packet / "m6-final-retire.tar.gz").stat().st_mode & 0o777 == 0o444
    assert all(path.stat().st_mode & 0o777 == 0o444 for path in packet.iterdir() if path.is_file())
    with tarfile.open(packet / "m6-final-retire.tar.gz") as archive:
        names = archive.getnames()
        assert "sessions-journals-index.json" in names
        assert all("chat.jsonl" not in name for name in names)
        task = archive.extractfile("evidence/task-1.json")
        assert task is not None
        assert b"/Users/" not in task.read()


def test_sigterm_during_build_cleans_partial_output_and_allows_retry(tmp_path: Path) -> None:
    _seed_packet_inputs(tmp_path)
    packet = tmp_path / "packet"
    env = {**os.environ, "M6_PACKET_BUILD_DELAY_SECONDS": "2"}
    process = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--build", "--root", str(tmp_path), "--output", str(packet)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    partials: list[Path] = []
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        partials = list(tmp_path.glob(".packet.partial-*"))
        if partials:
            break
        time.sleep(0.01)
    assert partials
    process.terminate()
    process.communicate(timeout=5)

    assert not packet.exists()
    assert not list(tmp_path.glob(".packet.partial-*"))
    retry = subprocess.run(
        [sys.executable, str(SCRIPT), "--build", "--root", str(tmp_path), "--output", str(packet)],
        capture_output=True, text=True, check=False,
    )
    assert retry.returncode == 0


def test_build_rejects_missing_required_evidence(tmp_path: Path) -> None:
    _seed_packet_inputs(tmp_path, tasks=range(1, 2))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--build", "--root", str(tmp_path), "--output", str(tmp_path / "packet")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "required evidence" in (result.stderr + result.stdout).lower()


def test_delete_non_object_approval_is_controlled_no_go(tmp_path: Path) -> None:
    manifest = tmp_path / "deletion-manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    approval = tmp_path / "approval.json"
    approval.write_text("[]\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--delete", "--root", str(tmp_path), "--manifest", str(manifest), "--approval", str(approval)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "NO-GO" in result.stdout


def test_verify_rejects_extra_tar_symlink(tmp_path: Path) -> None:
    _seed_packet_inputs(tmp_path)
    packet = tmp_path / "packet"
    built = subprocess.run(
        [sys.executable, str(SCRIPT), "--build", "--root", str(tmp_path), "--output", str(packet)],
        capture_output=True, text=True, check=False,
    )
    assert built.returncode == 0
    archive = packet / "m6-final-retire.tar.gz"
    malicious = tmp_path / "malicious.tar.gz"
    with tarfile.open(archive, "r:gz") as source, tarfile.open(malicious, "w:gz") as target:
        for member in source.getmembers():
            payload = source.extractfile(member)
            target.addfile(member, payload)
        link = tarfile.TarInfo("extra-link")
        link.type = tarfile.SYMTYPE
        link.linkname = "README.md"
        target.addfile(link)
    malicious.replace(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (packet / "archive.sha256").chmod(0o644)
    (packet / "archive.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    index = json.loads((packet / "packet-index.json").read_text(encoding="utf-8"))
    index["archive_sha256"] = digest
    (packet / "packet-index.json").chmod(0o644)
    (packet / "packet-index.json").write_text(json.dumps(index), encoding="utf-8")
    verified = subprocess.run(
        [sys.executable, str(SCRIPT), "--verify", "--root", str(tmp_path), "--output", str(packet)],
        capture_output=True, text=True, check=False,
    )
    assert verified.returncode != 0


def test_verify_rejects_tampered_allowlist_hash(tmp_path: Path) -> None:
    _seed_packet_inputs(tmp_path)
    packet = tmp_path / "packet"
    built = subprocess.run(
        [sys.executable, str(SCRIPT), "--build", "--root", str(tmp_path), "--output", str(packet)],
        capture_output=True, text=True, check=False,
    )
    assert built.returncode == 0
    index = json.loads((packet / "packet-index.json").read_text(encoding="utf-8"))
    index["consumer_allowlist_sha256"] = "tampered"
    (packet / "packet-index.json").chmod(0o644)
    (packet / "packet-index.json").write_text(json.dumps(index), encoding="utf-8")
    verified = subprocess.run(
        [sys.executable, str(SCRIPT), "--verify", "--root", str(tmp_path), "--output", str(packet)],
        capture_output=True, text=True, check=False,
    )
    assert verified.returncode != 0


def test_verify_rejects_tampered_packet_index(tmp_path: Path) -> None:
    _seed_packet_inputs(tmp_path)
    packet = tmp_path / "packet"
    built = subprocess.run(
        [sys.executable, str(SCRIPT), "--build", "--root", str(tmp_path), "--output", str(packet)],
        capture_output=True, text=True, check=False,
    )
    assert built.returncode == 0
    index = json.loads((packet / "packet-index.json").read_text(encoding="utf-8"))
    index["archive_sha256"] = "tampered"
    (packet / "packet-index.json").chmod(0o644)
    (packet / "packet-index.json").write_text(json.dumps(index), encoding="utf-8")

    verified = subprocess.run(
        [sys.executable, str(SCRIPT), "--verify", "--root", str(tmp_path), "--output", str(packet)],
        capture_output=True, text=True, check=False,
    )

    assert verified.returncode != 0
