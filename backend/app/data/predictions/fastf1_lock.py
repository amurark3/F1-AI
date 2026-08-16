"""Process-wide lock serialising FastF1 session loads.

FastF1 caches to a shared directory and is not safe to call concurrently — two
threads loading at once can interleave writes and corrupt the cache. Every
module in this package that calls into FastF1 takes this one lock, so it lives
on its own rather than in whichever loader happened to need it first.
"""

from __future__ import annotations

import threading

_fastf1_lock = threading.Lock()
