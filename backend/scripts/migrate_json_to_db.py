"""One-time migration: copy local prediction JSON files into the document store.

Run this once after setting ``DATABASE_URL`` so previously-accumulated
prediction snapshots and accuracy history are preserved in Postgres instead of
starting empty.  Safe to re-run — it simply upserts the current file contents.

    cd backend
    python -m scripts.migrate_json_to_db
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import PREDICTION_CACHE_PATH, PREDICTION_HISTORY_PATH
from app.data.store import (
    DOCUMENT_PREDICTION_CACHE,
    DOCUMENT_PREDICTION_HISTORY,
    document_store,
)


def _load(path_str: str) -> dict | None:
    path = Path(path_str)
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return None
    data = json.loads(content)
    return data if isinstance(data, dict) else None


def main() -> None:
    migrated = 0
    for name, path_str in (
        (DOCUMENT_PREDICTION_CACHE, PREDICTION_CACHE_PATH),
        (DOCUMENT_PREDICTION_HISTORY, PREDICTION_HISTORY_PATH),
    ):
        data = _load(path_str)
        if data is None:
            print(f"skip  {name}: no local data at {path_str}")
            continue
        result = document_store.write(name, data)
        if not result.ok:
            print(f"FAIL  {name}: {result.error}")
            continue
        print(f"wrote {name}: {len(json.dumps(data, default=str))} bytes from {path_str}")
        migrated += 1
    print(f"done. {migrated} document(s) migrated.")


if __name__ == "__main__":
    main()
