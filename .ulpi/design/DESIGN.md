---
project: DMARC Pipeline
register: product
aesthetic_direction: technical / utilitarian with industrial signage accents
color_strategy: committed
design_system: bespoke
design_variance: 6
motion_intensity: 4
visual_density: 7
---

# Design Read

**Technical precision meets editorial clarity** — a DMARC operations console that treats email
authentication data like infrastructure telemetry: dense where it matters, calm where it doesn't, and
never decorative for its own sake. Trust is conveyed through information density and typographic
discipline, not through chrome.

# Signature

**The live-updating stat strip** — a horizontal band of monospace numbers that acts as the product's
heartbeat. Every screen loads with a staggered reveal of these numbers counting up. It's the one
moment of orchestrated motion on the page; everything else is quiet. The monospace treatment signals
"this is data you can act on" the way a terminal signals "this is real."

# Color (locked)

| role | OKLCH | hex | use |
|------|-------|-----|-----|
| background | 220 0.02 0.08 | #0d1117 | page ground |
| surface | 220 0.03 0.13 | #161b22 | cards, panels |
| elevated | 220 0.04 0.18 | #1c2333 | hover states, nested surfaces |
| border | 220 0.05 0.28 | #2d3748 | dividers, card edges |
| text | 220 0.05 0.95 | #f0f4fa | primary text |
| muted | 220 0.05 0.65 | #8b98a9 | secondary labels |
| subtle | 220 0.05 0.45 | #5a6675 | timestamps, metadata |
| accent | 70 0.75 0.65 | #e8a33d | CTAs, highlights, pass indicators |
| accent-dim | 70 0.5 0.25 | #3d3426 | accent backgrounds |
| success | 145 0.65 0.6 | #3ce08a | pass, aligned |
| danger | 25 0.85 0.6 | #ff5e4d | fail, rejected, misaligned |
| warning | 50 0.85 0.65 | #e8c44d | partial, quarantine |
| info | 210 0.7 0.6 | #4da6ff | informational |

- Neutrals are tinted toward a cool 220° hue (+0.005 chroma) — never pure gray.
- 60-30-10 distribution: 60% background/surface, 30% text/UI chrome, 10% accent.
- WCAG AA verified: text/background ≈ 12:1, muted/background ≈ 6:1, accent on background ≈ 4.6:1.

# Type (locked)

| role | family | use | notes |
|------|--------|-----|-------|
| display | "JetBrains Mono", ui-monospace, monospace | stat numbers, key metrics | tight tracking, tabular |
| body | "Inter", system-ui, sans-serif | reading, labels | 400/500/600 only |
| utility | "JetBrains Mono", ui-monospace, monospace | data cells, IPs, counts | tabular-nums, 0.85em |

- **Contrast axis:** monospace display + sans body — the data/reading pairing.
- Body measure: 65–75ch for prose, full-width for data tables.
- No type size below 12px. Captions 12, body 14, stat values 28–42, display 56+.

# Scales (locked)

- **spacing:** 4, 8, 12, 16, 24, 32, 48, 64 (4-base, no odd values)
- **radius:** 0, 4, 8 (sharp by default — this is a tool, not a toy)
- **motion:** durations 120/240/400ms, easing `cubic-bezier(0.16, 1, 0.3, 1)` (expo-out, no bounce)
- **prefers-reduced-motion:** all motion collapses to opacity-only 80ms fades

# Voice

- **register:** plain, confident, technical
- **action vocabulary:** Upload → Uploading → Uploaded · Ingest → Ingesting → Ingested · View → Viewed
- **rules:** no buzzwords, no em-dash crutch, no fake precision. Use periods. Use real numbers or none.
- **tone:** "This is what happened with your email. Here's what to do about it."

# Anti-slop checklist (banned)

- No purple/blue glow, no gradient text, no glassmorphism
- No three-equal-cards-in-a-row (use stat strip + ruled tables)
- No centered hero over dark mesh
- No Inter/Roboto as primary (we use JetBrains Mono + Inter)
- No bounce/elastic easing
- No decorative status dots, no fake "trusted by" rows
- No em-dash as stylistic crutch
