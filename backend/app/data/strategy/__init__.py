"""
Pit Strategy Analysis Engine
=============================
Computes pit strategy breakdowns for any driver or circuit overview using
FastF1 session data.  Includes:

  - Current race stint data (compound, lap ranges, degradation curves)
  - Historical strategy data from last 3 editions of the circuit
  - Undercut/overcut analysis between adjacent drivers
  - Safety car probability from circuit history

Thread safety: All FastF1 session loads are wrapped with the lock in
``session`` to prevent data corruption from concurrent loads.

Layout
------
    session     load a race and extract its stints and pit stops
    history     patterns from previous editions of the circuit
    analysis    undercut/overcut, pit windows, compound mix
    pit         the per-race entry point
    reference   planning numbers for a race that has not run yet
"""

from app.data.strategy.pit import analyze_pit_strategy
from app.data.strategy.reference import circuit_strategy_reference

__all__ = ["analyze_pit_strategy", "circuit_strategy_reference"]
