# Wave 1 — eval frameworks

- `UKGovernmentBEIS/inspect_ai@a752313…`: first-class async human approver and per-sample sandbox make it a strong Dialogue Room Bench reference.
- `harbor-framework/harbor@4698544…`: canonical `trajectory.json`, verifier reward dictionaries, resumable artifact upload/fallback.
- `SWE-bench@f7bbbb2…`: deterministic TestSpec container, timeouts, runtime and output artifacts.
- Inspect + Harbor + SWE-bench compose better than adopting one entire engine.
- Sources: [Inspect human approver](https://github.com/UKGovernmentBEIS/inspect_ai/blob/a7523133367edde0ea2859a271b36a40de77f948/src/inspect_ai/approval/_human/approver.py#L13-L57), [Inspect sandbox](https://github.com/UKGovernmentBEIS/inspect_ai/blob/a7523133367edde0ea2859a271b36a40de77f948/src/inspect_ai/util/_sandbox/environment.py#L46-L97), [Harbor trajectory upload](https://github.com/harbor-framework/harbor/blob/4698544ea9d5ee95d01b05aeaa9ccbd161d5a7f6/src/harbor/upload/uploader.py#L530-L558), [SWE-bench timeout](https://github.com/SWE-bench/SWE-bench/blob/f7bbbb2ccdf479001d6467c9e34af59e44a840f9/swebench/harness/run_evaluation.py#L205-L219).

## EXPAND
- LEAD: Harbor resource policy schema — WHY: separate infra failure from agent score — ANGLE: source audit.
- LEAD: tau2-bench fixtures — WHY: API/human dialogue correctness — ANGLE: task/policy scorer contract.

