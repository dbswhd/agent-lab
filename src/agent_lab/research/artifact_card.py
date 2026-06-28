"""ResearchArtifactCard — delegates to quant-agentic-trading card_builder (SSoT)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from agent_lab.extensions.quant_runtime import require_quant_module

_CARD_BUILDER = "quant_pipeline.agentic_trading.card_builder"


def _builder() -> Any:
    return require_quant_module(_CARD_BUILDER)


def build_card_from_full_json(
    path: Path,
    pipeline_root: Path | None = None,
    *,
    built_at: str | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _builder().build_card_from_full_json(path, pipeline_root, built_at=built_at),
    )


def write_card_cache(cards_dir: Path, card: dict[str, Any]) -> Path:
    return cast(Path, _builder().write_card_cache(cards_dir, card))


def slug_from_full_path(path: Path) -> str:
    return cast(str, _builder().slug_from_full_path(path))


def __getattr__(name: str) -> Any:
    if name == "CARD_MAX_BYTES":
        return _builder().CARD_MAX_BYTES
    raise AttributeError(name)
