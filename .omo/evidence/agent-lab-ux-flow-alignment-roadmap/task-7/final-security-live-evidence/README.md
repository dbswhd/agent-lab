# Final security live-evidence verification

## Exact adversarial regression, red then green

- Scenario: a hand-authored `run.json` claims `source=real-oracle`, `verdict=pass`, has empty `evidence` and `checked_paths`, declares `sample_size=10`, and raises `false_success_max` to `1` while every other gate is eligible.
- Red invocation: `.venv/bin/pytest -q tests/test_dogfood_readiness_report.py::test_live_pass_rejects_forged_real_oracle_without_evidence_even_when_threshold_allows_it tests/test_dogfood_readiness_report.py::test_packet_keeps_false_success_open_when_manifest_threshold_is_raised tests/test_dogfood_readiness_report.py::test_live_pass_requires_run_session_and_commit_provenance_binding` (before the focused tests were extracted).
- Red observable: exit `1`; all three adversarial assertions fail before the fix.
- Red artifact: [red-tests.txt](red-tests.txt) and [red-tests.exit](red-tests.exit).
- Green invocation: `.venv/bin/pytest -q tests/test_dogfood_readiness_report.py tests/test_dogfood_readiness_live_evidence.py`
- Green observable: exit `0`, `9 passed`.
- Green artifact: [focused-tests.txt](focused-tests.txt) and [focused-tests.exit](focused-tests.exit).

## Packet CLI manual QA

- Scenario: forged empty-proof live PASS through the real report command.
- Invocation: `make dogfood-readiness-report MANIFEST=<temporary-forged-manifest> OUT_DIR=<temporary-output>`.
- Observable: exit `2` and `LiveEvidenceValidationError: live PASS requires non-empty Oracle evidence and checked_paths`.
- Artifact: [forged-empty-proof-cli.txt](forged-empty-proof-cli.txt) and [forged-empty-proof-cli.exit](forged-empty-proof-cli.exit).

- Scenario: forged live PASS with non-empty proof but no run `session_id` / `commit_sha` binding.
- Invocation: `make dogfood-readiness-report MANIFEST=<temporary-forged-manifest> OUT_DIR=<temporary-output>`.
- Observable: exit `2` and `LiveEvidenceValidationError: live PASS run provenance must bind session and commit`.
- Artifact: [forged-provenance-cli.txt](forged-provenance-cli.txt) and [forged-provenance-cli.exit](forged-provenance-cli.exit).

- Scenario: the checked-in Task 7 manifest.
- Invocation: `make dogfood-readiness-report MANIFEST=.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/manifest.json OUT_DIR=.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/current-packet`.
- Observable: exit `0`, `readiness=OPEN`, live `n=0`, and `default_change_authorized=false`.
- Artifact: [current-packet-cli.txt](current-packet-cli.txt), [current-packet-cli.exit](current-packet-cli.exit), [dogfood-readiness.json](current-packet/dogfood-readiness.json), and [dogfood-readiness.md](current-packet/dogfood-readiness.md).

The temporary forged manifests and run directories were deleted after each CLI scenario. No server or background process was started.
