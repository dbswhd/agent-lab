# Wave 1 — permissions/policy

- `openai/codex@7a0e974…`: explicit approval/sandbox/network/additional-directory capability surface and CLI translation.
- Older Go `opencode-ai/opencode@73ee493…`: permission request blocks on response and scopes grants to session/tool/action/path, but print mode auto-approves.
- OPA is a possible external policy decision point; it must advise or deny, never replace Human Inbox authority.
- High-risk anti-patterns: `danger-full-access + never`, `--yolo`, broad session grants, repository-defined hooks, shell compound-command pattern bypass, inherited secrets plus egress.
- Sources: [Codex capability types](https://github.com/openai/codex/blob/7a0e974e08c798d1e8d59d407aeb6e24db1313af/sdk/typescript/src/threadOptions.ts#L1-L20), [Codex CLI translation](https://github.com/openai/codex/blob/7a0e974e08c798d1e8d59d407aeb6e24db1313af/sdk/typescript/src/exec.ts#L102-L149), [OpenCode permission wait](https://github.com/opencode-ai/opencode/blob/73ee493265acf15fcd8caab2bc8cd3bd375b63cb/internal/permission/permission.go#L74-L108), [OPA](https://github.com/open-policy-agent/opa/tree/af3678f6cf90672bae2e85273d4bb5cac5330d7d).

## EXPAND
- LEAD: content-addressed approval receipt — WHY: prevent command/arg TOCTOU — ANGLE: comparable implementations and schema.

