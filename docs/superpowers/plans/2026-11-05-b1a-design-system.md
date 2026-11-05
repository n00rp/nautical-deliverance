# B1 Part A — Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tokens and every pilot 1 component in `web/`, documented in Storybook, with visual regression and accessibility checks in CI.

**Architecture:** CSS Modules + CSS custom properties (one tokens file, light/dark), React function components in `web/src/ui/`, Radix primitives only for Select/Dialog/Popover. Storybook 9 (Vite builder) holds a story per state; Playwright screenshots every story in CI's Linux container; axe runs on every story.

**Tech Stack:** React 19, TypeScript strict, Vite, CSS Modules, Radix UI primitives, Storybook (Vite), Playwright, axe-core, stylelint.

**Spec:** [docs/superpowers/specs/2026-11-05-b1-domain-and-design-system-design.md](../specs/2026-11-05-b1-domain-and-design-system-design.md) §2, B1-D8, B1-D9, B1-R12–R16. Visual source: the B0 prototype `docs/prototypes/b0-purchase-flow.html` (tokens and look).

## Global Constraints

- English only. TypeScript `strict` + `noUncheckedIndexedAccess`. All web gates from S0 stay green (typecheck, lint, format:check, depcruise, knip, test --coverage ≥ 90 % lines/branches, duplication).
- Requirement tests name `[B1-Rnn]` in the test title.
- No literal colours, font families, font sizes or spacing in component styles — only `var(--…)` tokens (B1-R12).
- Every dependency pinned exactly, release ≥ 14 days old; licence must pass `tools/check_licenses.py` (OFL-1.1 font files: see Task A1 step 1).
- Fonts self-hosted (B1-D9); no request to Google at runtime.
- Accessibility: keyboard operable, visible focus (`:focus-visible` token), WCAG 2.2 AA contrast in both themes.
- NumberField never converts to a JS `number` (D-074).
- Branch: `feat/b1a-design-system`; Conventional Commits ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; no push without the controller.

## Review Focus

1. **Dark mode via `prefers-color-scheme` with no `data-theme`** → tokens switch; stories render in both (visual regression covers both). Task A2.
2. **Very long text in table cells / names** (60+ chars, no spaces) → wraps or truncates with tooltip; never widens the page. Task A4.
3. **NumberField paste of `1 234,56` or `1,234.56`** → normalized `1234.56`; garbage paste → field error, value unchanged. Task A3.
4. **Narrow viewport (400 px)** → AppShell nav collapses; tables scroll inside their container. Tasks A4, A5.
5. **Reduced motion** → no transitions when `prefers-reduced-motion: reduce`. Task A2.

## File Structure

```
web/src/ui/tokens.css             all tokens (light, dark via media + data-theme)
web/src/ui/fonts/                 IBM Plex woff2 files + fonts.css (@font-face)
web/src/ui/<Component>/<Component>.tsx, .module.css, .stories.tsx, .test.tsx
web/.storybook/main.ts, preview.ts
web/stylelint.config.mjs          token-only rule
web/tests/visual/stories.spec.ts  Playwright: screenshot + axe per story (light/dark)
tools/trace.py                    + B-prefixed IDs
```

---

### Task A1: Tokens, fonts, token lint, B-prefixed traceability

**Files:** create `web/src/ui/tokens.css`, `web/src/ui/fonts/*`, `web/stylelint.config.mjs`; modify `web/package.json` (scripts `stylelint`), `tools/trace.py`, `tools/test_trace.py`, `.github/workflows/ci.yml` (web job runs stylelint, `# req: B1-R12`).

**Interfaces — Produces:** CSS variables `--color-bg, --color-surface, --color-fg, --color-muted, --color-line, --color-accent, --color-accent-fg, --color-accent-soft, --color-ok(-soft), --color-warn(-soft), --color-crit(-soft), --color-info-soft, --font-body, --font-display, --font-mono, --text-xs|sm|md|lg|xl, --space-1..6, --radius, --focus-ring`; `pnpm --dir web stylelint`; trace regex accepts `B\d+[a-z]?-R\d{2}`.

- [ ] **Step 1: Fonts and licence.** Obtain IBM Plex Sans (400/500/600), Sans Condensed (600), Mono (400/500) woff2 from the official IBM Plex release (record version, source URL, SHA-256 in `web/src/ui/fonts/README.md`). IBM Plex is SIL OFL-1.1: if `tools/check_licenses.py` scans them (it scans packages, not vendored files), no change is needed; if fonts come via an npm package, STOP and report — adding OFL-1.1 needs an owner decision.
- [ ] **Step 2: Failing tests.** `tools/test_trace.py` `test_b_prefixed_ids_collected` (`req("B1-R15")`): spec row `| B1-R01 |` and a TS test `[B1-R01]` → covered. `web/src/ui/tokens.test.ts` `[B1-R12] every token has a dark value` (parse tokens.css: each `--color-*` in `:root` reappears in both dark blocks). Stylelint fixture test `[B1-R12] lint rejects literal colour` (runs stylelint on a fixture CSS module with `color: #fff` → non-zero, rule name in output; clean module → zero).
- [ ] **Step 3: Implement** tokens from the prototype palette (rename to `--color-*`), `fonts.css`, stylelint rule (`stylelint-declaration-strict-value` or `color-no-hex` + `declaration-property-value-disallowed-list` — pick the pinned plugin; must also forbid literal `font-family` and px spacing in `*.module.css`), trace regex.
- [ ] **Step 4: Run** tools tests, web gates, stylelint → green. **Commit** `feat(web): add design tokens, self-hosted fonts and token lint`.

### Task A2: Storybook, visual regression, accessibility harness, Button

**Files:** create `web/.storybook/*`, `web/src/ui/Button/*`, `web/tests/visual/stories.spec.ts`, `web/playwright.config.ts`; modify `web/package.json` (scripts `storybook`, `build-storybook`, `test:visual`), `.github/workflows/ci.yml` (new job `visual`, `# req: B1-R13`, runs in pinned `mcr.microsoft.com/playwright` image by digest, uploads diff artifacts on failure).

**Interfaces — Produces:** `Button({ variant: "primary"|"secondary"|"ghost", loading?, disabled?, type?, children, ...buttonProps })`; story naming `UI/<Component>/<State>`; visual spec iterates `index.json` of the built Storybook and, per story, screenshots in light and dark (`colorScheme`) and runs axe (`@axe-core/playwright`), failing on any violation.

- [ ] **Step 1: Failing tests:** `Button.test.tsx` `[B1-R13] button states` (disabled not clickable; loading shows busy label and `aria-busy`); visual spec runs on the built storybook (baseline committed under `web/tests/visual/__screenshots__/`).
- [ ] **Step 2: Implement** Storybook config (preview imports tokens.css and fonts.css; theme toggle decorator sets `data-theme`), Button with all variants/states, Playwright config (Linux only for baselines; `--update-snapshots` documented in README).
- [ ] **Step 3: Reduced motion** (Review Focus 5): global CSS disables transitions under `prefers-reduced-motion: reduce`; story test asserts computed `transition-duration` is `0s`.
- [ ] **Step 4: Run** unit, build-storybook, visual (in the Playwright container locally via `docker run`), web gates → green. **Commit** `feat(web): add storybook, visual regression and button`.

### Task A3: Form components

**Files:** `web/src/ui/{TextField,NumberField,Select,Checkbox,DateTimeField,FieldError,FormSummary}/*`; add `@radix-ui/react-select` pinned.

**Interfaces — Produces:**
- `TextField({ id, label, value, onChange(value: string), error?, hint?, required?, disabled? })`
- `NumberField({ id, label, value: string, onChange(value: string), decimals: number, unit?, error?, … })` — value is a normalized decimal string `^-?\d+(\.\d+)?$` or `""`.
- `normalizeDecimal(input: string, decimals: number): { value: string } | { error: string }` in `NumberField/normalize.ts`.
- `Select<T extends string>({ id, label, value: T|"", options: {value: T, label: string, disabled?: boolean}[], onChange(v: T) })`
- `Checkbox({ id, label, checked, onChange(b: boolean) })`
- `DateTimeField({ id, label, valueUtc: string /* ISO, Z */, onChange(isoUtc: string), timeZone?: string /* IANA, shows local hint */ })`
- `formatInstant(isoUtc: string, timeZone?: string): string` → `"12 Nov 06:00 UTC · 07:00 local"` (B1-D10; used by B1 Part B for B1-R08 display).
- `FieldError({ id, children })`, `FormSummary({ errors: {fieldId: string, message: string}[] })` (links focus the field).

- [ ] **Step 1: Failing tests:** `[B1-R14] normalizeDecimal keeps precision` (`"0.1"`, `"12345678901234.56"`, `"1 234,56"`, `"1,234.56"` → exact strings; `"12abc"` → error; property test with fast-check over decimal strings: output equals canonical input, no float involved — assert implementation never calls `Number`/`parseFloat` via a source scan); `[B1-R08] formatInstant across DST` (`2026-03-29T00:30:00Z` and `T01:30:00Z` for `Europe/Amsterdam` → local 01:30 then 03:30); a11y label/error association tests for each field.
- [ ] **Step 2: Implement** components + stories (default, filled, error, disabled, focus; NumberField paste cases), using tokens only.
- [ ] **Step 3: Run** unit, visual, web gates → green. **Commit** `feat(web): add form components with exact decimal input`.

### Task A4: Data display components

**Files:** `web/src/ui/{Table,StatusPill,Panel,DetailPanel,EmptyState,HistoryList,LockedNote}/*`.

**Interfaces — Produces:**
- `Table<Row>({ columns: {key: string, header: string, align?: "start"|"end", render(row): ReactNode, sortValue?(row): string|number}[], rows: Row[], rowKey(row): string, onRowSelect?(row), selectedKey?, loading?, empty?: ReactNode, caption: string })` — sticky header, overflow container, keyboard row selection (Enter/Space), sort toggles `aria-sort`.
- `StatusPill({ status: "Draft"|"RFQ sent"|"Offers received"|"Winner selected"|"Nominated"|"Cancelled" } | { tone: "ok"|"warn"|"crit"|"info"|"accent", children })`
- `Panel({ title?, actions?, children })`, `DetailPanel({ title, open, onClose, children })` (side panel ≥ 900 px, stacked below on narrow)
- `EmptyState({ title, body?, action? })`, `LockedNote({ what: string })` → "Hidden for your role: …"
- `HistoryList({ entries: {id, actor, at: string /*ISO*/, action: "create"|"update"|"deactivate"|"reactivate", changes: {field, before: string|null, after: string|null}[]}[] })` newest first.

- [ ] **Step 1: Failing tests** per component (sorting, selection by keyboard, empty/loading, history order, long unbroken text does not overflow — Review Focus 2: assert `overflow-wrap:anywhere` on cells and container `scrollWidth` ≤ `clientWidth` for page wrapper in a narrow story via Playwright).
- [ ] **Step 2: Implement** + stories (incl. 15-row offer-like table, long-name row, empty, loading, dark).
- [ ] **Step 3: Run** → green. **Commit** `feat(web): add table, pills, panels and history list`.

### Task A5: Shell and feedback; S0 page migrated

**Files:** `web/src/ui/{AppShell,Toast,InlineConfirm,RoleGate}/*`; modify `web/src/App.tsx` (render inside AppShell; keep S0 behaviours and tests).

**Interfaces — Produces:**
- `AppShell({ productName, user: {name: string, roles: Role[]} | null, nav: {href, label, disabled?: boolean, section?: string}[], banner?: ReactNode, children })` — nav collapses to a menu button < 900 px (Review Focus 4).
- `useToast(): (message: string, tone?: "info"|"ok"|"warn"|"crit") => void` + `<ToastHost/>` (aria-live polite).
- `InlineConfirm({ label, confirmLabel, onConfirm, tone? })` — two-step button, no `window.confirm`.
- `type Role = "admin"|"bunker_buyer"|"operator"|"viewer"`; `RoleGate({ allow: Role[], roles: Role[], fallback?: ReactNode, children })`.

- [ ] **Step 1: Failing tests:** RoleGate matrix; InlineConfirm requires two activations; ToastHost announces; AppShell narrow-nav story; existing App tests still pass.
- [ ] **Step 2: Implement**, migrate App.tsx to AppShell (product name from `productName.ts`).
- [ ] **Step 3: Final verification:** all web gates, stylelint, unit, build-storybook, visual (light+dark, all stories, axe), `python tools/trace.py --check`. **Commit** `feat(web): add app shell, toasts, inline confirm and role gate`.

## Spec coverage
B1-R12 → A1 · B1-R13 → A2–A5 · B1-R14 → A3 · B1-R08 (display helper) → A3 · B1-R15 → A1 · B1-R16 → A5.
