# Current documentation surface audit

## Scope

Updated only the current documentation references that asserted obsolete Work-tab or Composer-control behavior:

- `docs/README.md`
- `docs/ARCHITECTURE.md`
- `docs/MISSION-LOOP-C-OMO.md`
- `docs/GJC-ENTRY.md`

Committed documentation change: `611a57da docs: align current console contract`.

## Evidence

### Scenario: current UI documentation matches the actual UI contract

Invocation:

```sh
rg -n 'TOPIC_ONLY_COMPOSER = true|IMPLICIT_ROOM_PRESET = "supervisor"|Work tab removed|activeLane === "work"' web/src/utils/roomComposerPrefs.ts web/src/utils/workspaceTabs.ts web/src/components/ComposerEventStack.tsx
rg -n -i 'topic-only|setting/session|decision queue|internal `work` lane|Work navigation tab 없음|navigation tab이 아니다|workspace tabs \(⌘1–6\)' docs/README.md docs/ARCHITECTURE.md docs/MISSION-LOOP-C-OMO.md docs/GJC-ENTRY.md
```

Binary observable: exit status `0`; the source contract reports `TOPIC_ONLY_COMPOSER = true`, an implicit `supervisor` room preset, a removed Work tab, and an internal `work` lane. The documentation audit found the corresponding topic-only, setting/session, Decision Queue, Human Inbox, and no-navigation-tab statements.

### Scenario: obsolete visible-Work-tab and Composer-picker claims are absent

Invocation:

```sh
if rg -n -i 'tools[[:space:]]*→[[:space:]]*work|\*\*work[[:space:]-]?tab\*\*|composer mode:[[:space:]]*\*\*fast[[:space:]]*/[[:space:]]*supervisor' docs/README.md docs/ARCHITECTURE.md docs/MISSION-LOOP-C-OMO.md docs/GJC-ENTRY.md; then exit 1; fi
```

Binary observable: exit status `0` with no matches.

### Scenario: edited documentation is well-formed and its relative links resolve

Invocation:

```sh
git diff --check
for doc in docs/README.md docs/ARCHITECTURE.md docs/MISSION-LOOP-C-OMO.md docs/GJC-ENTRY.md; do
  rg -o '\]\(\./[^)#]+' "$doc" | cut -d: -f3- | sed 's#](./##' | while IFS= read -r target; do
    test -e "$(dirname "$doc")/$target"
  done
done
```

Binary observable: exit status `0`; `documentation-format-and-relative-link-audit: PASS`.
