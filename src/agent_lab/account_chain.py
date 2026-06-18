"""auth_kind-branched account chain for the dynamic resilient room.

- api/local providers: in-turn secret N-account rotation (cooldown-filtered).
- oauth/cli providers: exactly ONE active CLI OAuth profile; NO in-turn key
  rotation. Failover for these is seat substitution (handled by the roster),
  not key rotation, mirroring credential_store.get_credential_chain() == []
  for OAUTH_ONLY providers.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from agent_lab import provider_registry
from agent_lab.credential_store import (
    _account_cooled,
    _sorted_accounts,
    get_account_chain,
    get_provider_accounts,
    is_credential_failure,
)
from agent_lab.usage_monitor import mark_exhausted

T = TypeVar("T")


def is_rotating(provider: str) -> bool:
    """True for api/local (in-turn rotation); False for oauth/cli (single profile)."""
    return provider_registry.supports_inturn_key_rotation(provider)


def active_profile(provider: str, *, now: float | None = None) -> tuple[str, str] | None:
    """Highest-priority non-cooled (label, profile_ref) for an oauth/cli provider.

    Returns None when no stored profile exists (use the CLI's ambient OAuth session).
    """
    for acct in _sorted_accounts(get_provider_accounts(provider)):
        if _account_cooled(acct, now=now):
            continue
        label = str(acct.get("label") or "").strip() or "profile"
        ref = str(acct.get("secret_or_profile_ref") or acct.get("secret") or "").strip()
        return (label, ref)
    return None


def usable_chain(provider: str, *, now: float | None = None) -> list[tuple[str, str]]:
    """auth_kind-aware usable entries.

    api/local: full priority-sorted, cooldown-filtered secret chain.
    oauth/cli: at most ONE entry (the single active profile), never a rotation.
    """
    if is_rotating(provider):
        return get_account_chain(provider, now=now)
    profile = active_profile(provider, now=now)
    return [profile] if profile else []


def call_with_account_chain(
    provider: str,
    fn: Callable[[str | None], T],
    *,
    now: float | None = None,
) -> T:
    """Invoke ``fn`` with auth_kind-correct failover.

    api/local: rotate through the secret chain on confirmed credential failures.
    oauth/cli: try the single active profile (or ambient OAuth) exactly once; on
    failure mark it exhausted and re-raise so the roster can substitute the seat.
    """
    chain = usable_chain(provider, now=now)

    if not is_rotating(provider):
        label, ref = chain[0] if chain else ("ambient", "")
        try:
            return fn(ref or None)
        except Exception as exc:  # noqa: BLE001 - reactive failover boundary
            if is_credential_failure(exc) and chain:
                mark_exhausted(provider, label, error=exc, now=now)
            raise

    if not chain:
        return fn(None)

    last_exc: BaseException | None = None
    for index, (label, secret) in enumerate(chain):
        try:
            return fn(secret)
        except Exception as exc:  # noqa: BLE001 - in-turn rotation boundary
            last_exc = exc
            is_last = index >= len(chain) - 1
            if is_credential_failure(exc):
                mark_exhausted(provider, label, error=exc, now=now)
                if not is_last:
                    continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{provider} account chain failed")
