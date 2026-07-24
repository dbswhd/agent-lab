# Dogfood readiness packet

`make dogfood-readiness-report MANIFEST=<json> OUT_DIR=<dir>` creates a
read-only readiness packet. It never changes flags, cohorts, defaults, or
documentation status.

The manifest must keep three evidence tiers separate:

- `mock`: deterministic regression or scripted dogfood artifacts.
- `browser`: a real browser run; mocked API routes remain browser evidence,
  not live evidence.
- `live`: credentialed agents and services with their raw session artifacts.

Every `PASS` evidence row must name an existing raw artifact. `OPEN` and
`deferred` rows instead require an owner and next gate. The packet reports:
Oracle coverage, false-success count, repair attempts, retry-cap plateaus,
gate latency, cohort/non-cohort success-rate gap, flags, cohort IDs, sample
window, commit SHA, and raw paths.

A `live` `PASS` must point to the exact live `sessions[].run_path` records it
counts. Each run must identify that session and the manifest commit SHA, and
its non-mock Oracle `PASS` must contain both `evidence[]` and
`checked_paths[]`. The declared live sample size must equal the number of
validated live runs. Any Oracle `PASS` missing either proof field is a
false-success and keeps readiness `OPEN`; `false_success_max` cannot override
that safety gate.

At least one final Oracle PASS session and one Oracle FAIL→repair→PASS session
are required. Overall readiness remains `OPEN` unless all evidence tiers and
operational gates pass their declared thresholds. F7, N4-D3, and HS-M5 must be
listed individually as `PASS`, `OPEN`, or `deferred`.

`CHECK=1` makes an `OPEN` packet return non-zero for an explicit promotion
gate. A green packet still does not authorize a default change; Human GO is a
separate decision.
