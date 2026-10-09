"""Self-improving prediction loop.

Closes the feedback loop around the race-finish model:

  1. **Actuals** — proactively records real finishing positions for completed
     races that have a stored prediction (so accuracy is always up to date).
  2. **Post-mortems** — when a race is evaluated, asks the LLM to explain the
     biggest prediction misses: which signal was wrong and what feature might
     have caught it.  These are stored and surfaced, and are a source of ideas
     for the next model iteration.
  3. **Gated retrain** — handled separately by ``app.ml.promote`` (challenger is
     promoted only if it still beats the grid-order baseline).

Everything degrades gracefully: no LLM key → actuals still recorded, post-mortem
skipped; no database → falls back to local JSON via the document store.
"""

from __future__ import annotations

import structlog

from app.data.predictions import (
    _latest_prediction_snapshot,
    _load_prediction_history,
    get_prediction_review,
    record_actual_result,
)
from app.data.store import DOCUMENT_PREDICTION_POSTMORTEMS, document_store

logger = structlog.get_logger()

# A "miss" worth explaining: predicted vs actual differs by at least this many
# positions.
MISS_THRESHOLD = 4


def _parse_key(key: str) -> tuple[int, int] | None:
    try:
        parts = key.strip("()").split(",")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None


def _biggest_misses(predicted: dict, actual: dict, limit: int = 6) -> list[dict]:
    """Per-driver predicted-vs-actual gaps, largest first."""
    misses = []
    for code in set(predicted) & set(actual):
        delta = int(actual[code]) - int(predicted[code])
        if abs(delta) >= MISS_THRESHOLD:
            misses.append(
                {
                    "driver": code,
                    "predicted": int(predicted[code]),
                    "actual": int(actual[code]),
                    "delta": delta,  # positive = finished worse than predicted
                }
            )
    misses.sort(key=lambda m: abs(m["delta"]), reverse=True)
    return misses[:limit]


def _read_postmortems() -> tuple[dict, bool]:
    """Return ``(postmortems, readable)``. See ``_write_postmortem`` for why."""
    read = document_store.read(DOCUMENT_PREDICTION_POSTMORTEMS)
    if not read.ok:
        logger.error("postmortems.read_failed", error=read.error)
        return {}, False
    return (read.payload if isinstance(read.payload, dict) else {}), True


def _load_postmortems() -> dict:
    postmortems, _ = _read_postmortems()
    return postmortems


def get_postmortem(year: int, round_num: int) -> dict | None:
    """Return the stored post-mortem for a race, if one exists."""
    return _load_postmortems().get(f"({year},{round_num})")


def _write_postmortem(key: str, payload: dict) -> None:
    """Merge one post-mortem into the stored document.

    Read-modify-write: an unreadable store means the merge base is unknown, and
    writing anyway would drop every post-mortem that failed to load.
    """
    store, readable = _read_postmortems()
    if not readable:
        logger.error("postmortems.write_skipped_unreadable_store", key=key)
        return

    store[key] = payload
    result = document_store.write(DOCUMENT_PREDICTION_POSTMORTEMS, store)
    if not result.ok:
        logger.error("postmortems.write_failed", key=key, error=result.error)


def _postmortem_prompt(year: int, round_num: int, review: dict, misses: list[dict]) -> str:
    miss_lines = "\n".join(
        f"- {m['driver']}: predicted P{m['predicted']}, finished P{m['actual']} "
        f"({'+' if m['delta'] > 0 else ''}{m['delta']})"
        for m in misses
    )
    return (
        f"You are an F1 data scientist reviewing our race-finish model after the "
        f"{year} Round {round_num}.\n\n"
        f"Headline accuracy: winner {'correct' if review.get('winner_correct') else 'wrong'} "
        f"(predicted {review.get('predicted_winner')}, actual {review.get('actual_winner')}); "
        f"avg position error {review.get('avg_position_error')}; "
        f"top-3 {review.get('top3_correct')}/{review.get('top3_possible')}.\n\n"
        f"Biggest misses (predicted vs actual):\n{miss_lines or '- none beyond threshold'}\n\n"
        f"In 3-4 sentences: explain the most likely reasons for the misses (grid vs "
        f"race pace, reliability/DNF, safety car, weather, strategy), and name ONE "
        f"concrete feature or signal that might have caught them. Be specific and terse."
    )


def generate_miss_postmortem(year: int, round_num: int, *, force: bool = False) -> dict | None:
    """Create (and store) an LLM post-mortem for a completed, evaluated race.

    Returns the post-mortem dict, or None if the race isn't evaluable yet or the
    LLM is unavailable.  Skips regeneration unless ``force`` is set.
    """
    key = f"({year},{round_num})"
    if not force and get_postmortem(year, round_num):
        return get_postmortem(year, round_num)

    review = get_prediction_review(year, round_num)  # also records actuals
    if not review.get("evaluated"):
        return None

    history = _load_prediction_history()
    entry = history.get(key) or {}
    predicted = _latest_prediction_snapshot(entry).get("predicted_positions") or {}
    actual = entry.get("actual_positions") or {}
    misses = _biggest_misses(predicted, actual)

    try:
        from datetime import datetime, timezone

        from langchain_core.messages import HumanMessage

        from app.api.llm import build_chat_llm

        llm = build_chat_llm()
        response = llm.invoke([HumanMessage(content=_postmortem_prompt(year, round_num, review, misses))])
        summary = str(response.content).strip()
    except Exception as exc:
        logger.warning("self_improvement.postmortem_llm_unavailable", error=str(exc))
        return None

    payload = {
        "year": year,
        "round": round_num,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "winner_correct": review.get("winner_correct"),
        "avg_position_error": review.get("avg_position_error"),
        "misses": misses,
        "summary": summary,
    }
    _write_postmortem(key, payload)
    logger.info("self_improvement.postmortem_written", key=key, misses=len(misses))
    return payload


def run_self_improvement_pass(year: int) -> dict:
    """Record actuals and generate missing post-mortems for a season's races.

    Intended to run after each race weekend (scheduled job or background loop).
    """
    history = _load_prediction_history()
    recorded = 0
    postmortems = 0
    for key, entry in list(history.items()):
        parsed = _parse_key(key)
        if not parsed or parsed[0] != year:
            continue
        y, r = parsed
        if entry.get("predicted_positions") and not entry.get("actual_positions"):
            record_actual_result(y, r)
            recorded += 1
        if not get_postmortem(y, r) and generate_miss_postmortem(y, r):
            postmortems += 1

    summary = {"year": year, "actuals_recorded": recorded, "postmortems_generated": postmortems}
    logger.info("self_improvement.pass_complete", **summary)
    return summary


if __name__ == "__main__":
    from datetime import datetime, timezone

    print(run_self_improvement_pass(datetime.now(timezone.utc).year))
