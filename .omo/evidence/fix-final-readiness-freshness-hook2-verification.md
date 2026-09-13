# Readiness freshness hook verification 2

## Source and tests

Invocation:

```text
git rev-parse HEAD
git diff-tree --no-commit-id --name-status -r HEAD
git diff HEAD^ HEAD --check
.venv/bin/pytest -q tests/test_dogfood_readiness_report.py tests/test_dogfood_readiness_live_evidence.py
```

Observed:

```text
HEAD=9a323834bf169533406e4fe0a36a56e2684336dd
changed files=docs/DOGFOOD-READINESS-STATUS.md,
  docs/evidence/dogfood-readiness/{README.md,browser-contract.txt,manifest.json},
  tests/test_dogfood_readiness_report.py
diff_check=PASS
..........                                                               [100%]
10 passed in 0.18s
```

The manifest source check observed `commit_sha=5677b7ea881a4bfd3c55fa57c1a97f1296d42df4`,
`live_status=OPEN`, and `live_sample_size=0`.

Judgment: PASS. The current commit still contains only the assigned readiness
fixture/docs/test scope and the focused readiness tests pass.

## Clean archive report

Invocation from a fresh `git archive HEAD` directory:

```text
/Users/yoonjong/Projects/agent-lab/.venv/bin/python scripts/dogfood_readiness_report.py \
  --manifest docs/evidence/dogfood-readiness/manifest.json \
  --out-dir /tmp/agent-lab-readiness-hook2.J9Sd6h/generated
```

Observed:

```text
readiness=OPEN
json=/tmp/agent-lab-readiness-hook2.J9Sd6h/generated/dogfood-readiness.json
markdown=/tmp/agent-lab-readiness-hook2.J9Sd6h/generated/dogfood-readiness.md
assertions=PASS
{'readiness': 'OPEN', 'live_n': 0, 'default_change_authorized': False}
packet_commit_sha= 5677b7ea881a4bfd3c55fa57c1a97f1296d42df4
```

Judgment: PASS. A clean checkout reads the tracked manifest and produces the
truthful non-promotable result: `OPEN`, live `n=0`, and
`default_change_authorized=false`.
