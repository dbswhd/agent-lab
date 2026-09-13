# Wave 2 — Microsoft Agent Framework

- Workflow resume accepts checkpoint storage/id + response map, validates graph fingerprint, guards concurrent runs and pending requests.
- Checkpoints occur by superstep; mid-superstep effects can replay. Restore resumes scheduler, which conflicts with Agent Lab's restore-then-stop invariant.
- Approval is real tool middleware but auto-approval/disable flags can bypass it. Borrow request IDs, response map, graph fingerprint and approval result shape; do not import scheduler or authority.
- Sources: [workflow run/restore](https://github.com/microsoft/agent-framework/blob/74a144085a5fd05921b473001528f3ae0725b76a/python/packages/core/agent_framework/_workflows/_workflow.py#L625-L757), [approval mode](https://github.com/microsoft/agent-framework/blob/74a144085a5fd05921b473001528f3ae0725b76a/python/packages/core/agent_framework/_agents.py#L568-L585), [auto-approval rules](https://github.com/microsoft/agent-framework/blob/74a144085a5fd05921b473001528f3ae0725b76a/python/packages/core/agent_framework/_skills.py#L2095-L2125).

## EXPAND
- DEAD END: framework replacement; conflicts with restore-then-stop and Room consensus authority.

