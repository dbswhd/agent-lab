# Wave 2 — AX vs Chidori

- AX enforces a single writer and transactional step append, but `Exec` still contains a resume TODO. It is architecture inspiration only.
- Chidori refuses export of leased active runs, snapshot-checks source drift, persists calls, detects replay divergence, and models Running/Cancelled/Paused/AwaitingApproval with pending signal state.
- Chidori is the better observation candidate; distributed exactly-once remains unproven and external effects still need idempotency keys.
- Sources: [AX single writer](https://github.com/google/ax/blob/f327e23b5b842e9b700675ded9a6cdb79c505856/internal/controller/controller.go#L32-L37), [AX resume TODO](https://github.com/google/ax/blob/f327e23b5b842e9b700675ded9a6cdb79c505856/internal/controller/controller.go#L64-L74), [Chidori export fencing](https://github.com/ThousandBirdsInc/chidori/blob/4bd624028cda6026b7040e57d94dc9c70096f46d/crates/chidori/src/export.rs#L45-L73), [stored states](https://github.com/ThousandBirdsInc/chidori/blob/4bd624028cda6026b7040e57d94dc9c70096f46d/crates/chidori/src/storage.rs#L25-L72).

## EXPAND
- DEAD END: AX shortlist until resume TODO and conformance tests land.

