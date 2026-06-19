"""Provider catalog for the dynamic resilient room (AGENT_LAB_DYNAMIC_ROOM).

Single source of truth for which agent providers exist and how their
credentials/usage behave. Additive: this module does not change the existing
``credential_store`` typed providers or the default ["cursor","codex","claude"]
room composition. It only adds metadata the dynamic roster/usage layers consult.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AuthKind = Literal["api", "oauth", "cli", "local", "peer"]
FallbackClass = Literal["primary", "spare", "local"]
AccountMode = Literal["ambient", "profile_slots", "api_chain"]


@dataclass(frozen=True)
class ProviderSpec:
    """Static metadata for one agent provider."""

    id: str
    label: str
    auth_kind: AuthKind
    usage_exposing: bool
    fallback_class: FallbackClass
    always_available: bool = False
    cooldown_exempt: bool = False
    # Auth methods this provider supports. Single source of truth for the
    # /login picker; empty means "derive {auth_kind}" via supported_auth().
    supported_auth: frozenset[AuthKind] = frozenset()
    account_mode: AccountMode = "api_chain"
    login_argv: tuple[str, ...] = ()
    logout_argv: tuple[str, ...] = ()
    status_argv: tuple[str, ...] = ()
    browser_hosts: tuple[str, ...] = ()


# Default catalog. cursor/claude/codex mirror the existing room agents; kimi and
# local are the new spare/floor providers from the approved plan.
_REGISTRY: dict[str, ProviderSpec] = {
    "cursor": ProviderSpec(
        "cursor",
        "Cursor",
        "api",
        True,
        "primary",
        # cursor-agent CLI supports both CURSOR_API_KEY and `cursor-agent login`
        # (browser OAuth). auth_kind stays "api" (default/primary path).
        supported_auth=frozenset({"api", "oauth"}),
        account_mode="ambient",
        login_argv=("cursor-agent", "login"),
        logout_argv=("cursor-agent", "logout"),
        status_argv=("cursor-agent", "status"),
        browser_hosts=("cursor.com", "www.cursor.com", "auth.cursor.com"),
    ),
    "claude": ProviderSpec(
        "claude",
        "Claude",
        "oauth",
        False,
        "primary",
        supported_auth=frozenset({"oauth"}),
        account_mode="ambient",
        login_argv=("claude", "auth", "login"),
        logout_argv=("claude", "auth", "logout"),
        status_argv=("claude", "auth", "status"),
        browser_hosts=("claude.ai", "console.anthropic.com", "auth.anthropic.com"),
    ),
    "codex": ProviderSpec(
        "codex",
        "Codex",
        "oauth",
        False,
        "primary",
        supported_auth=frozenset({"oauth"}),
        account_mode="profile_slots",
        login_argv=("codex", "login"),
        logout_argv=("codex", "logout"),
        status_argv=("codex", "login", "status"),
        browser_hosts=("auth.openai.com", "chatgpt.com", "openai.com"),
    ),
    "kimi": ProviderSpec(
        "kimi",
        "KIMI",
        "api",
        True,
        "spare",
        supported_auth=frozenset({"api"}),
    ),
    "kimi_work": ProviderSpec(
        "kimi_work",
        "Kimi Work",
        "peer",
        True,
        "spare",
        supported_auth=frozenset({"peer"}),
        account_mode="ambient",
    ),
    "local": ProviderSpec(
        "local",
        "Local",
        "local",
        False,
        "local",
        always_available=True,
        cooldown_exempt=True,
        supported_auth=frozenset({"local"}),
    ),
}

# Default room composition stays byte-stable with the pre-dynamic behavior.
DEFAULT_ROSTER: tuple[str, ...] = ("cursor", "codex", "claude")
# Ordered substitution pool consulted when a default seat is unavailable.
DEFAULT_SUBSTITUTION_PRIORITY: tuple[str, ...] = ("kimi_work", "kimi", "local")


def all_providers() -> list[ProviderSpec]:
    return list(_REGISTRY.values())


def provider_ids() -> list[str]:
    return list(_REGISTRY.keys())


def get_provider(pid: str) -> ProviderSpec | None:
    return _REGISTRY.get(pid)


def is_registered(pid: str) -> bool:
    return pid in _REGISTRY


def auth_kind(pid: str) -> AuthKind | None:
    spec = _REGISTRY.get(pid)
    return spec.auth_kind if spec else None


def supported_auth(pid: str) -> frozenset[AuthKind]:
    """Auth methods a provider supports — single source of truth for /login.

    Falls back to ``{auth_kind}`` when a spec leaves the explicit set empty.
    """
    spec = _REGISTRY.get(pid)
    if not spec:
        return frozenset()
    return spec.supported_auth or frozenset({spec.auth_kind})


def supports_auth(pid: str, kind: AuthKind) -> bool:
    return kind in supported_auth(pid)


def is_usage_exposing(pid: str) -> bool:
    spec = _REGISTRY.get(pid)
    return bool(spec and spec.usage_exposing)


def supports_inturn_key_rotation(pid: str) -> bool:
    """True for api/local providers (secret/endpoint chain rotates in-turn).

    False for oauth/cli providers (claude/codex): the CLI's active OAuth profile
    is process-global, so failover is seat substitution, not in-turn key rotation.
    """
    spec = _REGISTRY.get(pid)
    return bool(spec and spec.auth_kind in ("api", "local"))


def is_always_available(pid: str) -> bool:
    spec = _REGISTRY.get(pid)
    return bool(spec and spec.always_available)


def is_cooldown_exempt(pid: str) -> bool:
    spec = _REGISTRY.get(pid)
    return bool(spec and spec.cooldown_exempt)
