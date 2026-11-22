"""The Rulebook's computed text: the answer when no AI text can be shown, and the keyword card's.

It uses the same markup as the model's paragraph (``[n]`` source markers,
``**bold**``), so the page has one renderer.
"""

from __future__ import annotations

_LISTED_CODES = 3


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _events(count: int, year: int) -> str:
    return f"{count} {'event' if count == 1 else 'events'} in {year}"


def article_label(codes: list[str] | tuple[str, ...]) -> str | None:
    """ "Article B3.5.3", "Articles B3.5.3 and B3.5.4", "Articles X, Y, Z and 2 more"; ``None`` for none."""
    if not codes:
        return None
    if len(codes) == 1:
        return f"Article {codes[0]}"
    if len(codes) <= _LISTED_CODES:
        return f"Articles {', '.join(codes[:-1])} and {codes[-1]}"
    return f"Articles {', '.join(codes[:_LISTED_CODES])} and {len(codes) - _LISTED_CODES} more"


def _place(article: dict) -> str:
    page = f", page {article['page']}" if article["page"] else ""
    return f"{article['source']}{page}"


def _where(article: dict) -> str:
    label = article_label(article["codes"])
    return f"{label} ({_place(article)})" if label else _place(article)


def _quoted(item: dict) -> str:
    driver = f" ({item['driver']})" if item["driver"] else ""
    return (
        f"the {item['event']}, document {item['number']}, car {item['car']}{driver}: "
        f"**“{item['decision']}”** [{item['cite']}]"
    )


def _decisions_sentence(year: int, articles: list[dict], decisions: dict) -> str:
    events, total, shown = decisions["events"], decisions["total"], len(decisions["items"])
    if decisions["status"] == "unavailable":
        return "The stewards' decisions could not be read just now, so none is cited."
    if decisions["status"] == "none":
        union = list(dict.fromkeys(code for article in articles for code in article["codes"]))
        if not union:
            return "These passages name no article number, so no stewards' decision can be matched to them."
        if events == 0:
            return f"No {year} stewards' decisions have been collected yet."
        return f"None of the stewards' decisions collected from {_events(events, year)} cites {article_label(union)}."
    tail = f" {shown} of them are cited below." if total > shown else ""
    return (
        f"The stewards cited {article_label(decisions['articles'])} in {_plural(total, 'decision')} collected "
        f"from {_events(events, year)}.{tail} At {_quoted(decisions['items'][0])}"
    )


def computed_summary(year: int, articles: list[dict], decisions: dict) -> dict:
    """The heading and paragraph built from the evidence alone, to be shown as computed."""
    first = articles[0]
    label = article_label(first["codes"])
    heading = f"The closest rule: {label}" if label else f"The closest passage: {_place(first)}"
    related = f" Related passages: {' '.join(f'[{a["cite"]}]' for a in articles[1:])}." if articles[1:] else ""
    paragraph = (
        f"The closest passage in the FIA {year} F1 Regulations is **{_where(first)}** [1].{related} "
        f"{_decisions_sentence(year, articles, decisions)}"
    )
    return {"heading": heading, "paragraph": paragraph}


def keyword_summary(year: int, decisions: dict) -> dict:
    """The keyword card's heading and paragraph, marked as computed."""
    total, events, words = decisions["total"], decisions["events"], ", ".join(decisions["words"])
    if total == 1:
        heading = "1 stewards' decision shares words with the question"
    elif total:
        heading = f"{total} stewards' decisions share words with the question"
    else:
        heading = "No stewards' decision shares words with the question"
    if not decisions["words"]:
        paragraph = "The question has no word to search the stewards' decisions by."
    elif events == 0:
        paragraph = f"No {year} stewards' decisions have been collected yet."
    elif not total:
        paragraph = f"None of the stewards' decisions collected from {_events(events, year)} mentions {words}."
    else:
        shown = len(decisions["items"])
        tail = f" {shown} of {total} are cited below." if total > shown else ""
        paragraph = (
            f"Found by the words {words} in the stewards' decisions collected from {_events(events, year)}, "
            f"not matched to an article of the regulations. The closest: at {_quoted(decisions['items'][0])}{tail}"
        )
    return {"heading": heading, "paragraph": paragraph, "written_by": "computed", "why": None}
