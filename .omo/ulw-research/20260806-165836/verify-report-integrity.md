# Verification — report integrity

Executed after synthesis assembly on 2026-08-06.

- Markdown reference definitions: 47.
- External primary-source URLs: 37, all on `github.com` by user-requested scope.
- Local source/artifact references: 10; all paths exist.
- Undefined references: 0.
- Unused reference definitions: 0.
- External URL checks: 37/37 returned HTTP 2xx/3xx after redirects.
- Draft placeholders: 0. The two literal `TODO` strings are evidence about AX source, not report placeholders.
- Canonical identity corrections retained: OpenSandbox, Burr, Warren, Harbor, OpenHands SDK.

## Visual rendering

- Render path: Markdown → standalone HTML (`pandoc`) → A4 PDF (headless Chrome) → PNG pages (`pdftoppm`).
- Final render: 7 A4 pages, 773,575-byte PDF.
- Pixel inspection artifact: `rendered-final/contact-sheet.png` (1040×3000) plus 7 individual page PNGs.
- Delivery-header re-render inspection: `rendered-delivery-final/page-1.png` confirms the final 33-minute header and first-page layout.
- PASS: Korean text rendered; tables stayed within page bounds; no clipped rows, broken figures, blank content pages, overflow, or missing source ledger.
- First render exposed an empty-looking Sources section because reference definitions are hidden by Markdown renderers. The report was corrected with a visible repository-grouped source ledger and re-rendered before PASS.
