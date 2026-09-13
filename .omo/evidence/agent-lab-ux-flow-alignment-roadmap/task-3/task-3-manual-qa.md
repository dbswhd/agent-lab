# Task 3 manual QA

Commit under test: `f60e3b35e8645b0f3611cf115f2195925ce1650d`.

An isolated browser run passed 6/6. Happy and repaired-PASS captures show Oracle pass with no active Execute CTA. The Oracle-FAIL capture stays REPAIRING and exposes revalidation. The stale queue capture has two queued items but only one expanded decision and Submit CTA. Network inspection showed no approval/merge POST before rendered Human actions, then exactly one ordinary request per action; no auto/trust request was emitted.

Stale replay returned 409 without changing the resolved version; reload did not replay a POST; dirty and malformed inputs did not promote audit or Oracle success. Temporary QA archives and listeners were removed after inspection.

Artifacts: [`happy`](../browser/happy-final-pass.png), [`repair FAIL`](../browser/repair-oracle-fail.png), [`repair PASS`](../browser/repair-final-pass.png), [`single active decision`](../browser/single-active-decision-queued.png), and the three trace ZIPs in `../traces/`.
