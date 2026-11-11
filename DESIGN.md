---
name: Finance Pulse Analytics
description: Enterprise Financial Performance Intelligence and Profitability Optimization Analytics Platform — calm, precision macOS-inspired visual system for local financial intelligence.
colors:
  primary: "#0066CC"
  primary-hover: "#0052A3"
  primary-soft: "#EDF5FF"
  neutral-canvas: "#F5F5F7"
  neutral-surface: "#FFFFFF"
  neutral-subtle: "#F9F9FB"
  neutral-muted: "#ECECF0"
  ink-primary: "#1D1D1F"
  ink-secondary: "#515154"
  ink-muted: "#636368"
  ink-placeholder: "#6E6E73"
  positive: "#0E6027"
  positive-soft: "#EAF6EE"
  danger: "#A61B1B"
  danger-soft: "#FCECEB"
  warning: "#7C4300"
  warning-soft: "#FEF5E7"
  chart-expense: "#C2590A"
typography:
  display:
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", ui-sans-serif, system-ui, sans-serif'
    fontSize: "clamp(2.25rem, 4.1vw, 3.25rem)"
    fontWeight: 600
    lineHeight: 1.08
    letterSpacing: "-0.026em"
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", ui-sans-serif, system-ui, sans-serif'
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.18
    letterSpacing: "-0.022em"
  title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", ui-sans-serif, system-ui, sans-serif'
    fontSize: "19px"
    fontWeight: 600
    lineHeight: 1.28
    letterSpacing: "-0.014em"
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", ui-sans-serif, system-ui, sans-serif'
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "0em"
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", ui-sans-serif, system-ui, sans-serif'
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0em"
  numeric:
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", ui-sans-serif, system-ui, sans-serif'
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.35
    fontFeature: '"tnum" 1'
rounded:
  sm: "8px"
  md: "10px"
  lg: "14px"
  xl: "18px"
  sheet: "20px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "20px"
  xl: "24px"
  2xl: "36px"
  section: "72px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.neutral-surface}"
    rounded: "{rounded.md}"
    padding: "9px 16px"
    height: "38px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-pill:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.neutral-surface}"
    rounded: "{rounded.pill}"
    padding: "10px 20px"
    height: "38px"
  button-secondary:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.md}"
    padding: "9px 16px"
    height: "38px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.md}"
    padding: "9px 16px"
    height: "38px"
  input-field:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
    height: "40px"
  panel-card:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.lg}"
    padding: "22px 24px"
  kpi-strip:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.lg}"
    padding: "18px 20px"
  chip-neutral:
    backgroundColor: "{colors.neutral-muted}"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.pill}"
    padding: "3px 10px"
  nav-item-active:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.md}"
    padding: "8px 10px"
---

# Design System: Finance Pulse Analytics

## Overview

**Creative North Star: "Precision Ledger Instrument"**

**Finance Pulse Analytics: Enterprise Financial Performance Intelligence and Profitability Optimization Analytics Platform** translates Apple's spatial clarity and tactile restraint into a local-first enterprise financial workbench. Rather than competing with imported revenue, margin, and forecast figures through heavy chrome or decorative gradients, the interface recedes into cool aluminum-mist ground (`#F5F5F7`) and crisp optical-white work sheets (`#FFFFFF`) bound by sub-pixel hairline strokes. Every numerical value sits in aligned tabular columns so multi-period performance, outliers, target-margin plans, and scenario deltas read effortlessly at a glance.

The system splits cleanly between Persuade mode (the editorial landing showcase and uncluttered sign-in gate) and Operate mode (a persistent desktop sidebar with frosted translucent headers across User and Admin portals). Interaction relies on immediate press feedback (`scale(0.975)`), translucent sticky chrome (`saturate(180%) blur(20px)`), and unified hairline-divided strips rather than repetitive multi-card grids.

**Key Characteristics:**
- Cool Apple aluminum-mist canvas (`#F5F5F7`) paired with pure elevated white work sheets (`#FFFFFF`) and structural hairline borders (`rgba(29, 29, 31, 0.09)`).
- Single high-contrast cobalt action accent (`#0066CC`, 5.58:1 on white) reserved strictly for primary calls to action, focus rings, active toggles, and baseline series traces.
- Native system SF Pro Display and Text optical tracking coupled with forced `tabular-nums` (`tnum`) across KPI metrics, slider readouts, timestamps, and ledger tables.
- Monochrome 1.65px-stroke vector iconography anchored by a custom dark-graphite pulse waveform squircle brand mark.
- Explicit accessibility parity for `prefers-reduced-motion`, `prefers-reduced-transparency`, and `prefers-contrast: more`.

## Colors

A disciplined neutral grayscale architecture carries almost every surface, reserving color exclusively for interactive intent (`#0066CC`) and verified financial semantics (`#0E6027` gain, `#A61B1B` deficit, `#7C4300` outlier warning, `#C2590A` expense series).

### Primary
- **Apple Cobalt** (`primary`): Interactive primary buttons, pill CTAs, links, active navigation icon tint, focus rings (`rgba(0, 102, 204, 0.28)`), text selection wash (`rgba(0, 102, 204, 0.16)`), slider thumb borders, and Revenue chart lines.
- **Pressed Cobalt** (`primary-hover`): Hover state on primary buttons and high-contrast ink inside soft cobalt status chips.
- **Cobalt Mist** (`primary-soft`): Subtle background tint for role chips, drag-over dropzones, interactive link pills on hover, and dataset column mapping indicators.

### Neutral
- **Aluminum Mist** (`neutral-canvas`): Primary application shell canvas behind workspaces, auth backdrop, and the portal-comparison landing band.
- **Optical White** (`neutral-surface`): Primary panels, unified KPI metric strips, hero opening wash (`#FFFFFF` blending into `#F5F5F7`), interactive showcase window, auth card, inputs, and active sidebar pills.
- **Tinted Snow** (`neutral-subtle`): Alternating capability proof sheets, interactive row actions at rest, table row hover wash, window chrome bar, and upload dropzone surface.
- **Hairline Slate** (`neutral-muted`): Segmented switch wells, neutral status badges, header currency pills, slider tracks, and percentage bar tracks.
- **Deep Graphite** (`ink-primary`): Headings, primary metric figures, active controls, inverted tooltips, active subnav pill fill, and the dark waveform brand squircle background.
- **Charcoal Slate** (`ink-secondary`): Navigation labels, descriptive paragraph copy, chart legend labels, secondary filter captions, and field labels.
- **Muted Pewter** (`ink-muted`): Table headers, KPI labels, timestamps, chart axis ticks, footer metadata, and muted empty-state copy.
- **Placeholder Silver** (`ink-placeholder`): Input placeholder strings maintaining WCAG AA readability on optical-white fields.

### Semantic & Data Series
- **Emerald Ledger** (`positive` / `positive-soft`): Net profit gains, favorable scenario deltas, clean data-quality pills, check icons, and Chart.js Profit series.
- **Crimson Deficit** (`danger` / `danger-soft`): Negative profit/margin readouts, Expense anomaly tags, destructive validation flashes, and unfavorable scenario deltas.
- **Amber Caution** (`warning` / `warning-soft`): IQR anomaly warnings, malformed-date data-quality pills, and forecast caution context.
- **Warm Ochre Trace** (`chart-expense`): Dedicated Chart.js series stroke distinguishing operating Expenses from Revenue (`primary`) and Profit (`positive`).

### Named Rules
**The One Accent Rule.** Only Apple Cobalt (`primary`) carries interactive brand weight across a viewport; never introduce secondary brand hues, gradient fills on headings, or colored accent strips beside cards.
**The Honest Semantic Rule.** Green (`positive`), red (`danger`), and amber (`warning`) appear exclusively to report calculated financial outcomes or system validation states, never as decorative chrome.

## Typography

**Display Font:** `-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", ui-sans-serif, system-ui, sans-serif`
**Body Font:** `-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", ui-sans-serif, system-ui, sans-serif`
**Label/Mono Font:** `"SF Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace` (for monospace measurements when explicitly needed) and native system sans with `font-variant-numeric: tabular-nums` (`tnum`).

**Character:** Optical system typography pairs tight negative tracking on large titles with open neutral line height (`1.55`) on workspace prose and strictly fixed-width figures (`tabular-nums`) for effortless vertical scanning of ledgers and timestamps.

### Hierarchy
- **Display** (`display` — Weight `600`, responsive `clamp(2.25rem, 4.1vw, 3.25rem)`, line-height `1.08`, tracking `-0.026em`): Reserved solely for the primary persuasion hero headline above the interactive showcase window.
- **Headline** (`headline` — Weight `600`, `26px`, line-height `1.18`, tracking `-0.022em`): Top sticky workspace page titles (`h1`) across User and Admin portals, plus auth sheet headings (`28px` / `-0.022em`).
- **Title** (`title` — Weight `600`, `19px`, line-height `1.28`, tracking `-0.014em`): Panel and visualization headings (`h2`), supported by `16px` (`-0.01em`) card sub-headers (`h3`).
- **Body** (`body` — Weight `400`, `15px`, line-height `1.55`, tracking `0em`): Default prose and table ledger copy, capped at `58ch`–`65ch` on explanatory paragraphs (`56ch` hero lead, `58ch` methodology notes).
- **Label** (`label` — Weight `500`–`600`, `12px`–`14px`, line-height `1.4`, mixed case): Navigation links (`14px`), form labels (`13px`), table column headers (`12px`, `600` weight), and status pills (`12px`).
- **Numeric** (`numeric` — Weight `600`, `14px`–`22px`, `tabular-nums`): Right-aligned numeric ledger cells, KPI summary figures (`22px`, tracking `-0.02em`), definition list figures, and left-aligned timestamps/periods (`tnum`).

### Named Rules
**The Tabular Figure Rule.** Every monetary amount, percentage, count, date, period string, and number input enforces `font-variant-numeric: tabular-nums` (`font-feature-settings: "tnum" 1`) so decimals and columns align vertically.
**The Optical Tracking Rule.** Headlines scale negative tracking progressively with font size (`-0.014em` at `19px`, `-0.022em` at `26px`, `-0.026em` on hero display), while body copy and UI labels remain neutral (`0em`) in natural Sentence case with zero all-caps tracked eyebrows.

## Layout

Desktop portals anchor navigation inside a fixed `252px` translucent left sidebar paired with a scrollable main column capped cleanly at `1360px` (`28px 36px 52px` padding). Marketing and sign-in routes switch to a centered editorial flow (`1140px` showcase bands, `720px` centered hero copy, `440px` auth sheet) opening in generous whitespace before cascading down to stacked mobile viewports (`390px`).

Spatial hierarchy alternates densities intentionally rather than tiling equal cards:
1. A compact horizontal filter/control toolbar (`14px 18px` padding) anchors workspace parameters (`From` / `To` date inputs or forecasting controls).
2. A single unified KPI metric strip spans full grid width (`repeat(5, 1fr)`, `repeat(4, 1fr)`, or `repeat(3, 1fr)`), collapsing gracefully to `3` columns below `1120px` and stacking cleanly to `1` column below `640px`.
3. Primary visualization panels occupy full content width above asymmetric 2-column splits (`1.35fr 1fr` on dashboard insights + drilldowns; `1fr 1.05fr` on editorial claim-and-proof landing rows; `1fr 1fr` on dual workflow forms).
4. Sticky frosted headers collapse navigation behind a `38px` menu toggle sliding the drawer from the left on viewports `<= 960px` (`cubic-bezier(0.22, 1, 0.36, 1)` over `240ms`), while wide financial tables scroll inside padded `.tablewrap` bounds so `scrollWidth` matches viewport width cleanly down to `390px`.

## Elevation & Depth

Surfaces rely almost entirely on **tonal ground contrast plus 1px hairline borders** (`rgba(29, 29, 31, 0.09)` at rest, `rgba(29, 29, 31, 0.18)` on controls/table headers) rather than drop shadows. Real elevation is reserved exclusively for floating hero demonstrations, sticky glass navigation headers, auth dialogs, slider thumbs, and slide-over mobile drawers.

### Shadow Vocabulary
- **Subtle Rest Shadow** (`0 1px 2px rgba(29, 29, 31, 0.04)`): Barely perceptible anchor for active pill containers (`box-shadow: 0 1px 2px rgba(29, 29, 31, 0.06), inset 0 0 0 1px rgba(29, 29, 31, 0.09)` on the selected sidebar item) and floating switch thumbs.
- **Floating Sheet Shadow** (`0 24px 60px -16px rgba(29, 29, 31, 0.14), 0 4px 12px -2px rgba(29, 29, 31, 0.05)`): Reserved strictly for the centered authentication dialog and the landing interactive showcase window (`1px` perimeter ring plus deep soft elevation).
- **Mobile Drawer Shadow** (`24px 0 48px rgba(0, 0, 0, 0.12)`): Separates the slide-out navigation drawer over dimmed (`rgba(29, 29, 31, 0.28)`) scrolled workspace content below `960px`.
- **Frosted Sticky Chrome** (`rgba(255, 255, 255, 0.82)` with `backdrop-filter: saturate(180%) blur(20px)`): Sticky application and landing top bars allow underlying scrolled tables and charts to diffuse smoothly beneath content headers, falling back to solid `neutral-surface` under `prefers-reduced-transparency: reduce`.

### Named Rules
**The Flat-Workspace Rule.** Analytical panels, KPI strips, and toolbars never cast ambient shadows at rest; separation comes from crisp optical-white fills on Aluminum Mist (`#F5F5F7`) plus sub-pixel hairline borders.
**The Hover-Precision Rule.** Pointer hover transitions are gated behind `@media (hover: hover) and (pointer: fine)`, while tactile press feedback scales controls minimally (`scale(0.975)`–`0.985` over `120ms`) and collapses under `prefers-reduced-motion: reduce`.

## Shapes

Corner radii express progressive containment hierarchy from internal controls up to floating sheets, keeping interior components tighter than outer containers:
- **Small Control Radius (`sm` — `8px`)**: Tooltip scrubbers, quiet sidebar sign-out links, drawer close controls, and compact buttons inside headers (`34px`–`36px`).
- **Interactive Primitive Radius (`md` — `10px`)**: Standard rectangular buttons, form inputs, selects, action list rows, active sidebar nav items, and flash banners.
- **Primary Panel Radius (`lg` — `14px`)**: Unified KPI strips, primary work panels, filter toolbars, editorial capability proof sheets, and file dropzones.
- **Feature Sheet Radius (`xl` — `18px`)**: Hero showcase window (`18px`), portal comparison panels, and empty-state onboarding containers.
- **Modal Auth Sheet (`sheet` — `20px`)**: Centered standalone sign-in and account registration surfaces.
- **Full Capsule Pill (`pill` — `999px`)**: Hero CTAs, analysis sub-view filter tabs, segmented control shell/thumb, semantic status badges, slider tracks, and range progress bars.

## Components

Every component pairs quiet resting geometry with unambiguous keyboard focus (`3px` halo of `rgba(0, 102, 204, 0.28)` on buttons/links, `#0066CC` border plus soft `rgba(0, 102, 204, 0.16)` focus glow on fields).

### Buttons
Decisive, compact hit targets (`min-height: 38px`) with crisp optical centering and immediate downward scale (`0.975`) on `:active`.
- **Shape:** `10px` radius (`button-primary`, `button-secondary`) inside app toolbars and forms; `999px` pill radius (`button-pill`) on landing heroes, onboarding CTAs, and import confirmations.
- **Primary:** Solid `primary` (`#0066CC`) fill with pure white (`#FFFFFF`) 500-weight label (`9px 16px` standard, `10px 20px` pill; auth submit `44px` tall, `600` weight).
- **Hover / Focus:** Shifts background cleanly to `primary-hover` (`#0052A3`) within `150ms cubic-bezier(0.25, 0.1, 0.25, 1)` on fine pointers; keyboard `:focus-visible` renders a `3px` cobalt halo.
- **Secondary & Quiet:** Optical white (`#FFFFFF`) fill with hairline strong border (`rgba(29, 29, 31, 0.18)`) for exports and reset buttons (`button-secondary`); transparent borderless ghost treatment highlighting to `5%` graphite tint on hover (`button-quiet`).

### Chips
Restrained `999px` pills conveying state, metric currency, or analysis view selection without loud contrast noise.
- **Style:** `12px` 500-weight text (`3px 10px` padding) on semantic soft washes (`primary-soft`, `positive-soft`, `danger-soft`, `warning-soft`, `neutral-muted`).
- **Analysis Sub-View Tabs:** Horizontal wrap-friendly `999px` navigation pills (`7px 14px` padding, `13px` weight `500`) switching from `neutral-surface` with hairline border to high-contrast `ink-primary` (`#1D1D1F`) fill when active.

### Cards / Containers
Single-level flat white work surfaces (`14px` radius, `22px 24px` desktop / `18px 16px` mobile padding) separated strictly by `1px` perimeter hairlines. Nested cards inside cards are prohibited; internal grouped data (like Baseline figures or Live Estimate previews) uses borderless hairline dividers directly inside the parent panel.

### Inputs / Fields
Clean `40px` tall optical-white rectangles (`10px` radius, `8px 12px` padding) edged by `rgba(29, 29, 31, 0.18)`, pairing accessible `#6E6E73` placeholders with synchronized custom `range` sliders (`20px` circular white thumb ringed by `1.5px solid #0066CC`), password visibility toggles, and interactive dashed upload dropzones (`14px` radius, shifting to `#EDF5FF` tint and cobalt dashed stroke during file dragover).

### Navigation
Dual-level hierarchy uniting sticky frosted top bars with persistent desktop sidebar wayfinding (`252px` width). Active links elevate cleanly onto an optical-white rounded `10px` card (`600` weight ink, cobalt `16px` icon, `1px` hairline inset + xs shadow) rather than heavy filled ribbons; mobile viewports (`<= 960px`) slide the sidebar smoothly over the viewport on a translucent scrim.

### Signature Components
- **Unified KPI Strip:** Single rounded white container splitting `3`–`5` metrics horizontally via continuous `1px` vertical internal hairlines (collapsing cleanly into horizontal rules when wrapping at breakpoints), pairing `13px` muted labels with `22px` `tabular-nums` figures colored semantically only for Net Profit and Profit Margin.
- **Interactive Showcase Window:** Framed `18px` macOS-inspired browser frame housing an animated segmented pill control (`240ms cubic-bezier(0.22, 1, 0.36, 1)` sliding thumb) toggling live between a high-DPI HTML5 `<canvas>` trend chart with pointer crosshair scrubber (`sample_data`), categorical margin progress bars + IQR outlier alert, and linear regression forecast metrics computed from the real bundled sample ledger.

## Do's and Don'ts

### Do:
- **Do** enforce `font-variant-numeric: tabular-nums` on every financial figure, metric cell, timestamp, and input field (`numeric` / `.tabular`), right-aligning currency/percentage columns and left-aligning timestamps directly under matching column headers.
- **Do** compose multi-metric summaries as a single Unified KPI Strip divided by `1px` vertical hairlines instead of placing isolated stat cards side by side in grids.
- **Do** use native 16px `1.65px`-stroke monochrome vector icons paired with plain-English Sentence-case labels capped cleanly under `65ch`.
- **Do** test rendered viewports at both `1440px` desktop and `390px` mobile ensuring horizontal document overflow stays zero while wide ledger tables scroll safely inside `.tablewrap`.
- **Do** maintain WCAG AA contrast across every control (`#0066CC` interactive cobalt >= 5.5:1 on white, `#636368` metadata >= 5.4:1 on canvas) and preserve `prefers-reduced-motion`, `prefers-reduced-transparency`, and `prefers-contrast: more` rules.

### Don't:
- **Don't** place tracked uppercase eyebrows, pill kickers, or sequence numbers above section or page headings; let each `h1` and `h2` establish its own visual anchor.
- **Don't** nest bordered/tinted cards inside other cards; separate internal sub-blocks (such as Baseline metrics or Live Estimates) using horizontal `1px` hairlines on the parent surface.
- **Don't** replace SVG iconography with Unicode glyphs or emojis (`🚀`, `✨`, `📊`), and never paint gradient fills onto heading typography.
- **Don't** add `transition: all`, animate `width`/`height` properties on scroll, or ship hover-only states without `@media (hover: hover) and (pointer: fine)` media gating.
- **Don't** fabricate unverified marketing testimonials, cloud claims, pricing tables, or decorative fake sparklines inside Persuade surfaces; every preview figure must correspond to observable local computation.
