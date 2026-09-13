# Stop-hook verification 2

- Commit identity: `git rev-parse HEAD` returned `5677b7ea881a4bfd3c55fa57c1a97f1296d42df4`; see [sha.txt](sha.txt).
- Regression command: `.venv/bin/pytest -q tests/test_dogfood_readiness_report.py tests/test_dogfood_readiness_live_evidence.py` exited `0` with `9 passed`; see [focused-tests.txt](focused-tests.txt) and [focused-tests.exit](focused-tests.exit).
- Current-packet command: `make dogfood-readiness-report MANIFEST=.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/manifest.json OUT_DIR=<verification-output>` exited `0`; its parsed output is `readiness=OPEN`, `live_sample_size=0`, and `default_change_authorized=False`; see [current-cli.txt](current-cli.txt), [current-cli.exit](current-cli.exit), and [current-observable.txt](current-observable.txt).
- Forged-packet command: `make dogfood-readiness-report MANIFEST=<temporary-forged-manifest> OUT_DIR=<temporary-output>` exited `2` after rejecting a non-mock labeled PASS with empty evidence and checked paths; see [forged-empty-cli.txt](forged-empty-cli.txt) and [forged-empty-cli.exit](forged-empty-cli.exit).

Temporary forged manifests and run directories were removed after the command completed.
