# X2 lift dogfood (SSOT)

Reversible execute-lift fixture. **Do not use for product docs.**

Dogfood runs fix the intentional `roompy` slug typo below, then `make x2-lift-dogfood-prepare`
(or `--prepare` on the live repeat script) resets it for the next pass.

| Check | Criterion |
|-------|-----------|
| Target | L17 Evidence row |
| Wrong | `…-roompy에서-consensus-…` |
| Right | `…-room.py에서-consensus-…` |
| Verify | Evidence row에 `room.py에서` 있고 `roompy에서` 없음 (L5·L11 설명용 `roompy`는 유지) |

## Evidence row (editable)

| **X2-lift** | 세션 `…-room.py에서-consensus-x2-lift-dogfood` (2026-07-08): reversible marker for history lift |
