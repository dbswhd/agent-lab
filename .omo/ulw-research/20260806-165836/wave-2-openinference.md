# Wave 2 — OpenInference projection

- `session.id`, agent/tool span kinds and evaluation annotations are portable. Permission/HITL/handoff remain custom Agent Lab events.
- All masking defaults are false: without explicit config, prompts/tool args/results may be exported. Redaction is opt-out, not privacy-by-default.
- Safe projection should export IDs, hashes, policy/schema version and status; never raw approval text/tool args by default. Pin both mapping version and OTel schema URL.
- Sources: [masking configuration](https://github.com/Arize-ai/openinference/blob/8053d845d90ae1ad4796c7e2c5eaf807e932f5b4/spec/configuration.md#L7-L100), [Python config](https://github.com/Arize-ai/openinference/blob/8053d845d90ae1ad4796c7e2c5eaf807e932f5b4/python/openinference-instrumentation/src/openinference/instrumentation/config.py#L40-L145), [semantic fields](https://github.com/Arize-ai/openinference/blob/8053d845d90ae1ad4796c7e2c5eaf807e932f5b4/spec/semantic_conventions.md#L23-L57).

## EXPAND
- DEAD END: OpenInference as event SSOT; portability and authorization semantics are insufficient.

