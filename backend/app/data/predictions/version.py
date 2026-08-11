"""The prediction algorithm's logic version.

Isolated in its own module because the snapshot cache and the backfill script
import it purely to compare stored snapshots against current logic. Reading a
version number should not drag in FastF1, pandas or the scoring model.
"""

from __future__ import annotations

# Bump this whenever the prediction algorithm changes in a way that makes older
# stored snapshots outdated (roster construction, scoring, feature set, etc.).
# The snapshot cache treats any stored result computed under an older version as
# stale and recomputes it, so users never see predictions from superseded logic.
# v3: back-fill the full entry list so drivers without a qualifying time are
#     still predicted instead of being dropped from the grid.
PREDICTION_LOGIC_VERSION = 3
