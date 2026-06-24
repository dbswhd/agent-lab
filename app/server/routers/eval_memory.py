"""Read-only / pure-compute routes exposing the P4 eval harness and P5 memory store.

Stateless: every request builds fresh objects from the posted body — no cross-request
state, no singleton. Each route is gated by its flag and raises 404 when off, so flag
OFF ⇒ the endpoint is effectively absent (OFF-parity).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_lab.eval_harness import aggregate, eval_harness_enabled, score_instance
from agent_lab.memory_store import MemoryStore, event_memory_enabled

router = APIRouter(prefix="/api")


class EvalInstance(BaseModel):
    result_map: dict[str, str] = Field(default_factory=dict)
    f2p_ids: list[str] = Field(default_factory=list)
    p2p_ids: list[str] = Field(default_factory=list)
    status: str = "ok"


class EvalScoreBody(BaseModel):
    instances: list[EvalInstance] = Field(default_factory=list)


@router.post("/eval/score")
def eval_score(body: EvalScoreBody) -> dict[str, Any]:
    """Score a list of SWE-bench-style instances → per-instance results + aggregate.

    Pure compute (P4). 404 when AGENT_LAB_EVAL_HARNESS is off.
    """
    if not eval_harness_enabled():
        raise HTTPException(status_code=404, detail="eval harness disabled")
    results = [score_instance(i.result_map, i.f2p_ids, i.p2p_ids, i.status) for i in body.instances]
    return {"results": results, "aggregate": aggregate(results)}


class MemoryOp(BaseModel):
    op: str  # put | delete
    namespace: str
    key: str
    value: Any = None


class MemoryEvalBody(BaseModel):
    ops: list[MemoryOp] = Field(default_factory=list)


@router.post("/memory/eval")
def memory_eval(body: MemoryEvalBody) -> dict[str, Any]:
    """Apply an ops list to a FRESH per-request MemoryStore → namespaces/keys.

    Stateless (P5): no cross-request state. 404 when AGENT_LAB_EVENT_MEMORY is off.
    Unknown ops and non-JSON values are rejected with 400.
    """
    if not event_memory_enabled():
        raise HTTPException(status_code=404, detail="event memory disabled")
    store = MemoryStore()
    for op in body.ops:
        if op.op == "put":
            try:
                store.put(op.namespace, op.key, op.value)
            except TypeError as exc:
                raise HTTPException(status_code=400, detail=f"non-serializable value: {exc}") from exc
        elif op.op == "delete":
            store.delete(op.namespace, op.key)
        else:
            raise HTTPException(status_code=400, detail=f"unknown op: {op.op}")
    namespaces = store.namespaces()
    return {
        "namespaces": namespaces,
        "keys_by_namespace": {ns: store.list_keys(ns) for ns in namespaces},
    }
