"""
Pit Strategy Analysis Engine
=============================
Computes pit strategy breakdowns for any driver or circuit overview from
OpenF1 laps and race control (through the store), ``race_stints`` and the race
classification; no FastF1 request is made.  Includes:

  - Current race stint data (compound, lap ranges, degradation curves)
  - Historical strategy data from last 3 editions of the circuit (2023 onward)
  - Undercut/overcut analysis between adjacent drivers
  - Safety car probability from the circuit's races since 2023, with the
    number of races it is drawn from

An edition that cannot be read is reported as missing, never as an empty one,
and an answer with a missing edition is not cached.

Layout
------
    session     load a race and extract its stints and pit stops
    history     patterns from previous editions of the circuit
    analysis    undercut/overcut, pit windows, compound mix
    pit         the per-race entry point
    reference   which edition plans a race that has not run yet (OpenF1 + Jolpica)
    edition_sources  that edition's stints, classification, pit sheet and pit-lane times
    edition_plan     the edition reduced to the sequences, stops and pit-lane time its finishers ran
"""

from app.data.strategy.pit import analyze_pit_strategy
from app.data.strategy.reference import circuit_strategy_reference

__all__ = ["analyze_pit_strategy", "circuit_strategy_reference"]
