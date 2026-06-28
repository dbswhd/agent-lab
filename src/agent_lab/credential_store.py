"""User-managed API credentials with primary → fallback failover."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar, cast

if sys.version_info >= (3, 11):
    import tomllib
else:
    tomllib = None  # type: ignore[assignment,misc]

from agent_lab import provider_registry as _provider_registry

ProviderId = Literal["cursor", "claude", "codex"]

PROVIDERS: tuple[ProviderId, ...] = ("cursor", "claude", "codex")


def _derive_oauth_only() -> frozenset[ProviderId]:
    """Legacy typed providers needing no in-turn secret (supported auth ⊆ {oauth, cli}).

    Derived from the provider_registry single source of truth so this set and
    the /login picker never drift. Resolves to {"claude", "codex"} today
    (CLI OAuth only — API keys in Settings are ignored). Scoped to PROVIDERS:
    kimi/local use the accounts.toml chain, not this credentials.toml gate.
    """
    secretless = frozenset({"oauth", "cli"})
    return frozenset(
        cast(ProviderId, pid)
        for pid in PROVIDERS
        if _provider_registry.supported_auth(pid) and _provider_registry.supported_auth(pid) <= secretless
    )


# Room Claude/Codex use CLI OAuth only — API keys in Settings are ignored.
OAUTH_ONLY_PROVIDERS: frozenset[ProviderId] = _derive_oauth_only()

_PROVIDER_ENV: dict[str, str] = {
    "cursor": "CURSOR_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "codex": "OPENAI_API_KEY",
}
_PROVIDER_FALLBACK_ENV: dict[str, str] = {
    "cursor": "CURSOR_API_KEY_FALLBACK",
    "claude": "ANTHROPIC_API_KEY_FALLBACK",
    "codex": "OPENAI_API_KEY_FALLBACK",
}
_PROVIDER_LABELS: dict[str, str] = {
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
    r"usage limit",
    r"rate limit",
    r"\bquota\b",
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


def clear_provider_api_credentials(provider: str) -> bool:
    """Clear credentials.toml primary/fallback for a typed provider."""
    pid = provider.strip().lower()
    if pid not in PROVIDERS:
        return False
    data = load_credentials(create_default=False)
    block = data.get(pid) if isinstance(data.get(pid), dict) else {}
    had = bool(str(block.get("primary") or "").strip() or str(block.get("fallback") or "").strip())
    if not had:
        return False
    block = dict(block)
    block["primary"] = ""
    block["fallback"] = ""
    data[pid] = block
    save_credentials(data)
    return True


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


# --- Dynamic resilient room: additive multi-account chain (AGENT_LAB_DYNAMIC_ROOM) ---
# Accounts live in a sibling accounts.toml so the existing credentials.toml
# Settings save/load path stays byte-stable (OFF-parity). get_account_chain
# composes accounts[] (priority-sorted, cooldown-filtered) then the legacy chain.


def accounts_path() -> Path:
    from agent_lab.app_config import config_dir

    return config_dir() / "accounts.toml"


def _account_cooled(account: dict[str, Any], *, now: float | None = None) -> bool:
    raw = account.get("cooldown_until")
    if not isinstance(raw, (int, float, str)):
        return False
    try:
        until = float(raw)
    except (TypeError, ValueError):
        return False
    import time as _time

    return until > (now if now is not None else _time.time())


def _sorted_accounts(accounts: list[Any]) -> list[dict[str, Any]]:
    valid = [a for a in accounts if isinstance(a, dict)]

    def _key(a: dict[str, Any]) -> float:
        pr = a.get("priority")
        return float(pr) if isinstance(pr, (int, float)) else 1_000_000.0

    return sorted(valid, key=_key)


def _read_accounts_store() -> dict[str, list[dict[str, Any]]]:
    path = accounts_path()
    if not path.is_file() or tomllib is None:
        return {}
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(raw, dict):
        return out
    for pid, block in raw.items():
        if isinstance(block, dict) and isinstance(block.get("accounts"), list):
            out[pid] = [a for a in block["accounts"] if isinstance(a, dict)]
    return out


def get_provider_accounts(provider: str) -> list[dict[str, Any]]:
    return _read_accounts_store().get(provider, [])


def set_provider_accounts(provider: str, accounts: list[dict[str, Any]]) -> Path:
    """Persist accounts[] for one provider into accounts.toml, preserving others."""
    store = _read_accounts_store()
    store[provider] = [a for a in accounts if isinstance(a, dict)]
    lines = [
        "# Agent Lab multi-account chains — managed via /accounts or edited manually.",
        "# Additive to credentials.toml; primary/fallback there remain the legacy chain.",
        "",
    ]
    for pid in sorted(store):
        rows = store[pid]
        if not rows:
            continue
        for acct in rows:
            label = _escape_toml(str(acct.get("label") or "").strip())
            secret = _escape_toml(str(acct.get("secret_or_profile_ref") or acct.get("secret") or "").strip())
            priority = acct.get("priority")
            priority_val = int(priority) if isinstance(priority, (int, float)) else 1000
            cooldown = acct.get("cooldown_until")
            cooldown_val = float(cooldown) if isinstance(cooldown, (int, float)) else 0.0
            lines.append(f"[[{pid}.accounts]]")
            lines.append(f'label = "{label}"')
            lines.append(f'secret_or_profile_ref = "{secret}"')
            lines.append(f"priority = {priority_val}")
            lines.append(f"cooldown_until = {cooldown_val}")
            lines.append("")
    path = accounts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def get_account_chain(provider: str, *, now: float | None = None) -> list[tuple[str, str]]:
    """Ordered (label, secret) for a provider.

    accounts[] (priority asc, cooldown-filtered, non-empty secret) first, then the
    legacy credentials.toml chain for the existing typed providers. For oauth/cli
    providers the accounts[] entries hold profile refs (not secrets) and are excluded
    from this secret chain, mirroring get_credential_chain() == [] for OAUTH_ONLY.
    """
    from agent_lab import provider_registry as _pr

    if _pr.is_registered(provider):
        rotates = _pr.supports_inturn_key_rotation(provider)
    else:
        rotates = provider not in OAUTH_ONLY_PROVIDERS

    chain: list[tuple[str, str]] = []
    if rotates:
        for acct in _sorted_accounts(get_provider_accounts(provider)):
            secret = str(acct.get("secret_or_profile_ref") or acct.get("secret") or "").strip()
            label = str(acct.get("label") or "").strip() or "account"
            if not secret or _account_cooled(acct, now=now):
                continue
            if chain and chain[-1][1] == secret:
                continue
            chain.append((label, secret))

    if provider in PROVIDERS:
        for entry in get_credential_chain(provider):  # type: ignore[arg-type]
            if chain and chain[-1][1] == entry[1]:
                continue
            chain.append(entry)
    return chain
