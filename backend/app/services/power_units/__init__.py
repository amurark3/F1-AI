"""The power-unit usage screen: each car's allowance, usage, and what it cost.

Built from :mod:`app.data.power_units` — the FIA's own documents — and keyed
by car, because the FIA counts usage per car (Article B8.2.7): a stand-in uses
the allocation of the car they drive. Each car carries the drivers who raced
it, so the screen can show the driver beside the number.
"""

from app.services.power_units.report import build_power_units, clear_cache

__all__ = ["build_power_units", "clear_cache"]
