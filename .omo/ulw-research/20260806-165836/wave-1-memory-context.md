# Wave 1 — memory/context

- `letta-ai/letta-code@455b13b…`: git-style memory diff history is unusually inspectable and human-editable.
- `getzep/graphiti@425bf24…`: episodic provenance and valid/invalid time are strong contamination controls, but operationally heavy.
- `mem0ai/mem0@3f39fba…`: run/agent/user scopes, expiry, explainable retrieval; OSS lacks some temporal features available in hosted product.
- OpenHands Condenser is the strongest compaction pattern: raw append-only history plus explicit forgotten IDs and summary views.
- Sources: [Letta memory logger](https://github.com/letta-ai/letta-code/blob/455b13bfa127aae80bdca90aeaf793e1dfea9a7b/hooks/memory_logger.py#L1-L17), [Graphiti temporal schema](https://github.com/getzep/graphiti/blob/425bf2481b51437e43455e09d241c5f46e3d95f3/graphiti_core/driver/kuzu_driver.py#L58-L97), [Mem0 add](https://github.com/mem0ai/mem0/blob/3f39fba28f7781aaf581f64a4af39d017af65835/mem0/memory/main.py#L755-L805), [Mem0 search](https://github.com/mem0ai/mem0/blob/3f39fba28f7781aaf581f64a4af39d017af65835/mem0/memory/main.py#L1369-L1415), [OpenHands condenser](https://docs.openhands.dev/sdk/arch/condenser).

## EXPAND
- LEAD: OpenHands Condensation record source/tests — WHY: auditable context compaction — ANGLE: clone.
- LEAD: contamination fixtures — WHY: cross-run leakage and stale summaries — ANGLE: adversarial cases.

