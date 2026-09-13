# Final F3 manual QA run log

- Review worktree: `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review`
- Verified SHA: `01431f27a875ff0582a5d9e3f6905432eb0627c4`
- Browser: Playwright 1.60.0, Chromium, 1280x800, dark scheme
- Ports: `43173` lifecycle suite, `43174` Wave B suite; both were free before launch and free after teardown.

## Exact invocations and results

```sh
cd /Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/web
PLAYWRIGHT_WEB_PORT=43173 npx playwright test e2e/agent-lifecycle-journey.spec.ts \
  --grep='connected Human-gated journey|Oracle FAIL repairs|stale expected_version|reload resumes' \
  --trace=on --workers=1 --reporter=line
```

Result: `4 passed (13.2s)`.

```sh
cd /Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/web
PLAYWRIGHT_WEB_PORT=43174 npx playwright test e2e/wave-b-journey.spec.ts \
  --trace=on --workers=1 --reporter=line
```

Result: `4 passed (6.0s)`.

Trace inspection: all eight preserved traces are non-empty. Lifecycle traces contain Chromium screencast frames and PNG snapshots; golden has 277 frames/4 PNGs, Oracle repair 136/6, stale 24/2, reload 24/4. Wave B traces contain 23–44 frames and 2 PNG snapshots each. Network inspection shows golden `POST /plan/approve`, `/execute/dry-run`, `/execute/resolve` once each; repair adds `/execute/reverify` twice; stale resolves twice; reload has no side-effect POST. Wave B shows one expected request per journey: `/plan/reject`, `/execute/resolve`, `/execute/reverify`, and `/inbox/question-1/resolve` respectively.

## Visual observations

- Golden PASS screenshot: center worktree card shows Checks `3/3` and Oracle `통과`; the composer Decision Queue and Execute approval controls are absent; overview says `완료` / `Verified loop pass`.
- Oracle FAIL screenshot: center composer shows one active execution decision with `승인`, `거부`, `diff 보기`, and `Oracle 재검증`; overview shows `수정 중` and `Verified loop fail`.
- Oracle repaired PASS screenshot returns to the same no-active-decision surface with Checks `3/3` and Oracle `통과`.
- Stale screenshot shows one rendered active question decision and a `2건` queue count, with the next question queued below; no duplicate active decision is rendered.

## Cleanup

- Playwright web servers on 43173/43174 exited automatically; `lsof -nP -iTCP:43173 -sTCP:LISTEN` and the equivalent 43174 check returned no rows.
- No test browser/process was left running by either run.
- Ephemeral `/tmp/f3-qa-artifacts` and `/tmp/f3-port-*.txt` files were removed after their observations were recorded; retained evidence is under this directory only.
