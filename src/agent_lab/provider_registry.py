"""Provider catalog for the dynamic resilient room (AGENT_LAB_DYNAMIC_ROOM).

Single source of truth for which agent providers exist and how their
credentials/usage behave. Additive: this module does not change the existing
``credential_store`` typed providers or the default ["cursor","codex","claude"]
room composition. It only adds metadata the dynamic roster/usage layers consult.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AuthKind = Literal["api", "oauth", "cli", "local"]
FallbackClass = Literal["primary", "spare", "local"]


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


# Default catalog. cursor/claude/codex mirror the existing room agents; kimi and
# local are the new spare/floor providers from the approved plan.
_REGISTRY: dict[str, ProviderSpec] = {
    "cursor": ProviderSpec("cursor", "Cursor", "api", True, "primary"),
    "claude": ProviderSpec("claude", "Claude", "oauth", False, "primary"),
    "codex": ProviderSpec("codex", "Codex", "oauth", False, "primary"),
    "kimi": ProviderSpec("kimi", "KIMI", "api", True, "spare"),
    "local": ProviderSpec(
        "local", "Local", "local", False, "local",
        always_available=True, cooldown_exempt=True,
    ),
}

# Default room composition stays byte-stable with the pre-dynamic behavior.
DEFAULT_ROSTER: tuple[str, ...] = ("cursor", "codex", "claude")
# Ordered substitution pool consulted when a default seat is unavailable.
DEFAULT_SUBSTITUTION_PRIORITY: tuple[str, ...] = ("kimi", "local")


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
