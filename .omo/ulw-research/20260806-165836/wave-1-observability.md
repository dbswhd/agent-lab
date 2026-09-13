# Wave 1 — observability

- `Arize-ai/openinference@8053d84…` is the best portable vocabulary: AGENT/TOOL/GUARDRAIL/EVALUATOR span kinds, parent IDs, human/LLM/code annotations.
- `open-telemetry/semantic-conventions-genai@4a39b6e…` supplies `invoke_agent` and `execute_tool`, but the schema is moving.
- Phoenix and Langfuse are strong storage/eval UIs; OpenLLMetry supplies framework-specific instrumentors.
- None standardizes permission request/decision, Human Inbox, or handoff edges. Agent Lab must retain a canonical superset and emit projections.
- Sources: [OpenInference conventions](https://github.com/Arize-ai/openinference/blob/8053d845d90ae1ad4796c7e2c5eaf807e932f5b4/spec/semantic_conventions.md#L6-L38), [trace parentage](https://github.com/Arize-ai/openinference/blob/8053d845d90ae1ad4796c7e2c5eaf807e932f5b4/spec/traces.md#L9-L71), [OTel GenAI model](https://github.com/open-telemetry/semantic-conventions-genai/blob/4a39b6ef1363fab57bc40e18c82abb32cc89ebcd/reference/src/semconv_genai/semconv_model.py#L164-L195), [Phoenix datasets](https://github.com/Arize-ai/phoenix/blob/a68f232c3a5e328d62e95ac385605e0e6557cbfa/README.md#L48-L53).

## EXPAND
- LEAD: masking/redaction behavior — WHY: tool args can contain secrets — ANGLE: adapter source and defaults.

