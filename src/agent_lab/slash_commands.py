"""Slash-command surface for the dynamic resilient room (gajae-code style).

Six commands manage auth/accounts/models/usage/roster:
  /login /logout /accounts /model /usage /agents
Writes go through credential_store; secrets are always masked in output.
This module is the parser + dispatcher; the room router exposes it over HTTP.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from agent_lab.agent import roster as agent_roster
from agent_lab import provider_registry, usage_monitor
from agent_lab.consensus_gate import allocate_roles
from agent_lab.agents.registry import available_agents
from agent_lab.credential_store import (
    get_provider_accounts,
    mask_secret,
    set_provider_accounts,
)

SLASH_COMMANDS: tuple[str, ...] = (
    "login",
    "logout",
    "accounts",
    "model",
    "usage",
    "agents",
    "pipeline",
    "clarify",
    "plan",
    "execute",
)
# Handlers that need the session folder (mutate/read run.json).
_SESSION_HANDLERS: frozenset[str] = frozenset({"model", "pipeline", "clarify", "plan", "execute"})


def parse_command(text: str) -> tuple[str, list[str]] | None:
    """Parse "/cmd arg1 arg2" -> ("cmd", [args]); None when not a slash command."""
    s = (text or "").strip()
    if not s.startswith("/"):
        return None
    parts = s[1:].split()
    if not parts:
        return None
    return parts[0].lower(), parts[1:]


def is_slash_command(text: str) -> bool:
    parsed = parse_command(text)
    return parsed is not None and parsed[0] in SLASH_COMMANDS


def _err(command: str, message: str) -> dict[str, Any]:
    return {"ok": False, "command": command, "error": message}


def _require_provider(command: str, args: list[str]) -> str | dict[str, Any]:
    if not args:
        return _err(command, "provider required")
    provider = args[0]
    if not provider_registry.is_registered(provider):
        return _err(command, f"unknown provider: {provider}")
    return provider


def _masked_accounts(provider: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for acct in get_provider_accounts(provider):
        ref = str(acct.get("secret_or_profile_ref") or acct.get("secret") or "")
        out.append(
            {
                "label": str(acct.get("label") or ""),
                "masked": mask_secret(ref),
                "priority": acct.get("priority"),
                "cooldown_until": acct.get("cooldown_until"),
            }
        )
    return out


_AUTH_METHOD_LABELS = {"oauth": "OAuth (CLI 로그인)", "api": "API 키"}


def _login_methods() -> list[str]:
    """User-facing login methods = union of provider supported_auth, minus local."""
    methods: set[str] = set()
    for pid in provider_registry.provider_ids():
        methods |= set(provider_registry.supported_auth(pid))
    methods.discard("local")
    if "cli" in methods:  # treat CLI auth as OAuth in the picker
        methods.discard("cli")
        methods.add("oauth")
    return [m for m in ("oauth", "api") if m in methods]


def _login_provider_choices(method: str) -> dict[str, Any]:
    match = {method} | ({"cli"} if method == "oauth" else set())
    options: list[dict[str, Any]] = []
    for pid in provider_registry.provider_ids():
        if provider_registry.supported_auth(pid) & match:
            spec = provider_registry.get_provider(pid)
            options.append({"value": pid, "label": spec.label if spec else pid})
    if not options:
        return _err("login", f"no provider supports {method} login")
    return {
        "ok": True,
        "command": "login",
        "stage": "provider",
        "prompt": f"{_AUTH_METHOD_LABELS.get(method, method)} — provider 선택",
        "choices": {"kind": "provider", "method": method, "options": options},
    }


def _login_complete(method: str, provider: str, rest: list[str]) -> dict[str, Any]:
    if not provider_registry.is_registered(provider):
        return _err("login", f"unknown provider: {provider}")
    method = "oauth" if method == "cli" else method
    if not provider_registry.supports_auth(provider, method):  # type: ignore[arg-type]
        # tolerate cli/oauth equivalence
        if not (method == "oauth" and provider_registry.supports_auth(provider, "cli")):
            return _err("login", f"{provider} does not support {method} login")
    if method == "oauth":
        return {
            "ok": True,
            "command": "login",
            "provider": provider,
            "auth_kind": "oauth",
            "note": f"Run the {provider} CLI OAuth login; profiles are referenced, not stored as secrets.",
        }
    secret = rest[0] if rest else ""
    if not secret:
        return {
            "ok": True,
            "command": "login",
            "stage": "secret",
            "provider": provider,
            "auth_kind": "api",
            "prompt": f"{provider} API 키 입력",
            "input": {"kind": "secret", "prefill": f"/login api {provider} "},
        }
    accounts = get_provider_accounts(provider)
    accounts.append(
        {
            "label": f"account{len(accounts) + 1}",
            "secret_or_profile_ref": secret,
            "priority": len(accounts) + 1,
            "cooldown_until": 0.0,
        }
    )
    set_provider_accounts(provider, accounts)
    return {
        "ok": True,
        "command": "login",
        "provider": provider,
        "auth_kind": "api",
        "note": f"{provider} API 키가 등록되었습니다.",
        "accounts": _masked_accounts(provider),
    }


def _login(args: list[str]) -> dict[str, Any]:
    """Staged login picker.

    /login                      -> auth-method choices [OAuth, API key]
    /login <method>             -> provider choices supporting that method
    /login <method> <provider>  -> OAuth note, or API-key input prompt
    /login <method> <provider> <key> -> store API key
    /login <provider> [key]     -> legacy: infer method from supported_auth
    """
    if not args:
        return {
            "ok": True,
            "command": "login",
            "stage": "auth_method",
            "prompt": "로그인 방식 선택",
            "choices": {
                "kind": "auth_method",
                "options": [{"value": m, "label": _AUTH_METHOD_LABELS.get(m, m)} for m in _login_methods()],
            },
        }
    head = args[0].lower()
    if head in ("oauth", "api"):
        if len(args) == 1:
            return _login_provider_choices(head)
        return _login_complete(head, args[1], args[2:])
    # Legacy positional form: /login <provider> [key]
    if not provider_registry.is_registered(head):
        return _err("login", f"unknown provider: {head}")
    if len(args) > 1:
        kind = provider_registry.auth_kind(head) or "api"
        method = "oauth" if kind in ("oauth", "cli") else "api"
    elif provider_registry.supports_auth(head, "oauth"):
        method = "oauth"
    else:
        kind = provider_registry.auth_kind(head) or "api"
        method = "oauth" if kind in ("oauth", "cli") else "api"
    return _login_complete(method, head, args[1:])


def _logout_provider_choices() -> dict[str, Any]:
    options: list[dict[str, Any]] = []
    for pid in provider_registry.provider_ids():
        if pid == "local":
            continue
        spec = provider_registry.get_provider(pid)
        options.append({"value": pid, "label": spec.label if spec else pid})
    return {
        "ok": True,
        "command": "logout",
        "stage": "provider",
        "prompt": "로그아웃할 공급자 선택",
        "choices": {"kind": "provider", "options": options},
    }


def _logout(args: list[str]) -> dict[str, Any]:
    """Staged logout.

    /logout             -> provider choices
    /logout <provider>  -> clear API accounts; OAuth providers also start CLI logout
    """
    if not args:
        return _logout_provider_choices()
    provider = args[0].lower()
    if not provider_registry.is_registered(provider):
        return _err("logout", f"unknown provider: {provider}")
    if provider == "local":
        return _err("logout", "local provider does not require logout")

    accounts = get_provider_accounts(provider)
    had_accounts = bool(accounts)
    set_provider_accounts(provider, [])

    from agent_lab.credential_store import clear_provider_api_credentials

    cleared_credentials = clear_provider_api_credentials(provider)

    supports_oauth = provider_registry.supports_auth(provider, "oauth") or provider_registry.supports_auth(
        provider, "cli"
    )
    if supports_oauth:
        return {
            "ok": True,
            "command": "logout",
            "provider": provider,
            "auth_kind": "oauth",
            "cleared": had_accounts or cleared_credentials,
            "cleared_credentials": cleared_credentials,
            "note": f"{provider} CLI 로그아웃을 시작했습니다. 로컬 API 키 계정도 비워집니다.",
        }
    return {
        "ok": True,
        "command": "logout",
        "provider": provider,
        "auth_kind": "api",
        "cleared": True,
        "accounts": _masked_accounts(provider),
    }


def _accounts(args: list[str]) -> dict[str, Any]:
    provider = _require_provider("accounts", args)
    if isinstance(provider, dict):
        return provider
    sub = args[1].lower() if len(args) > 1 else "list"
    if sub == "list":
        return {"ok": True, "command": "accounts", "provider": provider, "accounts": _masked_accounts(provider)}
    if sub == "add":
        if len(args) < 4:
            return _err("accounts", "usage: /accounts <provider> add <label> <secret>")
        label, secret = args[2], args[3]
        accounts = get_provider_accounts(provider)
        accounts.append(
            {"label": label, "secret_or_profile_ref": secret, "priority": len(accounts) + 1, "cooldown_until": 0.0}
        )
        set_provider_accounts(provider, accounts)
        return {
            "ok": True,
            "command": "accounts",
            "provider": provider,
            "added": label,
            "accounts": _masked_accounts(provider),
        }
    if sub == "remove":
        if len(args) < 3:
            return _err("accounts", "usage: /accounts <provider> remove <label>")
        label = args[2]
        accounts = [a for a in get_provider_accounts(provider) if str(a.get("label") or "") != label]
        set_provider_accounts(provider, accounts)
        return {
            "ok": True,
            "command": "accounts",
            "provider": provider,
            "removed": label,
            "accounts": _masked_accounts(provider),
        }
    return _err("accounts", f"unknown subcommand: {sub}")


def _model_provider_picker() -> dict[str, Any]:
    from agent_lab.agent import model_prefs as mp

    return {
        "ok": True,
        "command": "model",
        "stage": "provider",
        "auto": mp.load_auto_multi_model(),
        "choices": {"kind": "model_provider", "options": mp.provider_picker_options()},
    }


def _model_preset_picker(provider: str) -> dict[str, Any]:
    from agent_lab.agent import model_prefs as mp

    if not mp.provider_has_model_picker(provider):
        return _err("model", f"unknown provider: {provider}")
    panel = mp.model_panel_options(provider)
    return {
        "ok": True,
        "command": "model",
        "stage": "preset",
        "provider": provider,
        "prompt": mp.provider_display_label(provider),
        "choices": {
            "kind": "model_panel",
            "provider": provider,
            "options": panel.get("options") or [],
            "efforts": panel.get("efforts") or [],
            "selected_model": panel.get("selected_model"),
            "selected_effort": panel.get("selected_effort"),
        },
    }


def _model_apply_preset(provider: str, preset_value: str) -> dict[str, Any]:
    from agent_lab.agent import model_prefs as mp

    if not provider_registry.is_registered(provider):
        return _err("model", f"unknown provider: {provider}")
    try:
        label = mp.apply_preset(provider, preset_value)
    except ValueError as exc:
        return _err("model", str(exc))
    # Carry a fresh panel snapshot so the frontend can redraw the still-open
    # side panel (model list + effort control) in place — model and effort
    # picks both land here, and neither should force the popover shut.
    panel = mp.model_panel_options(provider)
    return {
        "ok": True,
        "command": "model",
        "stage": "preset",
        "provider": provider,
        "prompt": mp.provider_display_label(provider),
        "model_updated": True,
        "note": f"{mp.provider_display_label(provider)} 모델을 {label}(으)로 설정했습니다.",
        "choices": {
            "kind": "model_panel",
            "provider": provider,
            "options": panel.get("options") or [],
            "efforts": panel.get("efforts") or [],
            "selected_model": panel.get("selected_model"),
            "selected_effort": panel.get("selected_effort"),
        },
    }


def _model_set_auto(enabled: bool) -> dict[str, Any]:
    from agent_lab.agent import model_prefs as mp

    mp.persist_auto_multi_model(enabled)
    return {
        "ok": True,
        "command": "model",
        "auto": enabled,
        "note": "여러 모델 사용" if enabled else "단일 모델 선택",
    }


def _looks_like_composition_args(args: list[str]) -> bool:
    if not args:
        return False
    if args[-1] in {"session", "default"}:
        return True
    return "," in " ".join(args)


def _model_compose(args: list[str], *, session_folder: Path | None = None) -> dict[str, Any]:
    if not args:
        composition = agent_roster.effective_room_composition(session_folder=session_folder)
        available = set(agent_roster.dynamic_available_ids(available_agents))
        options: list[dict[str, Any]] = []
        for pid in provider_registry.provider_picker_order():
            spec = provider_registry.get_provider(pid)
            if spec is None:
                continue
            options.append(
                {
                    "value": pid,
                    "label": spec.label,
                    "ready": pid in available,
                }
            )
        return {
            "ok": True,
            "command": "model",
            "stage": "composition",
            "prompt": "활성화할 에이전트 선택 (복수 선택 가능)",
            "composition": composition,
            "choices": {"kind": "multi", "current": composition, "options": options},
        }
    scope: str | None = None
    raw = list(args)
    if raw and raw[-1] in {"session", "default"}:
        scope = raw.pop()
    composition = agent_roster.normalize_composition_order([tok for tok in ",".join(raw).split(",") if tok.strip()])
    if not composition:
        return _err("model", "empty composition")
    if scope is None:
        return {
            "ok": True,
            "command": "model",
            "stage": "persist",
            "composition": composition,
            "prompt": f"[{', '.join(composition)}] — 적용 범위를 선택하세요",
            "choices": {
                "kind": "scope",
                "composition": composition,
                "options": [
                    {"value": "session", "label": "이번 세션만 (세션 동안 유지)"},
                    {"value": "default", "label": "기본값으로 저장"},
                ],
            },
        }
    joined = ",".join(composition)
    if scope == "session":
        if session_folder is None:
            return _err("model", "session scope requires an active session")
        from agent_lab.run.meta import patch_run_meta

        patch_run_meta(
            session_folder,
            lambda meta: {**meta, "room_models": composition},
        )
        note = f"Room 구성을 {', '.join(composition)}로 변경했습니다 (이 세션 동안 유지)."
    elif scope == "default":
        from agent_lab.room.models_config import persist_default_room_models

        persist_default_room_models(composition)
        os.environ["AGENT_LAB_ROOM_MODELS"] = joined
        note = f"Room 구성을 {', '.join(composition)}로 변경했습니다 (기본값 저장)."
    else:
        os.environ["AGENT_LAB_ROOM_MODELS"] = joined
        note = f"Room 구성을 {', '.join(composition)}로 변경했습니다."
    substitution = agent_roster.override_substitution() or list(provider_registry.DEFAULT_SUBSTITUTION_PRIORITY)
    return {
        "ok": True,
        "command": "model",
        "composition": composition,
        "substitution": substitution,
        "updated": True,
        "scope": scope,
        "note": note,
    }


def _model(args: list[str], *, session_folder: Path | None = None) -> dict[str, Any]:
    """Model picker + room composition.

    /model                         -> provider picker (OpenAI / Anthropic / …)
    /model <provider>              -> preset picker for that provider
    /model <provider> <preset>     -> apply preset (e.g. opus|high)
    /model auto on|off             -> toggle multi-model (compose) mode
    /model compose …               -> room agent composition
    /model cursor,codex session    -> legacy composition shorthand
    """
    if not args:
        return _model_provider_picker()
    head = args[0].lower()
    if head == "auto":
        token = (args[1] if len(args) > 1 else "").lower()
        if token not in {"on", "off", "1", "0"}:
            return _err("model", "usage: /model auto on|off")
        return _model_set_auto(token in {"on", "1"})
    if head == "compose":
        return _model_compose(args[1:], session_folder=session_folder)
    if _looks_like_composition_args(args):
        return _model_compose(args, session_folder=session_folder)
    if len(args) == 1 and provider_registry.is_registered(head):
        from agent_lab.agent import model_prefs as mp

        if mp.provider_has_model_picker(head):
            return _model_preset_picker(head)
    if len(args) >= 2 and provider_registry.is_registered(head):
        from agent_lab.agent import model_prefs as mp

        if mp.provider_has_model_picker(head):
            token = args[1].strip()
            if len(args) >= 3 and args[1].lower() == "effort":
                return _model_apply_preset(head, f"effort:{args[2]}")
            return _model_apply_preset(head, token)
    return _model_compose(args, session_folder=session_folder)


def _usage(args: list[str]) -> dict[str, Any]:
    if not args:
        options: list[dict[str, Any]] = []
        for pid in provider_registry.provider_ids():
            if pid == "local":
                continue
            spec = provider_registry.get_provider(pid)
            options.append({"value": pid, "label": spec.label if spec else pid})
        return {
            "ok": True,
            "command": "usage",
            "stage": "provider",
            "prompt": "사용량을 확인할 공급자 선택",
            "choices": {"kind": "provider", "options": options},
        }
    providers = [args[0]] if args and provider_registry.is_registered(args[0]) else provider_registry.provider_ids()
    rows: list[dict[str, Any]] = []
    for pid in providers:
        if pid == "local":
            continue
        for acct in get_provider_accounts(pid):
            label = str(acct.get("label") or "")
            rows.append(
                {
                    "provider": pid,
                    "label": label,
                    "cooldown_active": usage_monitor.cooldown_active(pid, label),
                    "usage_exposing": provider_registry.is_usage_exposing(pid),
                }
            )
    return {"ok": True, "command": "usage", "rows": rows}


def _agents(args: list[str]) -> dict[str, Any]:
    from agent_lab.agents.registry import available_agents

    roster = [str(a) for a in agent_roster.resolve_active_agents(None, available_agents)]
    if not args:
        options: list[dict[str, Any]] = []
        for pid in roster:
            spec = provider_registry.get_provider(pid)
            options.append({"value": pid, "label": spec.label if spec else pid})
        return {
            "ok": True,
            "command": "agents",
            "stage": "roster",
            "prompt": "현재 Room 로스터",
            "roster": roster,
            "roles": allocate_roles(roster),
            "choices": {"kind": "info", "options": options},
        }
    return {"ok": True, "command": "agents", "roster": roster, "roles": allocate_roles(roster)}


def _set_mission_phase(session_folder: Path, command: str, target_phase: str) -> dict[str, Any]:
    from agent_lab.mission.loop import get_mission_loop
    from agent_lab.run.meta import patch_run_meta, read_run_meta

    def _set(run: dict[str, Any]) -> dict[str, Any]:
        ml = get_mission_loop(run)
        ml["phase"] = target_phase
        run["mission_loop"] = ml
        return run

    patch_run_meta(session_folder, _set)
    run = read_run_meta(session_folder)
    phase = str(get_mission_loop(run).get("phase") or "")
    return {"ok": True, "command": command, "phase": phase}


def _pipeline(args: list[str], *, session_folder: Path | None = None) -> dict[str, Any]:
    """/pipeline — show current pipeline stage (phase + auto-routed mode)."""
    if session_folder is None:
        return _err("pipeline", "no active session")
    from agent_lab.mode_router import select_mode
    from agent_lab.run.meta import read_run_meta

    run = read_run_meta(session_folder)
    ml = run.get("mission_loop") if isinstance(run, dict) else {}
    phase = str((ml or {}).get("phase") or "MISSION_DEFINE")
    mode = select_mode(run) if isinstance(run, dict) else None
    return {
        "ok": True,
        "command": "pipeline",
        "pipeline": "on",
        "phase": phase,
        "mode": mode,
    }


def _clarify(args: list[str], *, session_folder: Path | None = None) -> dict[str, Any]:
    """/clarify — manually enter the CLARIFY stage (deep-interview analog)."""
    if session_folder is None:
        return _err("clarify", "no active session")
    result = _set_mission_phase(session_folder, "clarify", "CLARIFY")
    from agent_lab.plan.workflow import get_plan_workflow, init_plan_workflow_on_plan_send
    from agent_lab.run.meta import read_run_meta

    run = read_run_meta(session_folder)
    if not get_plan_workflow(run).get("enabled"):
        init_plan_workflow_on_plan_send(session_folder)
        result["plan_workflow_initialized"] = True
    return result


_EXECUTE_INTENT_ARGS: frozenset[str] = frozenset({"execute", "--execute"})


def _plan(args: list[str], *, session_folder: Path | None = None) -> dict[str, Any]:
    """/plan — manually enter the consensus/plan stage (ralplan analog).

    ``/plan execute`` additionally enables mission_loop right away, capturing
    the human's execute intent at plan-entry time (P1-2) instead of leaving
    them to separately discover ``/execute`` once discuss has converged.
    """
    if session_folder is None:
        return _err("plan", "no active session")
    result = _set_mission_phase(session_folder, "plan", "DISCUSS")
    from agent_lab.plan.workflow import get_plan_workflow, init_plan_workflow_on_plan_send
    from agent_lab.run.meta import read_run_meta

    run = read_run_meta(session_folder)
    if not get_plan_workflow(run).get("enabled"):
        init_plan_workflow_on_plan_send(session_folder)
        result["plan_workflow_initialized"] = True

    if any(a.strip().lower() in _EXECUTE_INTENT_ARGS for a in args):
        from agent_lab.mission.loop import enable_mission_loop, get_mission_loop

        if not get_mission_loop(run).get("enabled"):
            enable_mission_loop(session_folder)
        result["execute_intent"] = True

    from agent_lab.room.turn_policy import stamp_pending_skill_intent

    stamp_pending_skill_intent(session_folder, "plan")
    result["skill_intent"] = "plan"
    return result


def _execute(args: list[str], *, session_folder: Path | None = None) -> dict[str, Any]:
    """/execute — enqueue the session plan for worktree dry-run + Oracle verify.

    Room discuss/plan rounds converge in chat but have no chat-native path to
    the execute gate (``mission_loop.run_plan_gate``) — reaching it previously
    required knowing about the ``/mission-loop/*`` REST API and the Autonomy
    dial. This command is the explicit human action L0 "Manual" already
    requires for the execute/diff half (plan/NORTH-STAR.md ``L0``); it enables
    mission_loop for this session on first use and immediately runs the gate
    against the session's current plan.md.
    """
    if session_folder is None:
        return _err("execute", "no active session")

    from agent_lab.mission.loop import enable_mission_loop, get_mission_loop, run_plan_gate
    from agent_lab.plan.paths import read_session_plan_md
    from agent_lab.run.meta import read_run_meta

    run = read_run_meta(session_folder)
    plan_md = read_session_plan_md(session_folder, run)
    if not (plan_md or "").strip():
        return _err("execute", "no plan.md content yet — run /plan and let the room converge first")

    if not get_mission_loop(run).get("enabled"):
        enable_mission_loop(session_folder)

    result = run_plan_gate(session_folder, plan_md)
    if result.get("skipped"):
        return {"ok": False, "command": "execute", "skipped": True, "reason": result.get("reason")}
    return {
        "ok": True,
        "command": "execute",
        "phase": str(result.get("phase") or ""),
        "status": result.get("status"),
        "gate_result": result,
    }


_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "login": _login,
    "logout": _logout,
    "accounts": _accounts,
    "model": _model,
    "usage": _usage,
    "agents": _agents,
    "pipeline": _pipeline,
    "clarify": _clarify,
    "plan": _plan,
    "execute": _execute,
}


def dispatch(text: str, *, session_folder: Path | None = None) -> dict[str, Any]:
    parsed = parse_command(text)
    if parsed is None:
        return {"ok": False, "error": "not a slash command"}
    cmd, args = parsed
    handler = _HANDLERS.get(cmd)
    if handler is None:
        return _err(cmd, "unknown command")
    if cmd in _SESSION_HANDLERS:
        return handler(args, session_folder=session_folder)
    return handler(args)
