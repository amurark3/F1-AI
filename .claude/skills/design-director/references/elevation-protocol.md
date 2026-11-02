# Elevation Protocol

A systematic refinement process. Run the passes in order; each ends with an exit test. Then apply the playbook for the medium.

**Contents:** Passes 0–7 · Playbooks: Slides · Dashboards · Web pages and HTML artifacts · Spreadsheets · Reports and PDFs · Charts

## The passes

### Pass 0 — Brief

Pin down the audience, the medium and viewing conditions, the one takeaway, the tone and the constraints.
_Exit:_ you can state the takeaway in one sentence.

### Pass 1 — Functional

Complete, correct, real content, ordered the way the reader's questions arrive.
_Exit:_ with all styling stripped, a reader would still get the takeaway.

### Pass 2 — System

Define the tokens before styling any individual element.

- **Type:** one family (two at most) and 2–3 weights. Build 4–6 sizes from a ratio — about 1.2–1.25 for dense UI, 1.333–1.5 for slides and editorial.
- **Color:**
  - a tinted neutral ramp, not pure black and white
  - one accent
  - semantic colors (good, bad, warning) kept separate from the accent
  - a chart palette
- **Space:** a 4 or 8 base with 5–7 steps.
- **Grid:** columns, gutters and margins.
  - Slides: 12 columns and at least 5% outer margin.
  - Pages: content width around 1120–1200px, text measure 60–75 characters.
- **Shape:** one radius scale (or none) and one elevation language — borders or shadows, not both.

_Exit:_ no value in the output comes from outside the system.

### Pass 3 — Hierarchy and composition

- Rank every element as primary, secondary or tertiary.
- Express rank through size, weight, contrast, position and space — before color.
- Group related items by proximity and align everything to the grid.
- Give the piece one entry point and a reading path: a Z pattern for sparse layouts, an F pattern for dense ones.

_Exit:_ blur or squint at it. The primary element is still obvious and the groups still read as groups.

### Pass 4 — Signature move

Choose one bold move (see "Make it memorable" in the technique catalog) and spend it on the primary content.
_Exit:_ you can name the move, and it amplifies the takeaway instead of competing with it.

### Pass 5 — Detail

Cover:

- typography: punctuation, tracking, numerals, line wrapping
- optical alignment and number formatting
- consistent icons
- interactive states: hover, focus, empty, loading, error
- captions, sources, timestamps, page numbers

_Exit:_ the Detail section of the checklist passes.

### Pass 6 — Restraint

Remove 10–20%. For each element, ask what breaks without it. Common cuts:

- borders that duplicate whitespace
- legends and labels that repeat each other
- decorative icons
- a second accent color or an extra font weight
- shadows on flat content
- subtitles that restate the title
- gridlines

_Exit:_ nothing left can go without loss.

### Pass 7 — Verify

Render and look (see SKILL.md), run the interrogation checklist, fix, re-render. Two loops at most.

## Playbooks

### Slides and decks

- **Titles are takeaways.** Write "EMEA grew 31%, driven by renewals", not "EMEA Results". Reading only the titles should tell the whole story (the ghost-deck test).
- **One idea per slide.** If a slide needs two ideas, make two slides.
- **Sizes:** body at least 18pt (24pt or more if projected), titles 28–40pt, a hero number at 100pt or more.
- **Rhythm:** keep the title position, margins and grid identical on every slide. Vary the layout type on purpose — statement, big number, chart, comparison, image.
- **Replace bullets with structure:** 2–3 column comparisons, numbered steps, a simple diagram, or one strong sentence.
- **Charts:** highlight the series that matters, gray the rest and annotate the key point on the chart itself.
- **Open and close:** lead with the answer (Minto). End on the ask or the next step, not "Thank you / Questions?".
- **Section dividers** carry the signature move — a color field or a giant numeral.
- **Fonts:** if you don't know the recipients' machines, use cross-platform-safe faces and create distinction through size, weight and space. Embed fonts when the tool supports it.

### Dashboards

- **Start from decisions.** List the 3–5 questions the dashboard answers and lay it out in that order, with the most important at top left.
- **Flow:** headline KPIs → trends → breakdowns → detail table. Overview first, detail on demand.
- **KPI tiles are not equal.** Make the lead metric larger.
- **Every number needs context:** a target, the prior period, or a sparkline. A number without a comparison is trivia.
- **Color is semantic only:**
  - the accent marks selection and focus
  - red/green (or colorblind-safe blue/orange plus signs) marks good and bad
  - everything else is neutral
- **Consistency:** direct labels instead of legends, the same time range and units in every panel, and a visible "last updated".
- **Density follows the user.** Operators want compact rows (32–36px) and 12–13px text; executives want fewer, bigger numbers.
- **Tables:** right-aligned tabular numbers, a sticky header, light row hover, and zebra stripes or row rules but not both.
- **Design every state:** empty, loading and error.

### Web pages and HTML artifacts

- **Lead with type.** The hero should rest on typography and one clear action, not stock imagery.
- **Vary section rhythm** — width, density, alignment. Six identical card grids in a row is the template look.
- **Use asymmetry on purpose**, such as a 5/7 column split.
- **Spacing steps with hierarchy:** the gap between sections is much larger than between blocks, which is larger than between elements.
- **States:** design hover, focus-visible, active and disabled. Animate only transform and opacity, over 150–250ms, and honor `prefers-reduced-motion`.
- **Responsive:** check at about 390px and 1440px.
- **Fonts:** load a web font if the environment allows. Otherwise choose a system stack deliberately (`ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif`).
- **Self-contained artifacts:** inline the CSS and avoid external dependencies that may be blocked.

### Spreadsheets (for other people)

- **Order:** outputs and summary first (first sheet, top left); inputs and raw data later.
- **Number formats:**
  - thousands separators and consistent decimals per column
  - percentages to one decimal
  - finance negatives in parentheses
  - units in headers, e.g. "Revenue ($K)"
- **Alignment:** text left, numbers right, each header aligned with its data.
- **Headers:** bold with a bottom border and at most a light fill. Freeze the header row and the ID column.
- **Presentation sheets:** turn gridlines off and use thin horizontal rules between row groups.
- **Modeling convention:** blue font for hard-coded inputs, black for formulas, green for links to other sheets.
- **Hygiene:** fit column widths, keep merged cells out of data ranges, and use conditional formatting only where it answers a question (e.g. variance over 10%).

### Reports and PDFs

- **Page:** a page grid with generous margins (18–25mm or more), a 60–75 character measure, 10–11.5pt body and about 1.4–1.5 line-height.
- **Order:** an executive summary first — conclusions and numbers — then the evidence.
- **Furniture:**
  - a consistent heading scale
  - running headers and footers with the title and page numbers
  - numbered figures whose captions state the finding
- **Callouts:** pull out key numbers or quotes sparingly, in the margin or as callouts.
- **Pagination:** no widows or orphans, figures stay with their captions, tables never split mid-row.

### Charts (anywhere)

- **Match chart to comparison:**
  - over time → line
  - ranking → sorted horizontal bar
  - part-to-whole with 3 parts or fewer → stacked bar or simple donut
  - distribution → histogram or dot plot
  - relationship → scatter
  - never 3D; rarely pie
- **Titles:** the title states the insight; the subtitle gives the metric and unit.
- **Strip furniture:** the chart border, background fill, heavy gridlines (keep faint horizontal ones or none) and the legend (label lines and bars directly).
- **Emphasis:** one series in the accent, the rest in neutral gray. Annotate turning points ("Price change, Mar 3").
- **Axes:** bar axes start at zero; line axes needn't.
- **Consistency:** each category keeps the same color across every chart in the piece.
