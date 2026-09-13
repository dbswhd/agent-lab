# Tracked dogfood readiness fixture

This directory is the compact, reproducible source fixture for the current
dogfood readiness report. It is intentionally separate from generated `.omo`
packets and contains no credentialed live-session data.

- `manifest.json` records the source commit used to author this fixture:
  `5677b7ea881a4bfd3c55fa57c1a97f1296d42df4`.
- `browser-contract.txt` is the small tracked browser-contract result used by
  the browser evidence row.
- Generated `dogfood-readiness.json` and `.md` files are disposable outputs;
  they must not be treated as a new commit's provenance or as a promotion.

From the repository root:

```bash
make dogfood-readiness-report \
  MANIFEST=docs/evidence/dogfood-readiness/manifest.json \
  OUT_DIR=/tmp/agent-lab-dogfood-readiness
```

The expected result is `readiness=OPEN`, live `n=0`, and
`default_change_authorized=false`.
