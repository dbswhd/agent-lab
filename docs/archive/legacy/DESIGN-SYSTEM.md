# Agent Lab Design System

## 1. Atmosphere & Identity

Agent Lab is a quiet, dense macOS command center for supervising long-running agent work. Its signature is restrained graphite chrome with compact, contextual surfaces that appear beside the action instead of interrupting it.

## 2. Color

`web/src/styles/tokens.css` is the executable source of truth. Components use only its semantic variables: `--surface-*` for hierarchy, `--label-*` for text, `--border-*` for separation, `--accent*` for interaction, and `--ok`, `--warn`, `--danger` for status. Light and dark values are defined centrally; raw component colors are not added.

## 3. Typography

- Sans: `--font-sans`; mono: `--font-mono`.
- Scale: `--text-micro`, `--text-caption`, `--text-footnote`, `--text-body`, `--text-callout`, `--text-title3`, `--text-title2`, `--text-title1`.
- Weights and line heights use the declared `--weight-*` and `--leading-*` tokens.
- Dense metadata may use caption or micro; actionable labels use footnote or larger.

## 4. Spacing & Layout

- Spacing uses the existing `--space-*` scale; no new magic spacing values.
- Primary transcript and composer surfaces share `--composer-max`.
- Settings use compact responsive grids; overlays remain usable at 375, 768, and 1280 CSS pixels.
- Interactive targets remain at least 26px high in dense desktop contexts and preserve visible focus.

## 5. Components

### Picker

- Structure: optional heading, listbox options, optional cancel action.
- Variants: slash autocomplete, staged command choice, authentication flow.
- States: loading, empty, selected, hover, focus, disabled, error, completed.
- Keyboard: ArrowUp/Down, PageUp/Down, Enter, Escape; closing restores composer focus.

### Provider Status Row

- Structure: provider identity, auth method, connection status, secondary account detail.
- Settings renders this pattern read-only. Mutations are performed through slash commands.
- Status color is semantic and never the only signal.

### Authentication Flow

- Appears adjacent to the composer and streams trusted CLI progress.
- Secret input is masked and never copied into transcript or command history.
- Provides explicit cancel, retry, and safe browser-open actions.

## 6. Motion & Interaction

- Use `--transition` for micro-interactions and animate only `transform`, `opacity`, or `filter`.
- Hover, active, focus-visible, disabled, loading, success, and failure states are explicit.
- Respect `prefers-reduced-motion`; progress must remain understandable without animation.

## 7. Depth & Surface

Agent Lab uses a mixed strategy already encoded by tokens: tonal surface shifts and hairline borders define structure, while `--shadow-pop` is reserved for temporary elevated pickers. Persistent cards do not gain stronger shadows without updating this document and the token set.
