"""User-managed API credentials with primary → fallback failover."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

if sys.version_info >= (3, 11):
    import tomllib
else:
    tomllib = None  # type: ignore[assignment,misc]

ProviderId = Literal["cursor", "claude", "codex"]

PROVIDERS: tuple[ProviderId, ...] = ("cursor", "claude", "codex")

# Room Claude/Codex use CLI OAuth only — API keys in Settings are ignored.
OAUTH_ONLY_PROVIDERS: frozenset[ProviderId] = frozenset({"claude", "codex"})

_PROVIDER_ENV: dict[ProviderId, str] = {
    "cursor": "CURSOR_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "codex": "OPENAI_API_KEY",
}

_PROVIDER_FALLBACK_ENV: dict[ProviderId, str] = {
    "cursor": "CURSOR_API_KEY_FALLBACK",
    "claude": "ANTHROPIC_API_KEY_FALLBACK",
    "codex": "OPENAI_API_KEY_FALLBACK",
}

_PROVIDER_LABELS: dict[ProviderId, str] = {
    "cursor": "Cursor",
    "claude": "Claude",
    "codex": "Codex",
}

_CREDENTIAL_FAILURE_PATTERNS = (
    r"\b401\b",
    r"\b403\b",
    r"auth(?:entication)?",
    r"invalid api key",
    r"api key not set",
    r"credit balance",
    r"session limit",
    r"permission denied",
    r"unauthorized",
    r"forbidden",
    r"not authenticated",
)

T = TypeVar("T")


def credentials_path() -> Path:
    from agent_lab.app_config import config_dir

    return config_dir() / "credentials.toml"


def _empty_store() -> dict[str, Any]:
    return {pid: {"primary": "", "fallback": "", "primary_label": "", "fallback_label": ""} for pid in PROVIDERS}


def sanitize_oauth_provider_credentials(data: dict[str, Any]) -> dict[str, Any]:
    """Strip API keys for OAuth-only Room agents (Claude, Codex)."""
    for pid in OAUTH_ONLY_PROVIDERS:
        slot = data.get(pid)
        if not isinstance(slot, dict):
            continue
        slot["primary"] = ""
        slot["fallback"] = ""
    return data


def load_credentials(*, create_default: bool = False) -> dict[str, Any]:
    path = credentials_path()
    if not path.is_file():
        if create_default:
            save_credentials(_empty_store())
        return _empty_store()
    if tomllib is None:
        return _empty_store()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty_store()
    out = _empty_store()
    if not isinstance(raw, dict):
        return out
    for pid in PROVIDERS:
        block = raw.get(pid)
        if not isinstance(block, dict):
            continue
        slot = out[pid]
        for key in ("primary", "fallback", "primary_label", "fallback_label"):
            val = block.get(key)
            if val is not None:
                slot[key] = str(val).strip()
    cleaned = sanitize_oauth_provider_credentials(out)
    for pid in OAUTH_ONLY_PROVIDERS:
        block = raw.get(pid) if isinstance(raw.get(pid), dict) else {}
        if str(block.get("primary") or "").strip() or str(block.get("fallback") or "").strip():
            save_credentials(cleaned)
            break
    return cleaned


def save_credentials(data: dict[str, Any]) -> Path:
    data = sanitize_oauth_provider_credentials(data)
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Agent Lab API credentials — managed from Settings or edited manually.",
        "# Primary is tried first; fallback is used when primary auth fails.",
        "",
    ]
    for pid in PROVIDERS:
        block = data.get(pid) if isinstance(data.get(pid), dict) else {}
        lines.append(f"[{pid}]")
        primary = str(block.get("primary") or "").strip()
        fallback = str(block.get("fallback") or "").strip()
        primary_label = str(block.get("primary_label") or "").strip()
        fallback_label = str(block.get("fallback_label") or "").strip()
        lines.append(f'primary = "{_escape_toml(primary)}"')
        lines.append(f'fallback = "{_escape_toml(fallback)}"')
        if primary_label:
            lines.append(f'primary_label = "{_escape_toml(primary_label)}"')
        if fallback_label:
            lines.append(f'fallback_label = "{_escape_toml(fallback_label)}"')
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    _sync_primary_env_from_store(data)
    return path


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _sync_primary_env_from_store(data: dict[str, Any]) -> None:
    """Mirror primary keys into process env (and ~/.agent-lab/.env) for legacy callers."""
    for pid in PROVIDERS:
        block = data.get(pid) if isinstance(data.get(pid), dict) else {}
        primary = str(block.get("primary") or "").strip()
        env_name = _PROVIDER_ENV[pid]
        if primary:
            os.environ[env_name] = primary
        elif env_name in os.environ and not os.getenv(env_name, "").strip():
            os.environ.pop(env_name, None)
    _sync_dotenv_primaries(data)


def _sync_dotenv_primaries(data: dict[str, Any]) -> None:
    from agent_lab.app_config import config_dir

    dotenv_path = config_dir() / ".env"
    lines: list[str] = []
    if dotenv_path.is_file():
        lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    managed = {_PROVIDER_ENV[pid] for pid in PROVIDERS}
    kept = [ln for ln in lines if not any(ln.strip().startswith(f"{k}=") for k in managed)]
    while kept and not kept[-1].strip():
        kept.pop()
    for pid in PROVIDERS:
        block = data.get(pid) if isinstance(data.get(pid), dict) else {}
        primary = str(block.get("primary") or "").strip()
        if primary:
            kept.append(f"{_PROVIDER_ENV[pid]}={primary}")
    dotenv_path.parent.mkdir(parents=True, exist_ok=True)
    dotenv_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def apply_credentials_to_env() -> None:
    """Load credentials.toml and apply primary keys to os.environ."""
    data = load_credentials(create_default=False)
    _sync_primary_env_from_store(data)


def mask_secret(value: str) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    if len(text) <= 8:
        return "••••"
    return f"{'•' * max(4, len(text) - 4)}{text[-4:]}"


def public_credentials_payload() -> dict[str, Any]:
    data = load_credentials(create_default=False)
    agents: list[dict[str, Any]] = []
    for pid in PROVIDERS:
        block = data[pid]
        primary = str(block.get("primary") or "").strip()
        fallback = str(block.get("fallback") or "").strip()
        env_primary = (os.getenv(_PROVIDER_ENV[pid]) or "").strip()
        env_fallback = (os.getenv(_PROVIDER_FALLBACK_ENV[pid]) or "").strip()
        oauth_only = pid in OAUTH_ONLY_PROVIDERS
        agents.append(
            {
                "id": pid,
                "label": _PROVIDER_LABELS[pid],
                "env_primary": _PROVIDER_ENV[pid],
                "env_fallback": _PROVIDER_FALLBACK_ENV[pid],
                "primary_label": str(block.get("primary_label") or "").strip() or "메인",
                "fallback_label": str(block.get("fallback_label") or "").strip() or "서브",
                "oauth_only": oauth_only,
                "has_primary": False if oauth_only else bool(primary or env_primary),
                "has_fallback": False if oauth_only else bool(fallback or env_fallback),
                "primary_masked": None if oauth_only else mask_secret(primary or env_primary),
                "fallback_masked": None if oauth_only else mask_secret(fallback or env_fallback),
                "stored_primary": False if oauth_only else bool(primary),
                "stored_fallback": False if oauth_only else bool(fallback),
            }
        )
    return {
        "ok": True,
        "path": str(credentials_path()),
        "agents": agents,
    }


def provider_has_credentials(provider: ProviderId) -> bool:
    return bool(get_credential_chain(provider))


def get_credential_chain(provider: ProviderId) -> list[tuple[str, str]]:
    """Ordered (label, secret) pairs: store primary → env primary → store fallback → env fallback."""
    if provider in OAUTH_ONLY_PROVIDERS:
        return []
    data = load_credentials(create_default=False)
    block = data.get(provider) if isinstance(data.get(provider), dict) else {}
    store_primary = str(block.get("primary") or "").strip()
    store_fallback = str(block.get("fallback") or "").strip()
    env_primary = (os.getenv(_PROVIDER_ENV[provider]) or "").strip()
    env_fallback = (os.getenv(_PROVIDER_FALLBACK_ENV[provider]) or "").strip()
    primary_label = str(block.get("primary_label") or "").strip() or "메인"
    fallback_label = str(block.get("fallback_label") or "").strip() or "서브"

    chain: list[tuple[str, str]] = []
    for label, value in (
        (primary_label, store_primary),
        ("env", env_primary),
        (fallback_label, store_fallback),
        ("env-fallback", env_fallback),
    ):
        if not value:
            continue
        if chain and chain[-1][1] == value:
            continue
        chain.append((label, value))
    return chain


def is_credential_failure(exc_or_text: object) -> bool:
    text = str(exc_or_text or "").strip().lower()
    if not text:
        return False
    return any(re.search(pat, text) for pat in _CREDENTIAL_FAILURE_PATTERNS)


def call_with_credential_fallback(
    provider: ProviderId,
    fn: Callable[[str | None], T],
    *,
    allow_oauth_without_key: bool = False,
) -> T:
    """Try primary API key, then fallback on credential/auth errors."""
    chain = get_credential_chain(provider)
    if not chain:
        if allow_oauth_without_key:
            return fn(None)
        env_name = _PROVIDER_ENV[provider]
        raise RuntimeError(f"{_PROVIDER_LABELS[provider]} API key not set ({env_name})")

    last_exc: BaseException | None = None
    for index, (label, key) in enumerate(chain):
        try:
            return fn(key)
        except Exception as exc:
            last_exc = exc
            is_last = index >= len(chain) - 1
            if is_credential_failure(exc) and not is_last:
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{_PROVIDER_LABELS[provider]} credential chain failed")


def patch_from_request(body: dict[str, Any]) -> dict[str, Any]:
    current = load_credentials(create_default=False)
    for pid in PROVIDERS:
        incoming = body.get(pid)
        if not isinstance(incoming, dict):
            continue
        slot = current[pid]
        for key in ("primary", "fallback", "primary_label", "fallback_label"):
            if key not in incoming:
                continue
            raw = incoming.get(key)
            if raw is None:
                slot[key] = ""
            else:
                slot[key] = str(raw).strip()
    return sanitize_oauth_provider_credentials(current)
