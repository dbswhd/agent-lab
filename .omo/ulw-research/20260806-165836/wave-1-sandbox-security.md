# Wave 1 — sandbox/security

- `SWE-agent/swe-rex@5c995c3…` is the best small adapter reference: local Docker/Fargate/Modal lifecycle and timeouts, but it delegates credential/audit/snapshot policy to backends.
- Firecracker and gVisor are isolation primitives rather than an Agent Lab-ready runtime. Hosted E2B/Modal/Vercel have strong lifecycle/policy features but control-plane lock-in.
- Daytona OSS is explicitly unmaintained since June 2026 despite a broad feature surface; reject as a new dependency.
- Sources: [Daytona notice](https://github.com/daytonaio/daytona/blob/ec4c21b2d597091ac09ecc278f3bcc172575a987/README.md#L0-L6), [Firecracker isolation](https://github.com/firecracker-microvm/firecracker/blob/a4fe7dc66bb60fc3c652162431197d17641778d/README.md#L124-L135), [gVisor caveats](https://github.com/google/gvisor/blob/deb31f1879845872e8b01d9f5805fdae47c113a0/SECURITY.md#L80-L83), [SWE-ReX](https://github.com/SWE-agent/swe-rex/blob/5c995c365dfb1fd5bc56fda688be5d8538f9931f/README.md), [Vercel Sandbox skill](https://github.com/vercel/sandbox/blob/761032050d6238aa492addecd6dc90ce5b696b1f/skills/sandbox/SKILL.md#L113-L143).

## EXPAND
- LEAD: self-hosted OpenSandbox/Agent Sandbox — WHY: hosted lock-in alternative — ANGLE: enforcement and cleanup API.
- LEAD: TOCTOU trusted-host boundary — WHY: agent-written config can escape VM policy — ANGLE: handoff and repo hook counter-search.

