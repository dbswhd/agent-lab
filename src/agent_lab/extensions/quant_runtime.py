"""Lazy import of quant-agentic-trading (quant_pipeline) modules."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

from agent_lab.extensions.quant_trading import optional_agentic_src

_CACHE: dict[str, ModuleType | None] = {}


def load_quant_module(dotted: str) -> ModuleType | None:
    """Import `quant_pipeline.*` when AGENTIC_QUANT_PIPELINE_SRC is available."""
    if dotted in _CACHE:
        return _CACHE[dotted]

    src = optional_agentic_src()
    if src is None:
        _CACHE[dotted] = None
        return None

    src_str = str(src.resolve())
    if src_str not in sys.path:
        sys.path.insert(0, src_str)

    try:
        mod = importlib.import_module(dotted)
    except ImportError:
        _CACHE[dotted] = None
        return None

    _CACHE[dotted] = mod
    return mod


def require_quant_module(dotted: str) -> ModuleType:
    mod = load_quant_module(dotted)
    if mod is None:
        raise RuntimeError(
            f"quant-agentic-trading extension required for {dotted} "
            "(set AGENTIC_QUANT_PIPELINE_SRC)"
        )
    return mod
