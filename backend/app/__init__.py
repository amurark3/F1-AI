"""F1-AI backend.

structlog's console renderer prints every local variable of a traceback when
``rich`` is installed, and a failed connection put a database password on
screen that way. Importing the package swaps in plain tracebacks for every
process: the server (``setup_logging`` reuses this renderer), the tests and
the scripts that never call ``setup_logging``.
"""

import structlog

_DEFAULT_PROCESSORS = structlog.get_config()["processors"]
_DEFAULT_RENDERER = next(p for p in _DEFAULT_PROCESSORS if isinstance(p, structlog.dev.ConsoleRenderer))

# Same colour choice as structlog's default (terminal, NO_COLOR, FORCE_COLOR); only the tracebacks change.
SAFE_CONSOLE_RENDERER = structlog.dev.ConsoleRenderer(
    colors=_DEFAULT_RENDERER.colors,
    force_colors=_DEFAULT_RENDERER.force_colors,
    exception_formatter=structlog.dev.plain_traceback,
)

structlog.configure(
    processors=[SAFE_CONSOLE_RENDERER if p is _DEFAULT_RENDERER else p for p in _DEFAULT_PROCESSORS],
)
