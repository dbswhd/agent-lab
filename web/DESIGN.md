# Agent Lab Design System

## 1. Atmosphere & Identity

Agent Lab is a quiet operations console for people coordinating several coding agents without needing to live in a terminal. It should feel calm, legible, and trustworthy while work is active. The signature is progressive disclosure: final outcomes stay prominent, while status, reasoning summaries, tools, and diagnostics remain available without competing for attention.

## 2. Color

### Palette

The source of truth is `src/styles/tokens.css`; components must consume these semantic tokens instead of raw colors.

| Role | Token | Usage |
|---|---|---|
| App surface | `--surface-app` | Window background |
| Navigation surface | `--surface-rail` | Session rail and settings navigation |
| Working surface | `--surface-pane` | Transcript and primary page canvas |
| Raised surface | `--surface-card` | Inputs, active rows, popovers |
| Recessed surface | `--surface-sunken` | Grouped controls and secondary regions |
| Primary text | `--label-primary` | Titles, response text, active labels |
| Secondary text | `--label-secondary` | Supporting labels and metadata |
| Tertiary text | `--label-tertiary` | Hints and inactive controls; never essential body copy |
| Divider | `--border-hair` | Section separation |
| Control border | `--border-soft` | Inputs and interactive surfaces |
| Accent | `--accent` / `--accent-soft` | Focus, selection, primary action |
| Success | `--ok` / `--ok-soft` | Verified and resolved state |
| Warning | `--warn` / `--warn-soft` | Degraded but recoverable state |
| Danger | `--danger` / `--danger-soft` | Blocking or destructive state |

Status color supplements a text label and icon; it is never the only signal. Agent colors identify authors only and do not represent health.

## 3. Typography

Use `--font-sans` for UI and prose and `--font-mono` for commands, identifiers, paths, and raw output. The compact type ramp in `tokens.css` is authoritative: `--text-body` for readable content, `--text-footnote` for controls and metadata, `--text-caption` for short labels, and `--text-title1..3` for page and section titles. Essential body copy must not use `--text-caption` or `--label-tertiary`. Korean copy uses natural phrase boundaries and must not be forced into narrow fixed-width labels.

## 4. Spacing & Layout

Spacing uses the existing 4px-derived `--space-*` scale. Primary content is capped by `--composer-max`; settings content may expand to 1120px while maintaining a readable detail column. Desktop settings use a 180px category rail plus one content column. At widths below 760px the category rail becomes a full-width selector and all panels become single-column. At 375px, page padding is `--space-12` and no control may cause horizontal page scrolling.

The composer is a stable dock with this order: actionable status, mode/turn controls, active agent-model context, input. Only one blocking status is expanded at a time.

## 5. Components

### Action Notice

- **Structure:** semantic status region, severity icon, concise title/reason, primary action, optional disclosure.
- **Variants:** blocking, degraded, informational, resolved.
- **States:** active, busy, resolved, dismissed; resolved state expires automatically.
- **Accessibility:** `alert` only for newly blocking state, otherwise `status`; actions have explicit labels.

### Agent Model Chip

- **Structure:** agent label and concrete model name in one keyboard-focusable control.
- **Variants:** ready, unavailable, overflow summary.
- **Behavior:** opens or focuses the `/model` selection flow; the row scrolls horizontally rather than wrapping the composer taller.

### Activity Group

- **Structure:** a native disclosure summary followed by reasoning summaries, activity rows, command/tool runs, and errors.
- **Behavior:** open while running and collapsed after completion. Final agent output is outside the disclosure and always visible.
- **Accessibility:** summary reports item count and running/completed state; tool output remains selectable text.

### Settings Category

- **Structure:** category navigation and one focused content panel.
- **Behavior:** desktop vertical navigation; mobile select. The selected category persists for the current app session.
- **Depth:** sections use dividers and tonal shifts rather than nested card stacks.

## 6. Motion & Interaction

Use `--transition` for hover, focus, disclosure icon rotation, and opacity changes. Animate only `transform`, `opacity`, and color-related properties. Resolved notices may fade after three seconds. All interactions have visible `:focus-visible` treatment and respect `prefers-reduced-motion: reduce`, which disables non-essential transitions.

## 7. Depth & Surface

The strategy is tonal shift with hairline separators. Primary pages use `--surface-pane`, navigation uses `--surface-rail`, and interactive raised elements use `--surface-card`. Avoid nested bordered cards; reserve `--shadow-2` and stronger shadows for modal dialogs and floating popovers. Blocking states use a soft semantic tint and one border, never a large warning container around another card.
