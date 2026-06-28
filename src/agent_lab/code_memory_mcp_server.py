"""stdio MCP server for local code-memory search (Phase 0 pilot)."""

from __future__ import annotations

import ast
import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from mcp.server.fastmcp import FastMCP
from agent_lab.workspace.roots import project_root

mcp = FastMCP("agent-lab-code-memory")
_TRUE = {"1", "true", "yes", "on"}
_MODES = {"mock", "index"}
_TOKEN_RE = re.compile(r"[\w가-힣]+", re.UNICODE)
_INDEX_REVISION = "code-memory-phase0-v1"
_SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".mjs",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class _Fingerprint:
    mtime_ns: int
    size: int


@dataclass(frozen=True)
class _Chunk:
    path: str
    start_line: int
    end_line: int
    text: str
    kind: str
    symbol: str | None
    fingerprint: _Fingerprint


@dataclass(frozen=True)
class _Index:
    root: Path
    repo_rev: str | None
    built_at: str
    index_revision: str
    chunks: tuple[_Chunk, ...]
    file_count: int
    last_error: str | None = None


_INDEX_CACHE: dict[Path, _Index] = {}


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in _TRUE


def code_memory_mcp_enabled() -> bool:
    return _env_bool("AGENT_LAB_CODE_MEMORY_MCP", default=False)


def code_memory_mode() -> str:
    raw = (os.getenv("AGENT_LAB_CODE_MEMORY_MODE") or "").strip().lower()
    return raw if raw in _MODES else "mock"


def code_memory_cache_signature() -> tuple[bool, str]:
    return (code_memory_mcp_enabled(), code_memory_mode())


def _mode(mode: str | None) -> str:
    raw = (mode if mode is not None else code_memory_mode()).strip().lower()
    return raw if raw in _MODES else "mock"


def _now_iso() -> str:
    if os.getenv("AGENT_LAB_MOCK_AGENTS"):
        return "2026-01-01T00:00:00+00:00"
    return datetime.now(timezone.utc).isoformat()


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text) if len(t) >= 2}


def _snippet(text: str, *, query_terms: set[str], max_chars: int = 400) -> str:
    compact = " ".join(text.split())
    if not compact:
        return ""
    lower = compact.lower()
    best = -1
    for term in sorted(query_terms, key=lambda x: (-len(x), x)):
        pos = lower.find(term)
        if pos >= 0 and (best < 0 or pos < best):
            best = pos
    if best < 0:
        return compact[:max_chars] + ("…" if len(compact) > max_chars else "")
    start = max(0, best - 80)
    out = compact[start : start + max_chars]
    return ("…" if start > 0 else "") + out + ("…" if start + max_chars < len(compact) else "")


def _repo_rev(root: Path) -> str | None:
    try:
        p = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(root), check=False, capture_output=True, text=True, timeout=2
        )
    except Exception:
        return None
    return p.stdout.strip() or None if p.returncode == 0 else None


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _source_like(path: Path) -> bool:
    return path.suffix.lower() in _SOURCE_SUFFIXES or path.name in {"Dockerfile", "Makefile"}


def _read_text(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _source_files(root: Path) -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        cur = Path(dirpath)
        dirnames[:] = sorted(n for n in dirnames if not n.startswith(".") and n != ".git")
        for name in sorted(filenames):
            p = cur / name
            if any(part.startswith(".") or part == ".git" for part in p.relative_to(root).parts):
                continue
            if _source_like(p):
                out.append(p)
    return sorted(out, key=lambda p: _rel(root, p))


def _line_chunks(rel: str, text: str, fp: _Fingerprint) -> list[_Chunk]:
    lines = text.splitlines()
    out = []
    for start in range(0, len(lines), 24):
        end = min(len(lines), start + 24)
        body = "\n".join(lines[start:end])
        if body.strip():
            out.append(_Chunk(rel, start + 1, end, body, "text", None, fp))
    return out


def _ast_chunks(rel: str, text: str, fp: _Fingerprint) -> list[_Chunk]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines()
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            start = int(getattr(node, "lineno", 1))
            end = int(getattr(node, "end_lineno", start))
            if start >= 1 and end >= start:
                body = "\n".join(lines[start - 1 : end])
                if body.strip():
                    out.append(_Chunk(rel, start, end, body, "ast", str(node.name), fp))
    return sorted(out, key=lambda c: (c.start_line, c.end_line, c.symbol or ""))


def _build_index(root: Path) -> _Index:
    root = root.expanduser().resolve()
    chunks = []
    file_count = 0
    last_error = None
    try:
        for path in _source_files(root):
            text = _read_text(path)
            if text is None:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            file_count += 1
            rel = _rel(root, path)
            fp = _Fingerprint(stat.st_mtime_ns, stat.st_size)
            if path.suffix.lower() == ".py":
                chunks.extend(_ast_chunks(rel, text, fp))
            chunks.extend(_line_chunks(rel, text, fp))
    except Exception as exc:
        last_error = str(exc)
    return _Index(root, _repo_rev(root), _now_iso(), _INDEX_REVISION, tuple(chunks), file_count, last_error)


def _load_index(root: Path) -> _Index:
    root = root.expanduser().resolve()
    idx = _INDEX_CACHE.get(root)
    if idx is None:
        idx = _INDEX_CACHE[root] = _build_index(root)
    return idx


def _index_meta(root: Path, index: _Index | None = None, *, fresh: bool = True) -> dict[str, Any]:
    if index is None:
        return {
            "root": str(root.expanduser().resolve()),
            "repo_rev": None,
            "built_at": "mock",
            "index_revision": _INDEX_REVISION,
            "fresh": fresh,
        }
    return {
        "root": str(index.root),
        "repo_rev": index.repo_rev,
        "built_at": index.built_at,
        "index_revision": index.index_revision,
        "fresh": fresh,
    }


def _score(text: str, query: str, terms: set[str]) -> float:
    lower = text.lower()
    q = query.strip().lower()
    score = float(len(terms & _tokenize(text)) * 10)
    for term in terms:
        score += float(lower.count(term))
    if q:
        score += float(lower.count(q) * 5)
    return score


def _hit(c: _Chunk, *, score: float, snippet: str) -> dict[str, Any]:
    return {
        "path": c.path,
        "start_line": c.start_line,
        "end_line": c.end_line,
        "source_ref": f"{c.path}:{c.start_line}-{c.end_line}",
        "snippet": snippet,
        "score": score,
        "kind": c.kind,
        "symbol": c.symbol,
        "file_mtime_ns": c.fingerprint.mtime_ns,
        "fresh": True,
    }


def _mock_hits(query: str, k: int) -> list[dict[str, Any]]:
    terms = sorted(_tokenize(query)) or ["query"]
    count = max(0, min(int(k or 0), 5))
    out = []
    for i in range(count):
        path = f"mock/code_memory_{i + 1}.py"
        line = i + 1
        snip = _snippet(
            f"Mock code-memory hit {i + 1} for {query!r} using term {terms[i % len(terms)]}.", query_terms=set(terms)
        )
        out.append(
            {
                "path": path,
                "start_line": line,
                "end_line": line,
                "source_ref": f"{path}:{line}-{line}",
                "snippet": snip,
                "score": float(count - i),
                "kind": "mock",
                "symbol": None,
                "file_mtime_ns": 0,
                "fresh": True,
            }
        )
    return out


def code_memory_search_payload(
    root: Path, query: str, k: int = 5, path_glob: str | None = None, mode: str | None = None
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    active = _mode(mode)
    enabled = code_memory_mcp_enabled()
    limit = max(0, min(int(k or 0), 50))
    query = str(query or "")
    if not enabled:
        return {
            "ok": True,
            "enabled": False,
            "mode": active,
            "query": query,
            "hit_count": 0,
            "stale_hit_count": 0,
            "hits": [],
            "index": _index_meta(root),
        }
    if active == "mock":
        hits = _mock_hits(query, limit)
        return {
            "ok": True,
            "enabled": True,
            "mode": "mock",
            "query": query,
            "hit_count": len(hits),
            "stale_hit_count": 0,
            "hits": hits,
            "index": _index_meta(root),
        }
    index = _load_index(root)
    terms = _tokenize(query)
    candidates = []
    for c in index.chunks:
        if path_glob and not fnmatch.fnmatch(c.path, path_glob):
            continue
        score = _score(c.text, query, terms)
        if score > 0:
            candidates.append((score, c, _snippet(c.text, query_terms=terms)))
    candidates.sort(
        key=lambda r: (-r[0], r[1].path, r[1].start_line, r[1].end_line, r[1].symbol is None, r[1].symbol or "")
    )
    hits = []
    stale = 0
    for score, c, snip in candidates:
        try:
            stat = (root / c.path).stat()
        except OSError:
            stale += 1
            continue
        if stat.st_mtime_ns != c.fingerprint.mtime_ns or stat.st_size != c.fingerprint.size:
            stale += 1
            continue
        hits.append(_hit(c, score=score, snippet=snip))
        if len(hits) >= limit:
            break
    return {
        "ok": True,
        "enabled": True,
        "mode": "index",
        "query": query,
        "hit_count": len(hits),
        "stale_hit_count": stale,
        "hits": hits,
        "index": _index_meta(root, index, fresh=stale == 0),
    }


def code_memory_status_payload(root: Path, mode: str | None = None) -> dict[str, Any]:
    root = root.expanduser().resolve()
    active = _mode(mode)
    enabled = code_memory_mcp_enabled()
    if not enabled or active == "mock":
        return {
            "ok": True,
            "enabled": enabled,
            "mode": active,
            "root": str(root),
            "repo_rev": None,
            "built_at": None,
            "index_revision": None,
            "file_count": 0,
            "chunk_count": 0,
            "fresh": True,
            "last_error": None,
        }
    index = _load_index(root)
    return {
        "ok": True,
        "enabled": enabled,
        "mode": "index",
        "root": str(index.root),
        "repo_rev": index.repo_rev,
        "built_at": index.built_at,
        "index_revision": index.index_revision,
        "file_count": index.file_count,
        "chunk_count": len(index.chunks),
        "fresh": True,
        "last_error": index.last_error,
    }


def _code_memory_root() -> Path:
    raw = (os.getenv("AGENT_LAB_CODE_MEMORY_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    raw = (os.getenv("AGENT_LAB_SESSION_WORKSPACE") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return project_root().resolve()


@mcp.tool()
def code_memory_search(query: str, k: int = 5, path_glob: str | None = None) -> dict[str, Any]:
    return code_memory_search_payload(_code_memory_root(), query=str(query or ""), k=k, path_glob=path_glob)


@mcp.tool()
def code_memory_status() -> dict[str, Any]:
    return code_memory_status_payload(_code_memory_root())


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
