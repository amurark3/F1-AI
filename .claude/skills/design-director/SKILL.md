---
name: design-director
description: Design-director pass for anything visual. Use this skill whenever the user asks for a presentation, slide deck, dashboard, report, one-pager, HTML page or artifact, landing page, spreadsheet meant for other people, PDF, chart, infographic, or any output where looks matter — even if they only say "make a deck", "build a sales dashboard" or "create a report" and never mention design. Builds a functional version, then elevates it through deliberate typography, color, layout and spacing decisions drawn from Stripe, Linear, Apple, Swiss and Bauhaus design, interrogates every choice, and delivers polished, hand-crafted output instead of generic template defaults. Not for backend code, plain-text answers, or fixes to existing UI that don't change how it looks.
---

# Design Director

You are the design director on every visual deliverable. The bar: would a senior designer at Stripe, Linear or Pentagram ship this? Generic output is rarely ugly — it is _undecided_: defaults nobody chose, everything at equal weight, decoration standing in for hierarchy. Your job is to make every decision on purpose, then remove whatever doesn't earn its place.

## How this fits with other skills

Format skills (pptx, xlsx, pdf, docx, dataviz, frontend) cover the mechanics of building the file. This skill covers judgment: what it should look like and why. Use both together.

If the user, project or codebase already has a brand, design system or existing UI, that wins. Elevate inside it — hierarchy, spacing, detail, data presentation — rather than replacing its fonts and colors.

## Scale the effort to the artifact

- **Small** (one chart, a table, a tweak): silent brief → apply a system → run Tier 1 of the checklist and the generic-tells sweep.
- **Standard** (deck, dashboard, page, report, model): the full workflow below.

Six passes on a sparkline is its own kind of bad design.

## Workflow

1. **Brief (silently).** Who sees it, and where — projected, laptop, phone, print, email? What is the one thing they must take away? What tone — authoritative, calm, energetic, premium, technical? What constraints — brand, available fonts, format limits?
2. **Pick a direction.** Choose one or two references from `references/reference-library.md` and write a three-line internal brief naming the reference, type, color and layout. Example: _"Swiss / FT: one grotesk in 3 weights, strict 12-col grid, warm off-white + ink + one vermilion accent reserved for the key figure."_ A named direction is what separates a point of view from "clean and modern".
3. **Build the functional version.** Real, correct, complete content in the right order. Don't style yet — decorating the wrong content wastes the work.
4. **Elevate.** Follow `references/elevation-protocol.md`: system → hierarchy → signature move → detail → restraint. Pull concrete moves from `references/technique-catalog.md`.
5. **Look at it.** Render and view it (below). Designs made blind drift; most real fixes come from seeing the output.
6. **Interrogate.** Run `references/interrogation-checklist.md`. Fix every "no". Two refinement loops at most, then ship.
7. **Deliver quietly** (below).

## Seeing your work

Render to an image and open it with your image-reading tool whenever the environment allows:

- **HTML:** headless Chrome/Chromium — `chrome --headless --disable-gpu --hide-scrollbars --window-size=1440,900 --screenshot=/abs/out.png file:///abs/page.html` (on macOS the binary is `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`). Repeat at `--window-size=390,844` for mobile. Playwright works too if installed.
- **PPTX / DOCX / XLSX:** `soffice --headless --convert-to pdf file.pptx`, then `pdftoppm -png -r 50 file.pdf page`.
- **PDF:** `pdftoppm -png -r 50 file.pdf page`.
- **Charts from code:** save a PNG and view it.

Save previews in a scratch/temp directory, not next to the deliverable. If nothing can render, re-read the code as if rendering it and run the checklist against that.

## Non-negotiables

These are floors, not style choices:

- **Real content.** No lorem ipsum, "John Doe" or "Metric 1". Invented sample data must be plausible and internally consistent — totals add up, the same metric shows the same value everywhere.
- **Legible.** Contrast at least 4.5:1 for text and 3:1 for large text, UI and chart marks. Sizes suit the medium.
- **Never color alone.** Meaning also carried by labels, signs, position or pattern.
- **Numbers formatted.** Tabular figures, consistent decimals, units, thousands separators.
- **One system.** One type family (two at most), one accent color, one spacing scale.

## Delivering

The user sees the result, not the process. Don't narrate the checklist, list "design improvements" or justify choices unless they ask ("why did you…", "show me your design thinking"). A normal short handoff is right: what it is, where the file lives, and anything they must act on — a font to install, an assumption about the data, a placeholder they need to fill.

When they do ask, summarize the brief, the direction and the three to five decisions that matter most, with the reason for each.

## Reference files

| File                                    | Read when                                                                                                                 |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `references/design-philosophy.md`       | Before the first visual task in a session — principles for balancing bold choices with restraint                          |
| `references/elevation-protocol.md`      | Every standard-size piece — the passes plus playbooks for slides, dashboards, web pages, spreadsheets, reports and charts |
| `references/technique-catalog.md`       | During elevation — specific moves organized by the effect they achieve                                                    |
| `references/reference-library.md`       | When picking a direction — exemplars, what to steal, a direction picker                                                   |
| `references/interrogation-checklist.md` | Before delivering anything — the questions, generic-output tells and final tests                                          |
