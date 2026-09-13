# Wave 2 — self-hosted sandbox

- Canonical repository redirects to `opensandbox-group/OpenSandbox@47d85df…`; active, Apache-2.0.
- Unified lifecycle plus Docker/Kubernetes, egress policy, Credential Vault and optional gVisor/Kata/Firecracker make it stronger than SWE-ReX for policy/credential mediation.
- Credential Vault keeps real credentials in egress sidecar and injects scoped headers only for allowed HTTPS. DNS-only/default-allow are explicitly unsafe; service-mesh conflicts and cleanup/snapshot gaps remain.
- Use as a self-hosted control-layer reference, paired with an isolation primitive; do not assume Docker alone is hostile multi-tenant isolation.
- Sources: [OpenSandbox README](https://github.com/opensandbox-group/OpenSandbox/blob/47d85df848f957f5e7b3231e435ef9333a57537c/README.md), [security policy](https://github.com/opensandbox-group/OpenSandbox/blob/47d85df848f957f5e7b3231e435ef9333a57537c/SECURITY.md), [Credential Vault](https://github.com/opensandbox-group/OpenSandbox/blob/47d85df848f957f5e7b3231e435ef9333a57537c/docs/guides/credential-vault.md).

## EXPAND
- DEAD END: weaker Docker-only orchestration alternatives; insufficient isolation/policy evidence.

