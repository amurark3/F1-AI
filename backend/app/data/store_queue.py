"""Writes the Postgres document store holds through an outage.

A write that cannot reach the database is kept here and retried on the next
successful contact, so a transient outage self-heals without an operator. What
is kept decides whether the retry is safe once another process has written in
the meantime:

* ``update`` keeps its *changes*, which are re-applied to the latest document;
* ``write`` keeps a whole document together with the version it was built from,
  so the store can refuse to replay it over a newer write.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.data.store_types import DocumentChange


def compose(changes: tuple[DocumentChange, ...]) -> DocumentChange:
    """One change that applies ``changes`` in order (queued ones first)."""

    def composed(current: dict | None) -> dict:
        document = changes[0](current)
        for change in changes[1:]:
            document = change(document)
        return document

    return composed


class PendingWrites:
    """The queued whole documents and changes, by document name. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._documents: dict[str, tuple[dict, int | None]] = {}
        self._changes: dict[str, tuple[DocumentChange, ...]] = {}

    def names(self) -> tuple[str, ...]:
        """Every document with something queued, sorted."""
        with self._lock:
            return tuple(sorted({*self._documents, *self._changes}))

    def snapshot(self) -> tuple[dict[str, tuple[dict, int | None]], dict[str, tuple[DocumentChange, ...]]]:
        """Copies of what is queued now: whole documents, then changes."""
        with self._lock:
            return dict(self._documents), dict(self._changes)

    # -- whole documents (``write``) ----------------------------------------
    def queue_document(self, name: str, payload: dict, seen: int | None) -> None:
        """Hold ``payload``, built from version ``seen`` (``None``: never read)."""
        with self._lock:
            self._documents = {**self._documents, name: (payload, seen)}

    def drop_document(self, name: str) -> None:
        with self._lock:
            self._documents = {key: value for key, value in self._documents.items() if key != name}

    # -- changes (``update``) -----------------------------------------------
    def take_changes(self, name: str) -> tuple[DocumentChange, ...]:
        """Remove and return the changes queued for ``name``."""
        with self._lock:
            taken = self._changes.get(name, ())
            self._changes = {key: value for key, value in self._changes.items() if key != name}
            return taken

    def queue_changes(self, name: str, changes: tuple[DocumentChange, ...]) -> None:
        """Hold ``changes`` ahead of any queued for ``name`` since they were taken."""
        with self._lock:
            self._changes = {**self._changes, name: (*changes, *self._changes.get(name, ()))}

    def drop_changes(self, name: str, count: int) -> None:
        """Drop the first ``count`` changes of ``name``; later ones were queued since."""
        with self._lock:
            rest = self._changes.get(name, ())[count:]
            others = {key: value for key, value in self._changes.items() if key != name}
            self._changes = {**others, name: rest} if rest else others
