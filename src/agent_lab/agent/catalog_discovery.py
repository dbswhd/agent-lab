"""Provider model discovery for catalog generation (Codex OAuth backend)."""

from __future__ import annotations

from agent_lab.time_utils import utc_now_iso_seconds as _utc_now_iso
import base64
import json
import re
import subprocess
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

CODEX_BACKEND_BASE = "https://chatgpt.com/backend-api"
CODEX_MODEL_PATHS = ("/codex/models", "/models")
JWT_CLAIM_PATH = "https://api.openai.com/auth"
_EFFORT_ORDER = ("minimal", "low", "medium", "high", "xhigh", "max")



def extract_codex_account_id(access_token: str) -> str | None:
    try:
        parts = access_token.split(".")
        if len(parts) != 3:
            return None
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    auth = payload.get(JWT_CLAIM_PATH)
    if isinstance(auth, dict):
        account_id = auth.get("chatgpt_account_id")
        if isinstance(account_id, str) and account_id.strip():
            return account_id.strip()
    return None


def load_codex_oauth_credentials() -> tuple[str, str | None] | None:
    """Return ``(access_token, account_id)`` from ``~/.codex/auth.json`` when present."""
    from agent_lab.codex.oauth import live_auth_path

    path = live_auth_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        return None
    access = tokens.get("access_token") or tokens.get("access")
    if not isinstance(access, str) or not access.strip():
        return None
    account_id = tokens.get("account_id")
    if isinstance(account_id, str) and account_id.strip():
        return access.strip(), account_id.strip()
    return access.strip(), extract_codex_account_id(access.strip())


def parse_version_from_slug(slug: str) -> list[int]:
    """Best-effort version tuple for picker ordering (``gpt-5.5`` → ``[5, 5, 0]``)."""
    raw = slug.strip().lower()
    match = re.match(r"^gpt-(\d+)\.(\d+)(?:-|$)", raw)
    if match:
        return [int(match.group(1)), int(match.group(2)), 0]
    match = re.match(r"^gpt-(\d+)$", raw)
    if match:
        return [int(match.group(1)), 0, 0]
    match = re.match(r"^o(\d+)(?:-mini|-|$)", raw)
    if match:
        return [int(match.group(1)), 0, 0]
    return [0]


def _label_from_slug(slug: str, display_name: str | None = None) -> str:
    if display_name and display_name.strip():
        return display_name.strip()
    parts = slug.strip().split("-")
    if parts and parts[0].lower() == "gpt":
        if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
            return f"GPT-{parts[1]}.{parts[2]}"
        if len(parts) >= 2 and parts[1].isdigit():
            return f"GPT-{parts[1]}"
    return slug.strip()


def _normalize_efforts(raw_levels: Any) -> list[str]:
    if not isinstance(raw_levels, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_levels:
        effort: str | None = None
        if isinstance(item, str):
            effort = item.strip().lower()
        elif isinstance(item, dict):
            val = item.get("effort")
            if isinstance(val, str):
                effort = val.strip().lower()
        if not effort or effort == "none" or effort in seen:
            continue
        seen.add(effort)
        out.append(effort)
    out.sort(key=lambda level: _EFFORT_ORDER.index(level) if level in _EFFORT_ORDER else 99)
    return out


def _normalize_codex_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    slug = entry.get("slug") or entry.get("id")
    if not isinstance(slug, str) or not slug.strip():
        return None
    slug = slug.strip()
    supported = entry.get("supported_in_api")
    if supported is False:
        return None
    if entry.get("visibility") == "hide":
        return None
    display = entry.get("display_name")
    display_name = display.strip() if isinstance(display, str) else None
    row: dict[str, Any] = {
        "id": slug,
        "label": _label_from_slug(slug, display_name),
        "version": parse_version_from_slug(slug),
        "source": "discovered",
    }
    efforts = _normalize_efforts(entry.get("supported_reasoning_levels"))
    if efforts:
        row["efforts"] = efforts
    return row


def _parse_codex_models_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    entries = payload.get("models")
    if not isinstance(entries, list):
        entries = payload.get("data")
    if not isinstance(entries, list):
        return []
    out: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        row = _normalize_codex_entry(item)
        if row is not None:
            out.append(row)
    return out


def resolve_codex_client_version(*, timeout_sec: float = 6.0) -> str | None:
    """Probe the installed ``codex`` CLI version.

    The ChatGPT backend rejects ``/codex/models`` without a ``client_version``
    query param (``400 missing 'client_version'``), so discovery must report
    the same version the room's Codex CLI actually runs.
    """
    from agent_lab.codex.cli import _codex_env, resolve_codex_bin

    bin_path = resolve_codex_bin()
    if not bin_path:
        return None
    try:
        result = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=_codex_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (result.stdout or result.stderr or "").strip()
    match = re.search(r"(\d+\.\d+\.\d+)", output)
    return match.group(1) if match else None


def fetch_codex_catalog_models(
    *,
    access_token: str,
    account_id: str | None = None,
    timeout_sec: float = 20.0,
    base_url: str = CODEX_BACKEND_BASE,
    client_version: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch Codex models from ChatGPT backend (GJC-compatible paths)."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "OpenAI-Beta": "responses=experimental",
        "originator": "pi",
    }
    if account_id:
        headers["chatgpt-account-id"] = account_id
    version = client_version or resolve_codex_client_version()
    query = f"?{urlencode({'client_version': version})}" if version else ""

    saw_ok = False
    for path in CODEX_MODEL_PATHS:
        url = f"{base_url.rstrip('/')}{path}{query}"
        req = urllib.request.Request(url, method="GET", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError:
            continue
        except OSError:
            continue
        saw_ok = True
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            continue
        models = _parse_codex_models_payload(payload)
        if models:
            discovered_at = _utc_now_iso()
            for row in models:
                row["discovered_at"] = discovered_at
            return models, None
    if saw_ok:
        return [], "Codex backend returned no usable models"
    return [], "Codex model discovery unreachable (OAuth backend)"


def discover_codex_models(*, timeout_sec: float = 20.0) -> tuple[list[dict[str, Any]], str | None]:
    creds = load_codex_oauth_credentials()
    if creds is None:
        return [], "Codex OAuth credentials not found (~/.codex/auth.json)"
    access_token, account_id = creds
    return fetch_codex_catalog_models(
        access_token=access_token,
        account_id=account_id,
        timeout_sec=timeout_sec,
    )
