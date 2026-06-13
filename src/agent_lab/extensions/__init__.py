"""Optional integrations — agent-lab core must run without these."""

from agent_lab.extensions.quant_trading import (
    agentic_trading_available,
    extension_unavailable,
    optional_agentic_db,
    optional_agentic_src,
    optional_pipeline_root,
    quant_pipeline_available,
    require_agentic_src,
    require_pipeline_root,
)

__all__ = [
    "agentic_trading_available",
    "extension_unavailable",
    "optional_agentic_db",
    "optional_agentic_src",
    "optional_pipeline_root",
    "quant_pipeline_available",
    "require_agentic_src",
    "require_pipeline_root",
]
