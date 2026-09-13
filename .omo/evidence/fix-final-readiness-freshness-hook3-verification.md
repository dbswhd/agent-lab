# Readiness freshness hook verification 3

## Current revision and tests

The worktree had advanced since the readiness fixture commit. The current
revision and the fixture commit ancestry were checked directly:

```text
git rev-parse HEAD
git diff-tree --no-commit-id --name-status -r HEAD
git merge-base --is-ancestor 9a323834bf169533406e4fe0a36a56e2684336dd HEAD
.venv/bin/pytest -q tests/test_dogfood_readiness_report.py tests/test_dogfood_readiness_live_evidence.py
```

Observed:

```text
HEAD=25eeead92ee85c8853368c670d2f72136e8ea703
HEAD commit files: M docs/developer-agent-console.md
readiness fixture commit 9a323834bf169533406e4fe0a36a56e2684336dd is an ancestor: PASS
..........                                                               [100%]
10 passed in 0.19s
```

Judgment: PASS. The readiness fixture remains in the current history; the
newer unrelated documentation commit was not changed.

## Clean archive report

Invocation from a fresh `git archive HEAD` directory:

```text
/Users/yoonjong/Projects/agent-lab/.venv/bin/python scripts/dogfood_readiness_report.py \
  --manifest docs/evidence/dogfood-readiness/manifest.json \
  --out-dir /tmp/agent-lab-readiness-hook3.4n2NY4/generated
```

Observed:

```text
readiness=OPEN
json=/tmp/agent-lab-readiness-hook3.4n2NY4/generated/dogfood-readiness.json
markdown=/tmp/agent-lab-readiness-hook3.4n2NY4/generated/dogfood-readiness.md
readiness='OPEN' expected='OPEN'
live_n=0 expected=0
default_change_authorized=False expected=False
packet_commit_sha=5677b7ea881a4bfd3c55fa57c1a97f1296d42df4
assertions=PASS
```

Judgment: PASS. The current clean checkout reads the tracked fixture and
produces the required truthful non-promotable result.
