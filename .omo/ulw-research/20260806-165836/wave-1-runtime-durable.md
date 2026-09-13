# Wave 1 — durable runtime

- `google/ax@f327e23…`: append-only EventLog and controller replay/resume are agent-native; early redesign and contribution pause are adoption risks.
- `ThousandBirdsInc/chidori@4bd6240…`: strict journal durability, replay-divergence checks, parked VM resume; Rust/JS-VM integration cost is high.
- `restatedev/restate@933e091…`, `hatchet-dev/hatchet@2f65bd9…`: production-grade pause/journal/wait primitives but generic workflow infrastructure.
- `Netflix/conductor@548f386…`: stale reference only.
- Sources: [AX event log](https://github.com/google/ax/blob/f327e23b5b842e9b700675ded9a6cdb79c505856/internal/controller/eventlog/eventlog.go#L28-L33), [Chidori host core](https://github.com/ThousandBirdsInc/chidori/blob/4bd624028cda6026b7040e57d94dc9c70096f46d/crates/chidori/src/runtime/host_core.rs#L150-L172), [Restate journal](https://github.com/restatedev/restate/blob/933e0918579f5b44c696f9fb7a762246781f207b/crates/types/src/journal/entries.rs#L1-L120), [Hatchet durable listener](https://github.com/hatchet-dev/hatchet/blob/2f65bd931f5a6fa46285db250baaeab6d7a351e6/pkg/client/durable_listener.go#L1-L180).

## EXPAND
- LEAD: AX single-writer/fork semantics — WHY: compare with turn-end replay — ANGLE: tests and controller invariants.
- LEAD: Chidori pause/signal/replay — WHY: maps to Human Inbox — ANGLE: HTTP and replay tests.

