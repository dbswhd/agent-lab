"""Render Trading Mission topic from template."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

_KST = timezone(timedelta(hours=9))
_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "trading-mission" / "topic_template.md"
)


def _default_max_proposals() -> int:
    import os

    raw = (os.getenv("AGENT_LAB_TRADING_MAX_PROPOSALS") or "5").strip()
    try:
        return max(0, min(int(raw), 20))
    except ValueError:
        return 5


def render_premarket_topic(
    *,
    date_kst: datetime | None = None,
    max_proposals: int | None = None,
    template_path: Path | None = None,
) -> str:
    when = date_kst or datetime.now(_KST)
    cap = max_proposals if max_proposals is not None else _default_max_proposals()
    path = template_path or _TEMPLATE_PATH
    if not path.is_file():
        raise FileNotFoundError(f"topic template not found: {path}")
    text = path.read_text(encoding="utf-8")
    return (
        text.replace("{{DATE_KST}}", when.strftime("%Y-%m-%d"))
        .replace("{{MAX_PROPOSALS}}", str(cap))
        .strip()
        + "\n"
    )


def mission_id_from_date(date_kst: datetime | None = None) -> str:
    when = date_kst or datetime.now(_KST)
    return f"{when.strftime('%Y-%m-%d')}-premarket"


def mission_id_weekly(date_kst: datetime | None = None) -> str:
    when = date_kst or datetime.now(_KST)
    return f"{when.strftime('%Y-%m-%d')}-weekly"


_OFFLINE_TEMPLATE = (
    Path(__file__).resolve().parents[3] / "docs" / "trading-mission" / "offline_topic_template.md"
)


def render_offline_topic(
    *,
    date_kst: datetime | None = None,
    template_path: Path | None = None,
) -> str:
    when = date_kst or datetime.now(_KST)
    path = template_path or _OFFLINE_TEMPLATE
    if not path.is_file():
        raise FileNotFoundError(f"offline topic template not found: {path}")
    text = path.read_text(encoding="utf-8")
    return text.replace("{{DATE_KST}}", when.strftime("%Y-%m-%d")).strip() + "\n"


def session_slug_from_topic(topic: str) -> str:
    first = topic.strip().splitlines()[0] if topic.strip() else "trading-mission"
    slug = re.sub(r"[^\w가-힣]+", "-", first.lower())[:80].strip("-")
    return slug or "trading-mission"
