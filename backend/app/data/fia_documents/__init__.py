"""The FIA's race-weekend documents: found, downloaded and read, politely.

fia.com publishes every stewards' decision, classification, grid and report
of a Grand Prix as a PDF on the event's page, with no feed or API. This
package holds what every reader of those documents shares: :mod:`.site`
discovers and downloads them within the robots.txt crawl delay, :mod:`.listing`
reads an event page against the documents already held, :mod:`.rescission`
notices the ones the FIA takes back, and :mod:`.text` cleans up the text pypdf
extracts. :mod:`.document` is one collected document.
"""
