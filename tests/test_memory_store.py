"""P5 namespace KV memory store (AGENT_LAB_EVENT_MEMORY, default off).

Covers AC8-AC14 + N2 dump byte-stability.
"""

from __future__ import annotations

from pathlib import Path

from agent_lab.memory_store import MemoryStore


def test_ac8_put_get_and_default():
    s = MemoryStore()
    s.put("ns", "k", {"v": 1})
    assert s.get("ns", "k") == {"v": 1}
    assert s.get("ns", "missing") is None
    assert s.get("ns", "missing", "dflt") == "dflt"
    assert s.get("other", "k") is None  # unknown namespace


def test_ac9_namespaces_isolated():
    s = MemoryStore()
    s.put("a", "k", 1)
    s.put("b", "k", 2)
    assert s.get("a", "k") == 1
    assert s.get("b", "k") == 2


def test_ac10_sorted_listings():
    s = MemoryStore()
    for k in ["z", "a", "m"]:
        s.put("ns", k, 1)
    s.put("zz", "x", 1)
    s.put("aa", "x", 1)
    assert s.list_keys("ns") == ["a", "m", "z"]
    assert s.namespaces() == ["aa", "ns", "zz"]
    assert s.list_keys("unknown") == []


def test_ac11_delete_bool():
    s = MemoryStore()
    s.put("ns", "k", 1)
    assert s.delete("ns", "k") is True
    assert s.delete("ns", "k") is False  # already gone
    assert s.delete("nope", "k") is False  # unknown namespace


def test_ac12_non_json_raises_no_partial_mutation():
    s = MemoryStore()
    before_ns = s.namespaces()
    try:
        s.put("newns", "k", object())  # not JSON-serializable
    except (TypeError, ValueError):
        pass
    else:
        raise AssertionError("expected raise for non-JSON value")
    # no partial mutation: namespace was not created, nothing stored
    assert s.namespaces() == before_ns
    assert "newns" not in s.namespaces()
    assert s.get("newns", "k") is None


def test_ac13_round_trip_and_load_replaces(tmp_path: Path):
    s = MemoryStore()
    s.put("ns1", "a", {"x": 1})
    s.put("ns1", "b", [1, 2, 3])
    s.put("ns2", "c", "hello")
    p = tmp_path / "store.jsonl"
    s.dump(p)

    fresh = MemoryStore()
    fresh.load(p)
    assert fresh.get("ns1", "a") == {"x": 1}
    assert fresh.get("ns1", "b") == [1, 2, 3]
    assert fresh.get("ns2", "c") == "hello"
    assert fresh.namespaces() == ["ns1", "ns2"]

    # load REPLACES non-empty store contents
    dirty = MemoryStore()
    dirty.put("stale", "old", 999)
    dirty.load(p)
    assert dirty.namespaces() == ["ns1", "ns2"]  # "stale" discarded
    assert dirty.get("stale", "old") is None


def test_ac14_no_implicit_io(tmp_path: Path):
    # Operating on the store touches no disk unless dump() is called.
    s = MemoryStore()
    s.put("ns", "k", 1)
    s.get("ns", "k")
    s.list_keys("ns")
    s.delete("ns", "missing")
    # nothing was written anywhere under tmp_path
    assert list(tmp_path.iterdir()) == []


def test_n2_dump_byte_stable(tmp_path: Path):
    s = MemoryStore()
    s.put("b", "y", 2)
    s.put("a", "x", 1)
    p1 = tmp_path / "a.jsonl"
    p2 = tmp_path / "b.jsonl"
    s.dump(p1)
    s.dump(p2)
    assert p1.read_text(encoding="utf-8") == p2.read_text(encoding="utf-8")
    # deterministic sorted order: ns "a" before "b"
    first_line = p1.read_text(encoding="utf-8").splitlines()[0]
    assert '"namespace": "a"' in first_line
