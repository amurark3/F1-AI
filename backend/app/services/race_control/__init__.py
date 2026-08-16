"""Race Control overview orchestration and public service facade.

Focused feature services live beside this module. The package keeps the
existing router contract stable while limiting each file to one block of the
command center:

    weather            live forecast card, or an honest blank one
    risk               weather and championship-rival risk register
    workstreams        per-workstream status cards
    strategy_context   strategy dashboard and the numbers behind it
    overview           composes the above into the page payload
"""

from app.services.race_control.overview import build_overview

__all__ = ["build_overview"]
