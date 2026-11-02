# Interrogation Checklist

Run this before delivering. Every "no" is a fix. Tier 1 must pass. Tier 2 is the design crit — fix everything that's cheap, and anything visible at a glance.

## Tier 1 — must pass

### Purpose

- [ ] Can I state the one takeaway, and is it the first thing a viewer sees?
- [ ] Does the order follow the reader's questions?
- [ ] Is every number correct and consistent throughout — totals add up, the same metric shows the same value everywhere?
- [ ] Is all content real — no lorem, "Metric 1" or placeholder names?

### Legibility and access

- [ ] Are text sizes right for the medium? Slides ≥ 18pt; screen body 14–16px, dense UI 12–13px; print ≥ 9.5pt.
- [ ] Is contrast at least 4.5:1 for text and 3:1 for large text, UI and chart marks?
- [ ] Is meaning ever carried by color alone? It shouldn't be.
- [ ] Does it hold up at the real viewing size — the back of the room, a phone, a printed page?

## Tier 2 — the crit

### Hierarchy

- [ ] Squint: does one element clearly dominate, and is it the right one?
- [ ] Are there about three levels, or does everything compete?
- [ ] Can any emphasis (bold, color, box, icon, badge) be removed without losing the ranking?

### Typography

- [ ] One family (two at most), every size from the scale, three weights at most?
- [ ] Body measure 45–75 characters? Tight line-height on display type, open on body?
- [ ] Display tracking tightened? Small uppercase labels tracked out?
- [ ] Real quotes, dashes and ×, non-breaking spaces before units, no orphaned words in headlines?
- [ ] Numbers in tabular figures and aligned?

### Color

- [ ] A single accent, used only where it means something?
- [ ] Neutrals tinted and drawn from one ramp — no stray grays?
- [ ] Semantic colors (red, green) used only for meaning?
- [ ] Grayscale test: does the hierarchy survive without color?

### Layout and spacing

- [ ] Does everything snap to a grid? Count the distinct left edges — can one go?
- [ ] Is space inside groups smaller than space between groups?
- [ ] Are outer margins generous and consistent?
- [ ] Is there rhythm and variety, or N identical blocks in a row?

### Data and charts

- [ ] Does each chart title state the insight?
- [ ] Is the chart type right for the comparison?
- [ ] Direct labels instead of legends? Gridlines faint or gone? Bar axes starting at zero?
- [ ] Same category, same color, everywhere?
- [ ] Does every number have context — a target, the prior period or a benchmark?

### Detail

- [ ] Are radii, icon style, stroke widths and border weights consistent?
- [ ] Are interactive states (hover, focus, empty, loading, error) designed?
- [ ] Are sources, dates, units, page numbers and last-updated present where they belong?

## Generic-tells sweep

Any of these present without a specific reason → replace it.

- Purple-to-blue gradients, gradient text, glows, glassmorphism, blurred color blobs
- Emoji or icons decorating every heading or bullet; ✨ to signal "AI"
- Everything centered; every section the same width
- Three or four identical cards, or KPI tiles of equal weight
- A rounded card with a drop shadow on every container
- Default chart-library styling: legend box, heavy grid, rainbow series, 3D, pies with 6+ slices
- Topic titles on slides ("Overview", "Results"); bullet-only slides; a "Thank you!" closer
- Office defaults left unexamined: theme fonts everywhere, blue fill on every table header, borders on every cell, gridlines on a presentation sheet
- Pure `#000` on `#FFF`; random grays; more than one accent
- Filler copy: "Unlock the power of…", "seamless", "elevate your…", lorem
- A stock-style hero image with no content reason to exist

## Final tests

- **Five-second test:** after five seconds, what would someone remember? Is it the takeaway?
- **Remove-one test:** delete the least necessary element. Is it better? Repeat until it isn't.
- **Template test:** could this have come from a template gallery? If so, which decision makes it _this_ piece?
- **Director test:** could I defend every choice if asked "why?"
