"""Backward-compatible shim — implementation: scripts.soak.live_telegram_merge_soak."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

_impl = importlib.import_module("scripts.soak.live_telegram_merge_soak")
globals().update({k: getattr(_impl, k) for k in dir(_impl) if not k.startswith("__")})
