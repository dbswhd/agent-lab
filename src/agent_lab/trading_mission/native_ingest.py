"""Delegate Trading Mission ingest to quant_pipeline native ingest (RiskEngine)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_NATIVE_ENV = "AGENTIC_USE_NATIVE_INGEST"
_SRC_ENV_KEYS = ("AGENTIC_QUANT_PIPELINE_SRC", "QUANT_PIPELINE_AGENTIC_SRC")
_DB_ENV_KEYS = ("AGENTIC_TRADING_DB", "CONTROL_PLANE_DB")


def use_native_ingest() -> bool:
    raw = (os.getenv(_NATIVE_ENV) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def resolve_quant_pipeline_src() -> Path | None:
    """Locate New project `src/` for quant_pipeline imports."""
    for key in _SRC_ENV_KEYS:
        raw = (os.getenv(key) or "").strip()
        if raw:
            path = Path(raw).expanduser().resolve()
            if (path / "quant_pipeline").is_dir():
                return path

    home = Path.home()
    candidates = (
        home / "Documents/New project/src",
        home / "Projects/quant-pipeline/src",
    )
    pipeline_root = (os.getenv("QUANT_PIPELINE_ROOT") or "").strip()
    if pipeline_root:
        root = Path(pipeline_root).expanduser().resolve()
        candidates = (
            root.parent / "New project/src",
            root / "src",
            *candidates,
        )

    for path in candidates:
        if (path / "quant_pipeline").is_dir():
            return path.resolve()
    return None


def _normalize_native_report(report: dict[str, Any]) -> dict[str, Any]:
    out = dict(report)
    out["ingest_backend"] = "native"
    raw = out.get("ingested") or []
    ids: list[str] = []
    details: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            pid = str(item.get("proposal_id") or "").strip()
            if pid:
                ids.append(pid)
                details.append(item)
    if ids and not all(isinstance(x, str) for x in raw):
        out["ingested"] = ids
    if details:
        out["ingested_details"] = details
    return out


def _import_native_ingest(src: Path):
    src_str = str(src.resolve())
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
    from quant_pipeline.agentic_trading.ingest import ingest_session_folder

    return ingest_session_folder


def _subprocess_env(src: Path, db_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ("PATH", "HOME", "VIRTUAL_ENV", "PYTHONUTF8"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    env["PYTHONPATH"] = str(src.resolve())
    db_text = str(db_path.resolve())
    env["AGENTIC_TRADING_DB"] = db_text
    env["CONTROL_PLANE_DB"] = db_text
    return env


def _run_native_subprocess(
    session_folder: Path,
    *,
    src: Path,
    db_path: Path,
    force: bool,
    dry_run: bool,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        "-m",
        "quant_pipeline.agentic_trading.ingest_cli",
        str(session_folder.resolve()),
        "--session",
    ]
    if force:
        cmd.append("--force")
    if dry_run:
        cmd.append("--dry-run")

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=_subprocess_env(src, db_path),
        timeout=120,
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    if not stdout:
        return {
            "ok": False,
            "skipped": False,
            "reason": f"native ingest_cli failed (exit {proc.returncode}): {(proc.stderr or '')[:500]}",
            "ingest_backend": "native",
            "ingested": [],
            "errors": [],
        }
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "skipped": False,
            "reason": "native ingest_cli returned invalid JSON",
            "ingest_backend": "native",
            "ingested": [],
            "errors": [{"index": "*", "error": stdout[:300]}],
        }
    if proc.returncode != 0 and report.get("ok") is not False:
        report["ok"] = False
    report.setdefault("db_path", str(db_path))
    return _normalize_native_report(report)


def native_ingest_session_folder(
    session_folder: Path,
    *,
    db_path: Path,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run quant_pipeline ingest_session_folder (import-first, subprocess fallback)."""
    src = resolve_quant_pipeline_src()
    if src is None:
        return {
            "ok": False,
            "skipped": False,
            "reason": "native ingest: quant_pipeline src not found (set AGENTIC_QUANT_PIPELINE_SRC)",
            "ingest_backend": "native",
            "ingested": [],
            "errors": [],
        }

    folder = session_folder.expanduser().resolve()
    db = db_path.expanduser().resolve()
    prev_db = {key: os.environ.get(key) for key in _DB_ENV_KEYS}

    try:
        for key in _DB_ENV_KEYS:
            os.environ[key] = str(db)
        ingest_session_folder = _import_native_ingest(src)
        report = ingest_session_folder(folder, force=force, dry_run=dry_run)
        report.setdefault("db_path", str(db))
        return _normalize_native_report(report)
    except ImportError:
        return _run_native_subprocess(
            folder,
            src=src,
            db_path=db,
            force=force,
            dry_run=dry_run,
        )
    finally:
        for key, value in prev_db.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
