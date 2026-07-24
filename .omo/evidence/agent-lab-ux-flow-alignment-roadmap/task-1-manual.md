# Todo 1 manual surface proof

All commands ran from `/Users/yoonjong/Projects/agent-lab` after the documentation edits.

## Stale-term adversarial search

Invocation:

```bash
python - <<'PY'
from pathlib import Path
import re
files = [Path('.agent-lab/PROJECT.md'), Path('docs/USER-GUIDE.md'), Path('docs/05-room-agent-roles.md'), Path('docs/FLOW.md'), Path('docs/NOW.md'), Path('docs/redesign-2026-07/11-ui-ux-surface-map.md'), Path('docs/EXTERNAL-REFS-TRACEABILITY.md')]
pattern = re.compile(r'workbench|work tab|plan toggle|plan picker|wave b.*4/4|4/4.*wave b', re.I)
qualifiers = re.compile(r'archive|history|removed|not browser-accepted|browser acceptance|red|hidden|not visible|does not|아님|없다|제거|숨김|노출하지', re.I)
matches = [(f, n, line) for f in files for n, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1) if pattern.search(line)]
if any(not qualifiers.search(line) for _, _, line in matches):
    raise SystemExit('FAIL unqualified stale claim')
print(f'PASS adversarial stale-term search: {len(matches)} matches, all explicitly hidden/removed/archive/red')
PY
```

Observable: `PASS adversarial stale-term search: 14 matches, all explicitly hidden/removed/archive/red`.

The checker searched `workbench|work tab|plan toggle|plan picker|wave b.*4/4|4/4.*wave b` across all seven canonical docs and failed any match without an explicit archive/history/removed/red/hidden qualifier.

## Current surface proof

Invocation:

```bash
rg -n 'Decision Queue|topic-only|internal \`work\`|Workspace navigation|not browser-accepted|browser acceptance' \
  .agent-lab/PROJECT.md docs/USER-GUIDE.md docs/05-room-agent-roles.md docs/FLOW.md docs/NOW.md \
  docs/redesign-2026-07/11-ui-ux-surface-map.md docs/EXTERNAL-REFS-TRACEABILITY.md
sed -n '10,17p' .agent-lab/PROJECT.md
sed -n '200,242p;399,414p;994,1010p;1334,1343p' docs/USER-GUIDE.md
sed -n '1,8p;20,34p;100,110p' docs/05-room-agent-roles.md
sed -n '1,78p;160,200p' docs/FLOW.md
sed -n '1,40p;42,70p;105,110p' docs/NOW.md
sed -n '1,6p;73,88p;130,145p' docs/redesign-2026-07/11-ui-ux-surface-map.md
sed -n '1,20p;104,118p' docs/EXTERNAL-REFS-TRACEABILITY.md
```

Observable: all seven canonical docs expose topic-only Composer, Decision Queue precedence, current Transcript/Diff/Background/Files/Preview/Terminal plus Inspector Overview/Tools, and red/not-browser-accepted Wave B language. `sed -n` inspection covered PROJECT Room lines, USER-GUIDE IA/Composer and Inspector sections, roles Decision Queue section, FLOW lifecycle/gates, NOW Step 2/6–7 status, surface-map §7/§7.4, and traceability current-status/Partial sections.

## Markdown links and whitespace

Invocation:

```bash
python - <<'PY'
from pathlib import Path
import re
files = [Path('.agent-lab/PROJECT.md'), Path('docs/USER-GUIDE.md'), Path('docs/05-room-agent-roles.md'), Path('docs/FLOW.md'), Path('docs/NOW.md'), Path('docs/redesign-2026-07/11-ui-ux-surface-map.md'), Path('docs/EXTERNAL-REFS-TRACEABILITY.md')]
missing = []
count = 0
for f in files:
    for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', f.read_text(encoding='utf-8')):
        target = target.split('#', 1)[0].strip()
        if not target or '://' in target or target.startswith('mailto:'):
            continue
        count += 1
        if not (f.parent / target).resolve().exists():
            missing.append(f'{f}:{target}')
if missing:
    print('FAIL missing links')
    print('\n'.join(missing))
    raise SystemExit(1)
print(f'PASS markdown relative-link check: {len(files)} files, {count} local targets exist')
PY
git diff --check
```

Observable: `PASS markdown relative-link check: 7 files, 93 local targets exist`; `git diff --check` exits 0.

## Preservation

Unrelated dirty files (`.omo/boulder.json`, `.omo/drafts/`, `.omo/plans/`, `artifacts/plans/`, `scratch/`, and the existing benchmark report) were not edited or staged.

## Follow-up verifier rework

Follow-up commit: `057d5932573c7c9608282fc6b0d9bfec40135dcf` (`docs(ux): remove residual Work tab wording`).

Exact expanded search:

```bash
python - <<'PY'
from pathlib import Path
import re
files = [Path('.agent-lab/PROJECT.md'), Path('docs/USER-GUIDE.md'), Path('docs/05-room-agent-roles.md'), Path('docs/FLOW.md'), Path('docs/NOW.md'), Path('docs/redesign-2026-07/11-ui-ux-surface-map.md'), Path('docs/EXTERNAL-REFS-TRACEABILITY.md')]
pattern = re.compile(r'workbench|워크벤치|work tab|work 탭|work strip|plan toggle|plan picker|wave b.*4/4|4/4.*wave b|work\s*→|work\s+navigation', re.I)
qualifiers = re.compile(r'archive|history|removed|not browser-accepted|browser acceptance|red|hidden|not visible|does not|internal|아님|없다|제거|숨김|노출하지|legacy|과거|제거된|보여주지', re.I)
matches = [(f, n, line) for f in files for n, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1) if pattern.search(line)]
violations = [(f, n, line) for f, n, line in matches if not qualifiers.search(line)]
if violations:
    print('FAIL unqualified stale claim')
    print('\n'.join(f'{f}:{n}:{line}' for f,n,line in violations))
    raise SystemExit(1)
print(f'PASS expanded Korean/English stale-term search: {len(matches)} matches, all explicitly internal/hidden/removed/archive/red')
PY
```

Observable: `PASS expanded Korean/English stale-term search: 23 matches, all explicitly internal/hidden/removed/archive/red` (exact final checker: `matches=23 violations=0`).

Follow-up exact link/diff checks:

```bash
python - <<'PY'
from pathlib import Path
import re
files = [Path('.agent-lab/PROJECT.md'), Path('docs/USER-GUIDE.md'), Path('docs/05-room-agent-roles.md'), Path('docs/FLOW.md'), Path('docs/NOW.md'), Path('docs/redesign-2026-07/11-ui-ux-surface-map.md'), Path('docs/EXTERNAL-REFS-TRACEABILITY.md')]
missing=[]; count=0
for f in files:
  for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', f.read_text(encoding='utf-8')):
    target=target.split('#',1)[0].strip()
    if not target or '://' in target or target.startswith('mailto:'): continue
    count += 1
    if not (f.parent/target).resolve().exists(): missing.append(f'{f}:{target}')
if missing:
  print('FAIL missing links'); print('\n'.join(missing)); raise SystemExit(1)
print(f'PASS markdown relative-link check: {len(files)} files, {count} local targets exist')
PY
git diff --check
```

Observable: relative links `7 files, 93 local targets exist`; `git diff --check` exits 0. Residual current Korean Work-tab phrases were converted to Composer Decision Queue/internal work lane or archive/history wording, including the Mission Loop section and scenario appendix.

## Whole-file semantic Work audit

Exact audit invocation:

```bash
python - <<'PY'
from pathlib import Path
import re
p = Path('docs/USER-GUIDE.md')
lines = p.read_text(encoding='utf-8').splitlines()
pattern = re.compile(r'\bWork\b|work tab|work 탭|work strip|work lane|work_phase|(?-i:Work[A-Z])|worktree|workspace|Kimi Work|kimi_work|워크', re.I)
categories = {
  'archive/history': re.compile(r'archive|history|legacy|과거|이력', re.I),
  'internal-lane/component': re.compile(r'internal|내부|lane|component|컴포넌트|navigation tab이 아님|navigation tab 아님|Work[A-Z]|work_phase', re.I),
  'agent-identity': re.compile(r'Kimi Work|kimi_work|Work quota|work login', re.I),
  'filesystem/worktree': re.compile(r'worktree|workspace|cwd|작업', re.I),
}
occurrences=[]; violations=[]
for n,line in enumerate(lines,1):
  if pattern.search(line):
    occurrences.append((n,line))
    if not any(rx.search(line) for rx in categories.values()): violations.append((n,line))
if violations:
  print('FAIL unclassified Work occurrence(s)')
  print('\n'.join(f'{n}:{line}' for n,line in violations))
  raise SystemExit(1)
print(f'PASS semantic Work occurrence audit: {len(occurrences)} occurrences classified as archive/history, internal lane/component, agent identity, or filesystem/worktree')
for n,line in occurrences: print(f'{n}: {line}')
PY
```

Observable: `PASS semantic Work occurrence audit: 64 occurrences classified as archive/history, internal lane/component, agent identity, or filesystem/worktree`; no unclassified current Work navigation/surface claim remained.
