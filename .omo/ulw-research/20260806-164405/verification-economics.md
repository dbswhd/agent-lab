# Verification economics

| claim | risk | error cost | verification cost/time | path | decision | outcome | residual risk |
|---|---|---|---|---|---|---|---|
| recent feature availability | medium | stale recommendation | low | official docs/changelog + repo | verify | confirmed through 2026-08-06 | specs may continue changing |
| Agent Lab overlap | medium | duplicate roadmap | low | local SSOT/code trace | verify | current shipped/frozen matrix checked | docs may lag code |
| MCP breaking impact | high | runtime/plugin regression | medium | spec + SDK + dependency/runtime inspection | verify | v1 deliberately pinned; immediate auto-break avoided | v2 migration untested |
| ACP cutover | medium | adapter churn | medium | spec/changelog/RFD + current adapters | defer cutover, prototype only | v1 stable, v2/remote transport moving | adoption compatibility varies |
| exact vendor performance numbers | high | misleading prioritization | high | independent replication unavailable | abstain | omitted except clearly attributed paper claims | vendor/paper bias |
