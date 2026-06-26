"""OpenAI-compatible chat completions API (P2-7).

Exposes POST /v1/chat/completions with standard OpenAI request/response shapes.
Internally runs a Room discussion turn (or quick single-agent for low-latency)
and maps the agent replies to an OpenAI choices array.

Non-streaming: collects all agent replies, returns a single completion response.
Streaming: emits chat.completion.chunk SSE events as content arrives.

Response header X-AgentLab-RunId contains the session_id for audit trail.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1")

_MODEL_PRESET: dict[str, str] = {
    "gpt-4": "consensus",
    "gpt-4o": "consensus",
    "gpt-3.5-turbo": "fast",
    "agent-lab-fast": "fast",
    "agent-lab-balanced": "consensus",
    "agent-lab-thorough": "thorough",
}


class _Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "agent-lab-balanced"
    messages: list[_Message] = Field(default_factory=list)
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    user: str | None = None


def _resolve_preset(model: str) -> str:
    return _MODEL_PRESET.get(model.strip().lower(), "consensus")


def _extract_topic(messages: list[_Message]) -> str:
    """Return the last user message content as the room topic."""
    for msg in reversed(messages):
        if msg.role == "user":
            return msg.content.strip()
    return (messages[-1].content if messages else "").strip()


def _extract_system(messages: list[_Message]) -> str | None:
    for msg in messages:
        if msg.role == "system":
            return msg.content.strip()
    return None


def _completion_id() -> str:
    return "chatcmpl-agentlab-" + uuid.uuid4().hex[:16]


def _now_ts() -> int:
    return int(time.time())


def _build_completion(
    completion_id: str,
    model: str,
    content: str,
    session_id: str | None = None,
    finish_reason: str = "stop",
) -> dict[str, Any]:
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": _now_ts(),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "system_fingerprint": None,
        **({"agentlab": {"session_id": session_id}} if session_id else {}),
    }


def _chunk(completion_id: str, model: str, delta_content: str, finish: bool = False) -> str:
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": _now_ts(),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {} if finish else {"content": delta_content},
                "finish_reason": "stop" if finish else None,
            }
        ],
    }
    return f"data: {json.dumps(payload)}\n\n"


def _run_room_sync(
    topic: str,
    preset: str,
    event_q: "queue.Queue[dict[str, Any] | None]",
) -> tuple[str | None, str | None]:
    """Run a Room turn in a background thread, push SSE events to event_q."""
    from agent_lab.room import run_room
    from agent_lab.room_preset import preset_turn_profile

    turn_profile = preset_turn_profile(preset, fallback="quick")
    session_id: str | None = None
    synthesized: str | None = None

    def on_event(typ: str, payload: dict[str, Any]) -> None:
        nonlocal session_id
        if typ == "complete" and "session_id" in payload:
            session_id = payload["session_id"]
        event_q.put({"type": typ, **payload})

    try:
        folder, messages, plan_md = run_room(
            topic,
            synthesize=False,
            turn_profile=turn_profile,
            on_event=on_event,
        )
        session_id = folder.name
        agent_replies = [m for m in messages if m.role == "agent"]
        if agent_replies:
            if len(agent_replies) == 1:
                synthesized = agent_replies[0].content
            else:
                parts = [f"[{m.agent or 'agent'}]\n{m.content}" for m in agent_replies]
                synthesized = "\n\n---\n\n".join(parts)
        elif plan_md:
            synthesized = plan_md
    except Exception as exc:
        event_q.put({"type": "_error", "detail": str(exc)})
    finally:
        event_q.put(None)

    return session_id, synthesized


@router.post("/chat/completions")
async def chat_completions(request: Request, body: ChatCompletionRequest) -> Any:
    """OpenAI-compatible chat completions endpoint backed by Agent Lab Room."""
    topic = _extract_topic(body.messages)
    if not topic:
        return JSONResponse(
            {"error": {"message": "messages must include at least one user message", "type": "invalid_request_error"}},
            status_code=400,
        )

    model_id = body.model.strip() or "agent-lab-balanced"
    preset = _resolve_preset(model_id)
    completion_id = _completion_id()
    event_q: queue.Queue[dict[str, Any] | None] = queue.Queue()

    if body.stream:
        def generate():
            session_id: list[str | None] = [None]

            def _worker():
                sid, _ = _run_room_sync(topic, preset, event_q)
                session_id[0] = sid

            t = threading.Thread(target=_worker, daemon=True)
            t.start()

            yield _chunk(completion_id, model_id, "", finish=False).replace(
                '"content": ""', '"role": "assistant", "content": ""'
            ).replace('"role": "assistant", ', "")

            while True:
                ev = event_q.get()
                if ev is None:
                    break
                typ = ev.get("type", "")
                if typ == "agent_done":
                    frag = str(ev.get("content") or ev.get("reply") or "")
                    if frag:
                        yield _chunk(completion_id, model_id, frag)

            t.join(timeout=5)
            yield _chunk(completion_id, model_id, "", finish=True)
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"X-AgentLab-Preset": preset},
        )

    else:
        session_id_holder: list[str | None] = [None]
        content_holder: list[str | None] = [None]

        def _worker():
            sid, content = _run_room_sync(topic, preset, event_q)
            session_id_holder[0] = sid
            content_holder[0] = content

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        while True:
            try:
                ev = event_q.get(timeout=120)
            except queue.Empty:
                break
            if ev is None:
                break
        t.join(timeout=5)

        content = content_holder[0] or ""
        session_id = session_id_holder[0]
        resp = _build_completion(completion_id, model_id, content, session_id=session_id)
        headers = {}
        if session_id:
            headers["X-AgentLab-RunId"] = session_id
        return JSONResponse(resp, headers=headers)


@router.get("/models")
async def list_models() -> dict[str, Any]:
    """List available Agent Lab models in OpenAI format."""
    now = _now_ts()
    models = [
        {"id": "agent-lab-fast", "object": "model", "created": now, "owned_by": "agent-lab",
         "description": "Single-agent fast response (fast preset)"},
        {"id": "agent-lab-balanced", "object": "model", "created": now, "owned_by": "agent-lab",
         "description": "3-agent consensus (consensus preset)"},
        {"id": "agent-lab-thorough", "object": "model", "created": now, "owned_by": "agent-lab",
         "description": "3-agent + adversarial + live judge (thorough preset)"},
    ]
    return {"object": "list", "data": models}
