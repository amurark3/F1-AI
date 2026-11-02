# Technique Catalog

Specific visual moves, grouped by the effect they achieve. Pick moves for the effect you need — never apply them all.

**Contents:** Establish hierarchy · Create focus · Create calm and order · Add rhythm and variety · Depth without decoration · Make numbers legible · Feel premium · Feel editorial · Add warmth · Make it memorable · Make data speak · Polish details

## Establish hierarchy

- **Scale jump.** A primary element at 2× or more its neighbor reads as confident; a 1.1× step reads as indecisive.
- **Weight instead of size.** Use 600 against 400 at the same size for label/value pairs in dense UI.
- **Three text tones:** primary (~90% ink), secondary (~60%) and tertiary (~45%). Any tone that carries information must still reach 4.5:1 contrast.
- **Eyebrow label.** A small uppercase label above a heading: 11–12px, +0.06–0.1em tracking, secondary color.
- **Position.** Top-left is read first in left-to-right languages; in a sparse composition, so is the optical center.

## Create focus

- **Highlight and mute.** Color only the thing that matters and leave everything else in neutral gray.
- **Isolation.** Give the key element more surrounding space than anything else.
- **Single accent rule.** The accent covers at most 5–10% of the surface, so wherever it appears it means "look here".
- **Annotation.** A short label with a thin leader line pointing at the exact data point.

## Create calm and order

- **Strict grid.** Every edge snaps to a column or gutter.
- **Fewer alignment lines.** Count the distinct left edges and cut them to 2–3.
- **Proximity over boxes.** Replace borders with spacing. Use a hairline (1px, ~8–12% ink) only where spacing can't separate.
- **Vertical rhythm.** All spacing comes from the scale, and section gaps are 2–3× block gaps.
- **Tinted neutrals.** Warm `#F7F6F3` behind `#1C1B19` ink, or cool `#F6F7F9` behind `#14161A` — never pure `#FFF` and `#000`.

## Add rhythm and variety

- **Alternate density.** Follow a dense section with an airy statement.
- **Alternate width and alignment.** For example: a full-bleed band, then a narrow text column, then a wide grid.
- **Vary deck layouts.** Rotate among statement, big number, chart, comparison, quote and image slides.
- **Repeat a motif.** One consistent detail ties the piece together — section markers like "01", or a short accent rule above each heading.

## Depth without decoration

- **Surface steps.** Background → surface → raised, each a small lightness step (2–4% L), instead of shadows.
- **Layered soft shadow,** for floating elements only: `0 1px 2px rgb(0 0 0 / .06), 0 4px 12px rgb(0 0 0 / .06)`.
- **Top-edge hairline on dark surfaces:** `inset 0 1px 0 rgb(255 255 255 / .06)`.
- **Overlap.** Let one element cross a boundary — a number over a rule, an image over a section edge.

## Make numbers legible

- **Tabular figures:** `font-variant-numeric: tabular-nums`. In Office, pick fonts whose figures are tabular by default.
- **Alignment.** Right-align numbers and line up the decimals.
- **Abbreviate consistently.** Write $1.2M and $840K, not a mix of $1,200,000 and $0.84M.
- **Subordinate units.** Set units at ~60% of the number's size in a secondary color.
- **Deltas** carry a sign, an arrow and a direction color: "▲ 4.2% vs last month".
- **Precision matches the decision.** Revenue to one decimal in millions, not to the cent.

## Feel premium

- **Generous margins** — 1.5–2× what first feels necessary.
- **Display type:** tracking tightened to −0.02 to −0.04em at 40px and above, in light-to-regular weights.
- **Palette:** muted, with one rich accent; near-black in place of saturated colors.
- **Fine detail:** 1px hairlines, small-caps labels, exact alignment.
- **Imagery:** fewer images, shown larger.

## Feel editorial

- **Type pairing:** serif display with sans body, or the reverse — e.g. Newsreader or Source Serif with Inter or IBM Plex Sans.
- **Editorial devices:** large section numerals, pull quotes, captions in smaller italic or sans.
- **Asymmetric columns:** a narrow margin column for notes beside a wide text column.
- **Rules as structure**, newspaper-style horizontal lines.

## Add warmth

- **Warm neutrals** — cream, stone, sand — instead of cool grays.
- **A humanist or characterful typeface,** used for display only.
- **Specific, conversational copy** in microcopy and chart titles.
- **One hand-drawn annotation or illustration.**
- **Keep warmth out of data-dense areas.**

## Make it memorable — signature moves (pick one)

- **Giant number.** The headline metric at 6–10× body size.
- **Full-bleed color field.** One slide or section in solid accent with a single statement.
- **Dramatic headline.** Display type at `clamp(48px, 8vw, 128px)` with 0.95–1.05 leading.
- **Hard crop.** An image or chart cropped tight and bleeding off the edge.
- **Rule system.** A thick (4–8px) accent rule anchoring the composition, Swiss-style.
- **Monochrome plus one.** Everything grayscale except the key insight.
- **Index numerals.** Oversized "01 / 02 / 03" as structural graphics.

## Make data speak

- **Direct annotation:** insight titles, direct labels, notes at turning points.
- **Small multiples** with shared scales instead of one spaghetti chart.
- **Sparklines** inline in tables and KPI tiles.
- **Reference lines** for target and average, in a dashed neutral.
- **Sort bars by value** unless the order is inherent, like time or sequence.
- **Bullet charts** instead of gauges.

## Polish details

- **Typographic punctuation:** “ ” ’ — – × …, and a non-breaking space between a number and its unit.
- **Line wrapping:** `text-wrap: balance` on headings and `pretty` on paragraphs; no single-word last lines in headlines.
- **Nested radii.** Inner radius = outer radius − padding.
- **Optical alignment.** Hang quote marks and bullets into the margin; nudge icons until they _look_ centered.
- **One icon set:** one stroke width, sized to the cap height of the adjacent text.
- **Designed focus rings:** a 2px accent outline at 2px offset.
- **Footer details:** source, date, page number, last updated.
