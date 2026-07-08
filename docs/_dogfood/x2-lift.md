# X2 lift dogfood (SSOT)

Reversible execute-lift fixture. **Do not use for product docs.**

Dogfood runs fix the intentional `roompy` slug typo below, then `make x2-lift-dogfood-prepare`
(or `--prepare` on the live repeat script) resets it for the next pass.

| Check | Criterion |
|-------|-----------|
| Target | L7 session ID fragment |
| Wrong | `…-roompy에서-consensus-…` |
| Right | `…-room.py에서-consensus-…` |
| Verify | `grep "room\.py" docs/_dogfood/x2-lift.md` matches L7; `grep roompy` is empty |

## Evidence row (editable)

| **X2-lift** | 세션 `…-roompy에서-consensus-x2-lift-dogfood` (2026-07-08): reversible marker for history lift |
