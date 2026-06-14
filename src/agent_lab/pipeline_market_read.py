"""Read-only pipeline market tools — quote, freshness, portfolio, overlay (no orders)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from agent_lab.extensions.quant_runtime import load_quant_module
from agent_lab.extensions.quant_trading import extension_unavailable, optional_pipeline_root

_QUOTE_FIELD_CAP = 10
_FRESHNESS_ROW_CAP = 8


def _market_read():
    return load_quant_module("quant_pipeline.agentic_trading.market_read")


# Mock-first KR ETF quotes (v1 dev / no KIS keys).
_MOCK_QUOTES_KR: dict[str, dict[str, Any]] = {
    "069500": {
        "symbol": "069500",
        "name": "KODEX 200",
        "price": 35_120.0,
        "change_pct": 0.15,
        "bid": 35_115.0,
        "ask": 35_125.0,
        "currency": "KRW",
        "source": "mock",
    },
    "138230": {
        "symbol": "138230",
        "name": "KODEX 미국달러선물",
        "price": 12_450.0,
        "change_pct": -0.05,
        "bid": 12_445.0,
        "ask": 12_455.0,
        "currency": "KRW",
        "source": "mock",
    },
    "005930": {
        "symbol": "005930",
        "name": "삼성전자",
        "price": 72_300.0,
        "change_pct": 0.42,
        "bid": 72_200.0,
        "ask": 72_400.0,
        "currency": "KRW",
        "source": "mock",
    },
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _tail_jsonl(path: Path, limit: int = 3) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for raw in lines[-limit:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def resolve_freshness_python(pipeline: Path) -> str:
    """Pick interpreter for pipeline subprocesses (freshness, backtest)."""
    override = (os.getenv("AGENT_LAB_FRESHNESS_PYTHON") or "").strip()
    if override:
        return override
    override = (os.getenv("AGENT_LAB_PIPELINE_PYTHON") or "").strip()
    if override:
        return override
    venv_py = pipeline / ".venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


def _normalize_symbol(symbol: str, market: str) -> tuple[str, str]:
    code = re.sub(r"[^0-9A-Za-z]", "", str(symbol or "").strip().upper())
    mkt = str(market or "kr").strip().lower()
    if mkt not in {"kr", "us"}:
        mkt = "kr"
    return code, mkt


def _cap_fields(payload: dict[str, Any], *, max_fields: int = _QUOTE_FIELD_CAP) -> dict[str, Any]:
    keys = list(payload.keys())[:max_fields]
    return {k: payload[k] for k in keys}


def _quote_mode() -> str:
    raw = (os.getenv("AGENT_LAB_QUOTE_MODE") or "mock").strip().lower()
    if raw in {"mock", "kis", "pipeline"}:
        return raw
    return "mock"


def _quote_mock(symbol: str, market: str) -> dict[str, Any]:
    code, mkt = _normalize_symbol(symbol, market)
    if not code:
        return {"ok": False, "reason": "empty symbol", "symbol": symbol, "market": mkt}
    row = _MOCK_QUOTES_KR.get(code)
    if row is None:
        row = {
            "symbol": code,
            "name": code,
            "price": 10_000.0,
            "change_pct": 0.0,
            "bid": 9_990.0,
            "ask": 10_010.0,
            "currency": "KRW" if mkt == "kr" else "USD",
            "source": "mock_default",
        }
    payload = {"ok": True, "market": mkt, **row}
    return _cap_fields(payload)


def _quote_via_kis(pipeline: Path, symbol: str, market: str) -> dict[str, Any]:
    code, mkt = _normalize_symbol(symbol, market)
    if not code:
        return {"ok": False, "reason": "empty symbol", "symbol": symbol, "market": mkt}
    python = resolve_freshness_python(pipeline)
    script = (
        "import json,sys\n"
        "from brokers.kis_api_client import KISCompatClient\n"
        f"mode=(__import__('os').getenv('KIS_MODE') or 'mock').strip()\n"
        f"q=KISCompatClient(mode=mode).get_quote({code!r})\n"
        "print(json.dumps(q, ensure_ascii=False))\n"
    )
    try:
        proc = subprocess.run(
            [python, "-c", script],
            cwd=str(pipeline),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env={**os.environ, "PYTHONPATH": str(pipeline)},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": str(exc), "symbol": code, "market": mkt, "source": "kis"}
    if proc.returncode != 0:
        return {
            "ok": False,
            "reason": (proc.stderr or "kis quote failed").strip()[:300],
            "symbol": code,
            "market": mkt,
            "source": "kis",
        }
    try:
        raw = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"ok": False, "reason": "kis output not json", "symbol": code, "market": mkt}
    if not isinstance(raw, dict):
        return {"ok": False, "reason": "kis unexpected payload", "symbol": code, "market": mkt}
    price = raw.get("price") or raw.get("stck_prpr") or raw.get("last")
    payload = {
        "ok": True,
        "symbol": code,
        "market": mkt,
        "price": price,
        "change_pct": raw.get("change_pct") or raw.get("prdy_ctrt"),
        "bid": raw.get("bid") or raw.get("bidp"),
        "ask": raw.get("ask") or raw.get("askp"),
        "name": raw.get("name") or raw.get("hts_kor_isnm"),
        "currency": "KRW" if mkt == "kr" else "USD",
        "source": "kis",
    }
    return _cap_fields(payload)


def get_quote(
    symbol: str,
    market: str = "kr",
    *,
    pipeline: Path | None = None,
) -> dict[str, Any]:
    """Compact quote read (mock-first; optional KIS via AGENT_LAB_QUOTE_MODE=kis)."""
    mode = _quote_mode()
    if mode == "mock":
        return _quote_mock(symbol, market)
    root = pipeline or optional_pipeline_root()
    if root is None:
        return extension_unavailable(
            "quant_pipeline",
            "quote in kis/pipeline mode requires QUANT_PIPELINE_ROOT",
            extra={"symbol": symbol, "market": market},
        )
    if mode == "kis":
        return _quote_via_kis(root, symbol, market)
    return _quote_mock(symbol, market)


def run_data_freshness(pipeline: Path | None = None) -> dict[str, Any]:
    """Run quant_control_freshness.py and return structured freshness block."""
    root = pipeline or optional_pipeline_root()
    qm = _market_read()
    if root is not None and qm is not None:
        return qm.run_data_freshness(root)
    if root is None:
        return {
            "blocking": True,
            "ok": False,
            "message": "quant-pipeline extension not configured (QUANT_PIPELINE_ROOT)",
            "rows": [],
            "extension": "quant_pipeline",
        }
    script = root / "scripts" / "spec91" / "quant_control_freshness.py"
    if not script.is_file():
        return {
            "blocking": True,
            "ok": False,
            "message": "freshness script missing",
            "rows": [],
        }
    python = resolve_freshness_python(root)
    try:
        proc = subprocess.run(
            [python, str(script)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "blocking": True,
            "ok": False,
            "message": f"freshness failed: {exc}",
            "rows": [],
        }
    stdout = (proc.stdout or "").strip()
    if proc.returncode != 0 or not stdout:
        return {
            "blocking": True,
            "ok": False,
            "message": (proc.stderr or "freshness non-zero exit").strip()[:500],
            "rows": [],
        }
    try:
        payload = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError:
        return {
            "blocking": True,
            "ok": False,
            "message": "freshness output not json",
            "rows": [],
        }
    blocking = not bool(payload.get("ok"))
    rows = payload.get("rows") or []
    if isinstance(rows, list):
        rows = rows[:_FRESHNESS_ROW_CAP]
    else:
        rows = []
    return {
        "blocking": blocking,
        "ok": bool(payload.get("ok")),
        "message": str(payload.get("message") or ""),
        "rows": rows,
        "portfolios": (payload.get("portfolios") or [])[:5],
        "trade_allowed": not blocking,
    }


def get_data_freshness(*, pipeline: Path | None = None) -> dict[str, Any]:
    """MCP-friendly freshness summary."""
    root = pipeline or optional_pipeline_root()
    if root is None:
        return extension_unavailable(
            "quant_pipeline",
            "freshness requires QUANT_PIPELINE_ROOT",
        )
    block = run_data_freshness(root)
    return {"ok": True, "pipeline_root": str(root), "freshness": block}


def read_portfolio_snapshot(pipeline: Path | None = None) -> dict[str, Any]:
    """Mock-first portfolio JSON used by RiskEngine preflight."""
    root = pipeline or optional_pipeline_root()
    if root is not None:
        mock_path = root / "data" / "agentic_trading" / "mock_portfolio.json"
        mock = _read_json(mock_path)
        if mock:
            return mock
    return {
        "source": "mock_default",
        "cash": 1_000_000.0,
        "equity": 5_000_000.0,
        "positions": {},
    }


def get_portfolio_snapshot(*, pipeline: Path | None = None) -> dict[str, Any]:
    """Compact portfolio for MCP (cash, equity, positions only)."""
    root = pipeline or optional_pipeline_root()
    raw = read_portfolio_snapshot(root)
    positions = raw.get("positions") if isinstance(raw.get("positions"), dict) else {}
    payload: dict[str, Any] = {
        "ok": True,
        "source": str(raw.get("source") or "mock"),
        "cash": float(raw.get("cash") or 0),
        "equity": float(raw.get("equity") or 0),
        "positions": positions,
        "position_count": len(positions),
    }
    if root is not None:
        payload["pipeline_root"] = str(root)
    else:
        payload["extension"] = "quant_pipeline"
        payload["pipeline_root"] = None
    return payload


def read_overlay_signals(pipeline: Path | None = None) -> dict[str, Any]:
    root = pipeline or optional_pipeline_root()
    qm = _market_read()
    if root is not None and qm is not None:
        return qm.read_overlay_signals(root)
    if root is None:
        return {
            "kr_kospi_v1": {
                "position": "unknown",
                "action": "none",
                "flag": None,
                "recent_actions": [],
            }
        }
    state_path = root / "data" / "kr_kospi_v1" / "holdings_state.json"
    log_path = root / "logs" / "kr_kospi_v1" / "action_log.jsonl"
    flag_path = root / "logs" / "kr_kospi_v1" / "ACTION_REQUIRED.flag"
    state = _read_json(state_path) or {}
    recent = _tail_jsonl(log_path, limit=3)
    last = recent[-1] if recent else {}
    return {
        "kr_kospi_v1": {
            "position": state.get("position") or state.get("current_position") or "unknown",
            "action": last.get("action") or last.get("decision") or "none",
            "flag": flag_path.name if flag_path.is_file() else None,
            "recent_actions": recent,
        }
    }


def get_overlay_signals(*, pipeline: Path | None = None) -> dict[str, Any]:
    root = pipeline or optional_pipeline_root()
    if root is None:
        return extension_unavailable(
            "quant_pipeline",
            "overlay signals require QUANT_PIPELINE_ROOT",
        )
    qm = _market_read()
    if qm is not None:
        return qm.get_overlay_signals(pipeline=root)
    return {"ok": True, "pipeline_root": str(root), "overlay_signals": read_overlay_signals(root)}


def read_kill_switch(pipeline: Path | None = None) -> bool:
    root = pipeline or optional_pipeline_root()
    qm = _market_read()
    if root is not None and qm is not None:
        return qm.read_kill_switch(root)
    if root is None:
        return False
    flags = [
        root / "logs" / "kr_overlay" / "EMERGENCY_STOP",
        root / "logs" / "kr_kospi_v1" / "EMERGENCY_STOP",
        root / "data" / "EMERGENCY_STOP",
    ]
    return any(p.is_file() for p in flags)
