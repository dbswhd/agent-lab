# Final readiness freshness verification

Verification run after reported commit `9a323834bf169533406e4fe0a36a56e2684336dd`.

## Commit and focused tests

Invocation:

```text
git rev-parse HEAD
git show --format=fuller --stat --oneline HEAD
git diff HEAD^ HEAD --check
.venv/bin/pytest -q tests/test_dogfood_readiness_report.py tests/test_dogfood_readiness_live_evidence.py
```

Observed:

```text
9a323834bf169533406e4fe0a36a56e2684336dd
5 files changed, 167 insertions(+), 5 deletions(-)
..........                                                               [100%]
10 passed in 0.20s
```

Judgment: PASS. The commit contains only the readiness fixture/docs/test scope and has no whitespace errors.

## Clean checkout CLI

Invocation from a `git archive HEAD` checkout:

```text
/Users/yoonjong/Projects/agent-lab/.venv/bin/python scripts/dogfood_readiness_report.py \
  --manifest docs/evidence/dogfood-readiness/manifest.json \
  --out-dir /tmp/agent-lab-readiness-hook.E0PTpu/generated
```

Observed:

```text
readiness=OPEN
json=/tmp/agent-lab-readiness-hook.E0PTpu/generated/dogfood-readiness.json
markdown=/tmp/agent-lab-readiness-hook.E0PTpu/generated/dogfood-readiness.md
assertions=PASS
readiness= OPEN
live_n= 0
default_change_authorized= false
packet_commit_sha= 5677b7ea881a4bfd3c55fa57c1a97f1296d42df4
```

Judgment: PASS. The tracked manifest is usable in a clean checkout, remains `OPEN`, reports live `n=0`, and keeps `default_change_authorized=false`. The packet SHA is the documented source-authoring SHA, not the generated future commit.
