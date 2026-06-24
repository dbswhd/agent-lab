"""Namespace KV memory store (G7).

Pure stdlib, deterministic. Default OFF via AGENT_LAB_EVENT_MEMORY, and intentionally
NOT wired into any consumer this increment (zero consumer call sites => OFF-parity).

``MemoryStore`` is an in-memory ``namespace -> key -> value`` map. It performs NO
implicit IO: the store mutates only in memory unless ``dump(path)`` is called, and
``load(path)`` REPLACES the store's current contents (deterministic). Values must be
JSON-serializable; this is validated on ``put`` BEFORE any mutation so a rejected
value never partially mutates the store. Listing methods return deterministically
sorted output.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_TRUE = frozenset({"1", "true", "yes", "on"})


def event_memory_enabled() -> bool:
    """AGENT_LAB_EVENT_MEMORY (default OFF). Shared with event_schema; unused this increment."""
    return (os.getenv("AGENT_LAB_EVENT_MEMORY") or "").strip().lower() in _TRUE


class MemoryStore:
    """In-memory namespace-isolated key-value store with opt-in JSONL persistence."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def put(self, namespace: str, key: str, value: Any) -> None:
        """Store ``value`` under ``(namespace, key)``.

        Validates JSON-serializability BEFORE mutating; on failure raises TypeError
        without creating the namespace or storing anything (no partial mutation).
        """
        json.dumps(value)  # validate-before-mutate; raises TypeError on non-serializable
        self._data.setdefault(namespace, {})[key] = value

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        """Return the stored value, or ``default`` when absent (never raises)."""
        return self._data.get(namespace, {}).get(key, default)

    def list_keys(self, namespace: str) -> list[str]:
        """Return the namespace's keys, deterministically sorted (empty for unknown ns)."""
        return sorted(self._data.get(namespace, {}).keys())

    def delete(self, namespace: str, key: str) -> bool:
        """Remove ``(namespace, key)``; return True if it existed, else False."""
        ns = self._data.get(namespace)
        if ns is None or key not in ns:
            return False
        del ns[key]
        return True

    def namespaces(self) -> list[str]:
        """Return all namespace names, deterministically sorted."""
        return sorted(self._data.keys())

    def dump(self, path: str | Path) -> None:
        """Write one JSONL record per (namespace, key, value), in deterministic order."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for ns in sorted(self._data.keys()):
                for key in sorted(self._data[ns].keys()):
                    row = {"namespace": ns, "key": key, "value": self._data[ns][key]}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def load(self, path: str | Path) -> None:
        """REPLACE the store's contents with the records in ``path`` (deterministic)."""
        fresh: dict[str, dict[str, Any]] = {}
        with Path(path).open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                fresh.setdefault(row["namespace"], {})[row["key"]] = row["value"]
        self._data = fresh
