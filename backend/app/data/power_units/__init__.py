"""Power-unit element usage, read from the FIA's own race-weekend documents.

Every count, allowance breach and penalty on the power-unit screen comes from
three FIA publications per Grand Prix, never from inference:

* the Technical Delegate's report *PU Elements used per Driver up to now* —
  each car's running total of every element going into the weekend;
* the Technical Delegate's report *New PU Elements for this Competition* —
  each element fitted at this event, with the count before it and the season
  allowance in the FIA's own words;
* the stewards' decision for each car that went beyond its allowance — the
  elements, the session, and the grid drop or pit-lane start it cost.

f1db carries the grid sheet those penalties were applied to, but not the
offence (see :mod:`app.data.f1db_grid`); this package is what supplies it.

None of these documents is published as data — they are PDFs on fia.com — so
the package is split by job: :mod:`.fia_site` discovers and downloads them
politely, :mod:`.sources` keeps the extracted text in the document store,
:mod:`.ingest` is the job that keeps that corpus current, and the parsers
(:mod:`.cover`, :mod:`.usage_report`, :mod:`.new_elements`, :mod:`.decision`,
dispatched by :mod:`.documents`) turn text back into facts at read time. Text
rather than facts is what gets stored, so a parser fix applies to every
document already collected without asking the FIA for anything again.
"""
