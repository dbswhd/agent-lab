# Wave 1 — workflow graphs

- `dagworks-inc/burr@a05875f…`: immutable State, typed reads/writes, serializable StateDelta, explicit transitions and visualization. Best small semantic reference.
- Dify provides durable human-input form/channel policy but is a large product runtime.
- Mastra has useful typed suspend/resume; source-level proof remained weaker in Wave 1.
- DBOS/Hatchet/Temporal/Prefect provide durable infrastructure, not Agent Lab's agent semantics.
- Sources: [Burr StateDelta](https://github.com/dagworks-inc/burr/blob/a05875f09687b958bd83a5767be25d37821bee83/burr/core/state.py#L71-L120), [Dify workflow entry](https://github.com/langgenius/dify/blob/06d8301a905da655a4e42b380330f023ca227d79/api/core/workflow/workflow_entry.py#L60-L126), [Dify human input runtime](https://github.com/langgenius/dify/blob/06d8301a905da655a4e42b380330f023ca227d79/api/core/workflow/node_runtime.py#L769-L825), [DBOS management](https://github.com/dbos-inc/dbos-transact-ts/blob/dfd600cc48537a69f3d57d28108a781bfb82c988/src/workflow_management.ts#L18-L70).

## EXPAND
- LEAD: Burr action/state tests — WHY: low-cost pattern absorption — ANGLE: clone and exercise.

