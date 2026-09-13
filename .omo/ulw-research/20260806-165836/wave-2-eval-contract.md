# Wave 2 — Inspect + Harbor

- Inspect `ActiveSample` tracks message/token/cost/time/working limits, transcript, sandboxes, counters, retries and limit errors. `EvalSample` separates typed events/attachments, scores, usage, timing and errors.
- Inspect approval manager is in-memory/ACP; durable decision record is missing.
- Harbor preserves verifier reward even when artifact upload fails, so agent score and infrastructure error are orthogonal. Missing reward file is explicit verifier error.
- Recommended fixtures: approval replay; exact-limit/+1 boundary; seeded sandbox artifact hash; reward txt/json/missing; upload outage retaining reward.
- Sources: [Inspect ActiveSample](https://github.com/UKGovernmentBEIS/inspect_ai/blob/a7523133367edde0ea2859a271b36a40de77f948/src/inspect_ai/log/_samples.py#L101-L185), [EvalSample](https://github.com/UKGovernmentBEIS/inspect_ai/blob/a7523133367edde0ea2859a271b36a40de77f948/src/inspect_ai/log/_log.py#L395-L517), [Harbor upload error](https://github.com/harbor-framework/harbor/blob/4698544ea9d5ee95d01b05aeaa9ccbd161d5a7f6/src/harbor/upload/uploader.py#L715-L728), [verifier parse](https://github.com/harbor-framework/harbor/blob/4698544ea9d5ee95d01b05aeaa9ccbd161d5a7f6/src/harbor/verifier/verifier.py#L227-L238).

## EXPAND
- DEAD END: single-framework adoption. Composition is stronger and preserves Agent Lab SSOT.

