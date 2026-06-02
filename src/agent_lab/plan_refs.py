"""Validate plan.md provenance refs against chat.jsonl line count."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

REF_PATTERN = re.compile(r"\(ref:\s*chat\.jsonl#L(\d+)\)", re.IGNORECASE)
REF_BLOCK_PATTERN = re.compile(r"\(ref:\s*([^)]+)\)", re.IGNORECASE)
LINE_NUM_PATTERN = re.compile(r"L(\d+)", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9가-힣]{2,}")

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "that",
        "this",
        "for",
        "with",
        "from",
        "are",
        "was",
        "were",
        "have",
        "has",
        "had",
        "not",
        "but",
        "can",
        "will",
        "you",
        "your",
        "our",
        "ref",
        "chat",
        "jsonl",
        "plan",
        "md",
        "이",
        "가",
        "은",
        "는",
        "을",
        "를",
        "에",
        "의",
        "로",
        "과",
        "와",
        "도",
        "만",
        "등",
        "및",
        "또",
        "것",
        "수",
    }
)


@dataclass
class PlanRefValidation:
    valid: bool
    chat_line_count: int
    refs: list[int] = field(default_factory=list)
    invalid_refs: list[int] = field(default_factory=list)
    has_unclear: bool = False

    def summary(self) -> str:
        if self.valid:
            return (
                f"OK: {len(self.refs)} ref(s), all within chat.jsonl "
                f"(1..{self.chat_line_count})"
            )
        bad = ", ".join(f"L{n}" for n in self.invalid_refs)
        return (
            f"FAIL: {len(self.invalid_refs)} ref(s) out of range "
            f"(chat.jsonl has {self.chat_line_count} lines): {bad}"
        )


def count_chat_lines(chat_path: Path) -> int:
    if not chat_path.is_file():
        return 0
    return sum(
        1 for line in chat_path.read_text(encoding="utf-8").splitlines() if line.strip()
    )


def extract_plan_refs(plan_md: str) -> list[int]:
    return [int(m.group(1)) for m in REF_PATTERN.finditer(plan_md)]


def extract_ref_line_numbers(ref_block: str) -> list[int]:
    return [int(m.group(1)) for m in LINE_NUM_PATTERN.finditer(ref_block)]


def _strip_refs(text: str) -> str:
    return REF_BLOCK_PATTERN.sub("", text)


def tokenize_for_overlap(text: str) -> set[str]:
    cleaned = _strip_refs(text)
    cleaned = re.sub(r"[*`#|]", " ", cleaned)
    tokens = {
        t.lower()
        for t in TOKEN_PATTERN.findall(cleaned)
        if t.lower() not in _STOPWORDS
    }
    return tokens


def overlap_score(plan_tokens: set[str], ref_tokens: set[str]) -> tuple[int, float]:
    if not plan_tokens or not ref_tokens:
        return 0, 0.0
    shared = plan_tokens & ref_tokens
    score = len(shared) / min(len(plan_tokens), len(ref_tokens))
    return len(shared), score


def is_suspicious_ref_overlap(plan_tokens: set[str], ref_tokens: set[str]) -> bool:
    """Conservative heuristic — informational only."""
    if len(plan_tokens) < 4:
        return False
    shared, score = overlap_score(plan_tokens, ref_tokens)
    if shared >= 2:
        return False
    if shared == 1 and score >= 0.08:
        return False
    if shared == 0:
        return True
    return score < 0.06


@dataclass
class PlanRefMeaningWarning:
    plan_line: int
    snippet: str
    refs: list[int]
    shared_count: int
    overlap_score: float


@dataclass
class PlanRefMeaningValidation:
    warnings: list[PlanRefMeaningWarning] = field(default_factory=list)
    total_ref_items: int = 0

    def summary(self) -> str:
        if not self.warnings:
            return f"OK: {self.total_ref_items} ref item(s), no low-overlap warnings"
        lines = ", ".join(
            f"plan L{w.plan_line} → chat L{','.join(str(r) for r in w.refs)}"
            for w in self.warnings[:5]
        )
        extra = f" (+{len(self.warnings) - 5} more)" if len(self.warnings) > 5 else ""
        return f"WARN: {len(self.warnings)} low-overlap ref item(s): {lines}{extra}"


def load_chat_contents(chat_path: Path) -> list[str]:
    if not chat_path.is_file():
        return []
    contents: list[str] = []
    for line in chat_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            contents.append(str(obj.get("content", "")))
        except json.JSONDecodeError:
            contents.append(line)
    return contents


def validate_plan_ref_meaning(session_folder: Path) -> PlanRefMeaningValidation:
    """Flag plan items whose refs have very low keyword overlap (informational)."""
    plan_path = session_folder / "plan.md"
    chat_path = session_folder / "chat.jsonl"
    if not plan_path.is_file():
        return PlanRefMeaningValidation()
    chat_contents = load_chat_contents(chat_path)
    if not chat_contents:
        return PlanRefMeaningValidation()

    warnings: list[PlanRefMeaningWarning] = []
    total = 0
    for i, line in enumerate(plan_path.read_text(encoding="utf-8").splitlines(), start=1):
        if "(ref:" not in line.lower() or "(ref: 불명확)" in line:
            continue
        plan_tokens = tokenize_for_overlap(line)
        if not plan_tokens:
            continue
        refs: list[int] = []
        for m in REF_BLOCK_PATTERN.finditer(line):
            refs.extend(extract_ref_line_numbers(m.group(1)))
        if not refs:
            continue
        total += 1
        ref_text = "\n".join(
            chat_contents[n - 1]
            for n in refs
            if 1 <= n <= len(chat_contents)
        )
        ref_tokens = tokenize_for_overlap(ref_text)
        shared, score = overlap_score(plan_tokens, ref_tokens)
        if is_suspicious_ref_overlap(plan_tokens, ref_tokens):
            snippet = _strip_refs(line).strip()
            if len(snippet) > 72:
                snippet = snippet[:71] + "…"
            warnings.append(
                PlanRefMeaningWarning(
                    plan_line=i,
                    snippet=snippet,
                    refs=sorted(set(refs)),
                    shared_count=shared,
                    overlap_score=round(score, 3),
                )
            )
    return PlanRefMeaningValidation(warnings=warnings, total_ref_items=total)


def validate_plan_refs(session_folder: Path) -> PlanRefValidation:
    """Check that plan.md L refs point to existing chat.jsonl lines."""
    plan_path = session_folder / "plan.md"
    chat_path = session_folder / "chat.jsonl"
    if not plan_path.is_file():
        return PlanRefValidation(valid=False, chat_line_count=0, invalid_refs=[])
    plan_md = plan_path.read_text(encoding="utf-8")
    line_count = count_chat_lines(chat_path)
    refs = extract_plan_refs(plan_md)
    invalid = [n for n in refs if n < 1 or n > line_count]
    has_unclear = "(ref: 불명확)" in plan_md
    return PlanRefValidation(
        valid=len(invalid) == 0,
        chat_line_count=line_count,
        refs=refs,
        invalid_refs=invalid,
        has_unclear=has_unclear,
    )
