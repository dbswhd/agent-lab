"""Codex ChatGPT OAuth profile storage (메인/서브) for Room failover."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

from agent_lab.env_flags import env_bool

CodexOAuthSlot = Literal["primary", "fallback"]
_OAUTH_SLOTS: tuple[CodexOAuthSlot, ...] = ("primary", "fallback")

T = TypeVar("T")


def _config_dir() -> Path:
    from agent_lab.app_config import config_dir

    return config_dir()


def profiles_root() -> Path:
    return _config_dir() / "codex-oauth"


def meta_path() -> Path:
    return profiles_root() / "meta.json"


def live_auth_path() -> Path:
    return Path.home() / ".codex" / "auth.json"


def profile_auth_path(slot: CodexOAuthSlot) -> Path:
    return profiles_root() / slot / "auth.json"


def auth_revoked_marker_path() -> Path:
    return _config_dir() / "codex-auth-revoked.json"


def mark_codex_auth_revoked(detail: str) -> None:
    """Record that a real codex call died on a revoked/invalidated OAuth token.

    ``codex login status`` only reads the local auth.json and keeps reporting
    "Logged in" after a server-side revocation, so preflight must remember the
    last observed live failure. The marker auto-clears once ``auth.json`` is
    newer than it (i.e. the user re-ran ``codex login``).
    """
    path = auth_revoked_marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "detail": detail[:500],
                "marked_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def clear_codex_auth_revoked() -> None:
    auth_revoked_marker_path().unlink(missing_ok=True)


def codex_auth_revoked_detail() -> str | None:
    """Active revocation detail, or None. Auto-clears after a re-login."""
    marker = auth_revoked_marker_path()
    if not marker.is_file():
        return None
    auth = live_auth_path()
    if auth.is_file():
        if auth.stat().st_mtime > marker.stat().st_mtime:
            # auth.json was rewritten after the failure — user re-logged in.
            clear_codex_auth_revoked()
            return None
        # capture/apply use copy2 (mtime preserved), so a snapshot restore can
        # leave auth.json with an old mtime forever — compare token content too:
        # a re-login always bumps `last_refresh` past the marker timestamp.
        marked_at = _marker_marked_at(marker)
        last_refresh = _auth_last_refresh(_read_auth_json(auth))
        if marked_at and last_refresh and last_refresh > marked_at:
            clear_codex_auth_revoked()
            return None
    try:
        detail = json.loads(marker.read_text(encoding="utf-8")).get("detail")
    except (json.JSONDecodeError, OSError):
        detail = None
    return str(detail or "Codex OAuth 세션이 만료되었습니다 — 재로그인 필요")


def _marker_marked_at(marker: Path) -> datetime | None:
    try:
        raw = json.loads(marker.read_text(encoding="utf-8")).get("marked_at")
    except (json.JSONDecodeError, OSError):
        return None
    return _parse_utc_timestamp(raw)


def _parse_utc_timestamp(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _read_auth_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _auth_account_id(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return None
    account = str(tokens.get("account_id") or "").strip()
    return account or None


def _auth_last_refresh(data: dict[str, Any] | None) -> datetime | None:
    if not data:
        return None
    return _parse_utc_timestamp(data.get("last_refresh"))


def _resolve_codex_bin() -> str | None:
    from agent_lab.codex.cli import resolve_codex_bin

    return resolve_codex_bin()


def _codex_env() -> dict[str, str]:
    from agent_lab.codex.cli import _codex_env

    return _codex_env(api_key=None)


def load_meta() -> dict[str, Any]:
    path = meta_path()
    if not path.is_file():
        return {
            "primary_label": "메인",
            "fallback_label": "서브",
            "primary_captured_at": None,
            "fallback_captured_at": None,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "primary_label": "메인",
            "fallback_label": "서브",
            "primary_captured_at": None,
            "fallback_captured_at": None,
        }
    if not isinstance(data, dict):
        data = {}
    return {
        "primary_label": str(data.get("primary_label") or "메인").strip() or "메인",
        "fallback_label": str(data.get("fallback_label") or "서브").strip() or "서브",
        "primary_captured_at": data.get("primary_captured_at"),
        "fallback_captured_at": data.get("fallback_captured_at"),
    }


def save_meta(patch: dict[str, Any]) -> dict[str, Any]:
    meta = load_meta()
    for key in (
        "primary_label",
        "fallback_label",
        "primary_captured_at",
        "fallback_captured_at",
    ):
        if key not in patch:
            continue
        val = patch[key]
        if key.endswith("_label") and val is not None:
            meta[key] = str(val).strip() or meta[key]
        else:
            meta[key] = val
    meta_path().parent.mkdir(parents=True, exist_ok=True)
    meta_path().write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return meta


def profile_exists(slot: CodexOAuthSlot) -> bool:
    path = profile_auth_path(slot)
    return path.is_file() and path.stat().st_size > 0


def live_login_status() -> tuple[bool, str | None]:
    if env_bool("AGENT_LAB_MOCK_AGENTS"):
        return True, "mock"
    revoked = codex_auth_revoked_detail()
    if revoked:
        # `codex login status` keeps saying "Logged in" from the local
        # auth.json even after a server-side revocation — trust the last
        # observed live failure until auth.json is rewritten by a re-login.
        return False, f"Codex OAuth 세션 만료 (revoked) — /login 으로 재로그인: {revoked}"
    codex = _resolve_codex_bin()
    if not codex:
        return False, "codex CLI not found"
    try:
        result = subprocess.run(
            [codex, "login", "status"],
            capture_output=True,
            text=True,
            timeout=12.0,
            env=_codex_env(),
            cwd=str(Path.home()),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)[:200]
    combined = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
    low = combined.lower()
    if result.returncode == 0 and "logged in" in low:
        line = next((ln.strip() for ln in combined.splitlines() if ln.strip()), "logged in")
        return True, line
    if live_auth_path().is_file():
        return True, "auth.json present"
    return False, combined[:200] or "not logged in"


def capture_profile(slot: CodexOAuthSlot, *, label: str | None = None) -> dict[str, Any]:
    live = live_auth_path()
    if not live.is_file():
        ok, detail = live_login_status()
        if not ok:
            raise RuntimeError(detail or "Codex OAuth 세션이 없습니다. 터미널에서 codex login 후 다시 시도하세요.")
        raise RuntimeError("~/.codex/auth.json 이 없습니다. codex login 후 다시 시도하세요.")

    dest = profile_auth_path(slot)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(live, dest)
    dest.chmod(0o600)
    # Fresh capture = fresh login — drop any recorded revocation immediately.
    clear_codex_auth_revoked()

    captured_at = datetime.now(timezone.utc).isoformat()
    label_key = f"{slot}_label"
    patch: dict[str, Any] = {f"{slot}_captured_at": captured_at}
    if label and label.strip():
        patch[label_key] = label.strip()
    meta = save_meta(patch)

    return {
        "ok": True,
        "slot": slot,
        "label": meta[label_key],
        "captured_at": captured_at,
        "path": str(dest),
    }


def clear_profile(slot: CodexOAuthSlot) -> None:
    path = profile_auth_path(slot)
    if path.is_file():
        path.unlink()
    meta = load_meta()
    meta[f"{slot}_captured_at"] = None
    save_meta(meta)


def live_session_is_fresher(slot: CodexOAuthSlot) -> bool:
    """True when live ~/.codex holds a newer token than the snapshot, same account.

    Codex rotates the refresh token on refresh and rewrites auth.json in place.
    Re-applying an older snapshot reverts to a rotated-out refresh token, which
    the server rejects with `refresh_token_invalidated` — and reuse detection
    can revoke the whole session family, killing even a fresh re-login.
    """
    live = _read_auth_json(live_auth_path())
    snap = _read_auth_json(profile_auth_path(slot))
    live_account = _auth_account_id(live)
    snap_account = _auth_account_id(snap)
    if not live_account or not snap_account or live_account != snap_account:
        return False
    live_refresh = _auth_last_refresh(live)
    snap_refresh = _auth_last_refresh(snap)
    if live_refresh is None or snap_refresh is None:
        return False
    return live_refresh > snap_refresh


def sync_profile_from_live(slot: CodexOAuthSlot) -> None:
    """Refresh a stored snapshot from the live session (token-rotation sync-back)."""
    live = live_auth_path()
    if not live.is_file():
        return
    dest = profile_auth_path(slot)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(live, dest)
    dest.chmod(0o600)
    save_meta({f"{slot}_captured_at": datetime.now(timezone.utc).isoformat()})


def apply_profile(slot: CodexOAuthSlot) -> None:
    src = profile_auth_path(slot)
    if not src.is_file():
        raise RuntimeError(f"Codex OAuth profile missing: {slot}")
    if live_session_is_fresher(slot):
        # Same account, newer live token (re-login or rotation) — overwriting
        # live would revert to an invalidated refresh token. Sync the snapshot
        # forward instead and keep the live session as-is.
        sync_profile_from_live(slot)
        return
    live = live_auth_path()
    live.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, live)
    live.chmod(0o600)


def _profile_auth_fingerprint(slot: CodexOAuthSlot) -> str | None:
    path = profile_auth_path(slot)
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def oauth_account_chain() -> list[tuple[str, CodexOAuthSlot | None]]:
    """Ordered (label, slot). slot=None → use live ~/.codex without overlay."""
    meta = load_meta()
    chain: list[tuple[str, CodexOAuthSlot | None]] = []
    seen_fp: set[str] = set()
    for slot in _OAUTH_SLOTS:
        if not profile_exists(slot):
            continue
        fp = _profile_auth_fingerprint(slot)
        if fp and fp in seen_fp:
            continue
        if fp:
            seen_fp.add(fp)
        chain.append((meta[f"{slot}_label"], slot))
    if not chain:
        chain.append(("live", None))
    return chain


def codex_oauth_ready() -> tuple[bool, str | None]:
    revoked = codex_auth_revoked_detail()
    if revoked:
        # A stored profile snapshot carries the same revoked token, so
        # profile_exists() alone must not win over an observed live failure.
        return False, f"Codex OAuth 세션 만료 (revoked) — /login 으로 재로그인: {revoked}"
    if profile_exists("primary") or profile_exists("fallback"):
        return True, None
    ok, detail = live_login_status()
    if ok:
        return True, None
    return False, detail or "codex OAuth 미등록 — codex login 후 Settings에서 계정 캡처"


def public_codex_oauth_payload() -> dict[str, Any]:
    meta = load_meta()
    live_ok, live_detail = live_login_status()
    primary_fp = _profile_auth_fingerprint("primary")
    fallback_fp = _profile_auth_fingerprint("fallback")
    fallback_stale = bool(
        profile_exists("primary")
        and profile_exists("fallback")
        and primary_fp
        and fallback_fp
        and primary_fp != fallback_fp
    )
    return {
        "ok": True,
        "path": str(profiles_root()),
        "primary_label": meta["primary_label"],
        "fallback_label": meta["fallback_label"],
        "has_primary": profile_exists("primary"),
        "has_fallback": profile_exists("fallback"),
        "primary_captured_at": meta.get("primary_captured_at"),
        "fallback_captured_at": meta.get("fallback_captured_at"),
        "fallback_stale": fallback_stale,
        "live_logged_in": live_ok,
        "live_detail": live_detail,
    }


def probe_profile(slot: CodexOAuthSlot) -> dict[str, Any]:
    """Apply a stored profile and run `codex login status` (Settings diagnostics)."""
    if not profile_exists(slot):
        return {"slot": slot, "ok": False, "detail": "프로필 없음 — Settings에서 캡처"}
    try:
        apply_profile(slot)
        ok, detail = live_login_status()
        return {
            "slot": slot,
            "ok": ok,
            "detail": detail or ("logged in" if ok else "not logged in"),
        }
    except Exception as exc:
        return {"slot": slot, "ok": False, "detail": str(exc)[:240]}


def probe_captured_profiles() -> list[dict[str, Any]]:
    meta = load_meta()
    rows: list[dict[str, Any]] = []
    for slot in _OAUTH_SLOTS:
        if not profile_exists(slot):
            continue
        row = probe_profile(slot)
        row["label"] = meta[f"{slot}_label"]
        rows.append(row)
    return rows


def call_with_codex_oauth_fallback(
    fn: Callable[[CodexOAuthSlot | None], T],
    *,
    on_switch: Callable[[str, CodexOAuthSlot], None] | None = None,
) -> T:
    """Try stored OAuth profiles in order; slot=None uses live ~/.codex session."""
    chain = oauth_account_chain()
    last_exc: BaseException | None = None
    for index, (label, slot) in enumerate(chain):
        try:
            if slot is not None:
                apply_profile(slot)
                if on_switch and index > 0:
                    on_switch(label, slot)
            result = fn(slot)
            if slot is not None:
                _sync_back_after_call(slot)
            return result
        except Exception as exc:
            last_exc = exc
            is_last = index >= len(chain) - 1
            if not is_last and _should_failover_codex(exc):
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Codex OAuth account chain failed")


def _sync_back_after_call(slot: CodexOAuthSlot) -> None:
    """After a successful call, persist any token rotation back into the snapshot."""
    try:
        if live_session_is_fresher(slot):
            sync_profile_from_live(slot)
    except OSError:
        pass


def _should_failover_codex(exc: BaseException) -> bool:
    """Whether to try the next stored OAuth profile (quota only — not auth errors)."""
    return _is_codex_usage_limit(exc)


def codex_auth_failure_remediation(detail: str) -> list[str]:
    """Actionable steps when Codex OAuth token fails (401 / invalidated)."""
    return [
        "Composer에서 `/login` → Codex 선택 — 앱 안에서 브라우저 OAuth 재로그인 (완료 시 메인 프로필 자동 캡처)",
        "또는 터미널에서 `codex logout` 후 `codex login` — 이후 Settings → Codex OAuth → **현재 로그인 → 메인** 재캡처",
        "메인·서브가 같은 계정이면 서브 캡처는 한도 failover에만 의미 있음 — 다른 계정이 아니면 서브 삭제",
    ]


def _is_codex_usage_limit(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "usage limit" in text or "rate limit" in text or "quota" in text
