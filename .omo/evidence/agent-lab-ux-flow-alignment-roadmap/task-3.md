# Task 3 — Decision Queue to Oracle golden journey

Status: confirmed at `f60e3b35e8645b0f3611cf115f2195925ce1650d`.

The browser fixture proves the topic-to-PASS interaction contract: one Decision Queue action at a time, plan revision/approval, dry-run/diff, explicit merge, Oracle PASS-only completion, and FAIL-to-repair-to-PASS. It proves that the frontend emits no approval/merge POST before a rendered Human action and emits one ordinary request after each click. It does not claim production-route authorization or Mission authority; Task 6 owns that evidence.

## Final evidence

- Lifecycle suite: 6/6; repeat: 18/18.
- Affected nondefault-port E2E: 17/17; full nondefault-port E2E: 27/27.
- Unit suite: 185 passed; build, Prettier, and diff check passed.
- Five independent final-SHA lanes—goal, code, QA, security, and context—all passed.

Raw command records are in [`task-3/raw/code-lane-repair`](./task-3/raw/code-lane-repair/) and [`task-3/raw/security-context-fix`](./task-3/raw/security-context-fix/). Screenshots and traces remain under [`task-3`](./task-3/). Earlier clean-start and fixture-security failures are superseded; they are not current release evidence.

Residual watch: the stateful lifecycle fixture is large and is intentionally limited to browser/request-contract proof. Real authority, backend durability, restart/rollback, and live dogfood remain later-gate work.
