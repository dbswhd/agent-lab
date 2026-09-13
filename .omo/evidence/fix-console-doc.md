# Console composer contract documentation fix

- Scenario: Validate the current Composer contract in `docs/developer-agent-console.md`.
- Invocation: `rg -n -i 'plan\\s*toggle' docs/developer-agent-console.md`.
- Observable: command produced no matches and exited `1`; this is the expected no-stale-claim result.
- Scenario: Validate patch formatting and scope.
- Invocation: `git diff --check` and `git diff --cached --check` after staging `docs/developer-agent-console.md`.
- Observable: both commands exited 0; staged stat was exactly one file with one insertion and one deletion.
- Commit: `25eeead92ee85c8853368c670d2f72136e8ea703` (`docs: align console composer contract`).

## Reverification transcript (2026-07-24)

Invocation:

```text
set +e
rg -n -i 'plan\\s*toggle' docs/developer-agent-console.md
scan_exit=1
git diff --check
diff_exit=0
git show --format='%H%n%s' --stat --oneline HEAD
25eeead9 docs: align console composer contract
 docs/developer-agent-console.md | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)
```

Judgment: the targeted scan has no output and exit `1` (no forbidden claim), `git diff --check` exits `0`, and HEAD contains exactly the intended one-file documentation change.

## Independent hook verification (2026-07-24, second pass)

Raw command results:

```text
COMMAND 1: rg -n -i plan\\s*toggle docs/developer-agent-console.md
EXIT 1: 1
COMMAND 2: git diff --check
EXIT 2: 0
COMMAND 3: git show --format=fuller --stat --oneline HEAD
25eeead9 docs: align console composer contract
 docs/developer-agent-console.md | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)
EXIT 3: 0
COMMAND 4: git show --format= --name-only HEAD
docs/developer-agent-console.md
EXIT 4: 0
COMMAND 5: sha256sum docs/developer-agent-console.md .omo/evidence/fix-console-doc.md
71e37e3d242f92e7c248be37dfb62556b0440b0b4e4c30a05aae4aad4a291799  docs/developer-agent-console.md
7842c34b2bac7d1715d74e1244c654d6819db4045970edf3d3f5dbca9f7444ad  .omo/evidence/fix-console-doc.md
EXIT 5: 0
COMMAND 6: test -s evidence
EXIT 6: 0
exit_code=0
```

Judgment: all required checks passed; `rg` exit `1` confirms no matching stale claim, while scope, formatting, evidence non-emptiness, and hashes were successfully verified.

## Stop-hook verification (2026-07-24, third pass)

Raw output from the independent verification command:

```text
=== A: commit identity and scope ===
25eeead92ee85c8853368c670d2f72136e8ea703
25eeead92ee85c8853368c670d2f72136e8ea703
docs: align console composer contract

M docs/developer-agent-console.md
A_EXIT=0
=== B: current document forbidden-claim scan ===
B_EXIT=1
=== C: exact Composer row ===
27:| **Composer** | topic-only message · attachments (room preset is a setting/session default; Plan controls are hidden) |
C_EXIT=0
=== D: whitespace and worktree diff ===
D1_EXIT=0 D2_EXIT=0
=== E: evidence artifact ===
2235 .omo/evidence/fix-console-doc.md
E_EXIT=0
exit_code=0
```

Judgment: commit identity and one-file scope are correct; the forbidden-claim scan has no matches (expected exit `1`); the topic-only Composer row is present; both diff checks and worktree cleanliness pass; and the evidence artifact is non-empty.
