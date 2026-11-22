"""The Rulebook's heading and paragraph: written by the model, checked by code.

Code chooses the evidence (regulation passages and stewards' decisions); the
model only words it. A reply is shown only when every source marker, article
number, document number and car number in it is one the evidence holds.
Otherwise, or when no model answers, the computed text stands in, labelled.
A checked reply is cached per question and evidence; a computed one never is.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING

import structlog

from app.api.llm import available_providers, build_chat_llm, is_provider_failure, mark_unavailable, message_text
from app.data.analysis_cache import analysis_cache
from app.services.rulebook_decisions import ARTICLE_CODE, cites
from app.services.rulebook_text import computed_summary, keyword_summary

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

logger = structlog.get_logger()

ANSWER_VERSION = 1
CACHE_KIND = "rulebook_answer"
HEADING_MAX = 120
PARAGRAPH_MAX = 1200
BOLD_MAX = 3

_SYSTEM = (
    "You answer questions about the FIA Formula 1 regulations using only the numbered sources below. "
    'Reply with one JSON object and nothing else: {"heading": "...", "paragraph": "..."}. '
    "heading: one plain sentence of at most 100 characters that answers the question, with no source numbers "
    "and no asterisks. paragraph: at most 120 words; after each claim put the number of the source that "
    "supports it in square brackets, like [1]; cite at least one source. Name an article, document or car "
    "number only as it appears in the sources. Do not add penalties, numbers, names, dates or events the "
    "sources do not state. If the sources do not answer the question, say so plainly in both. You may mark up "
    "to three key phrases with **double asterisks**."
)
_KEYWORD_NOTE = (
    " The regulation text is unavailable: the sources are stewards' decisions found by the question's words. "
    "State only what the decisions say and never paraphrase a rule you have not been shown."
)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")
_MARKER = re.compile(r"\[(\d+)\]")
_ISC_ARTICLE = re.compile(r"Article\s+(\d+(?:\.\d+)+)")
_DOCUMENT = re.compile(r"\b(?:document|doc\.?)\s*(?:no\.?\s*)?(\d{1,3})\b", re.IGNORECASE)
_CAR = re.compile(r"\bcar\s+(?:no\.?\s*)?(\d{1,2})\b", re.IGNORECASE)
_BOLD = re.compile(r"\*\*[^*]+\*\*")


def _normalise(query: str) -> str:
    return " ".join(query.lower().split()).rstrip("?!. ")


def _cache_key(query: str, year: int, articles: list[dict], decisions: dict) -> str:
    evidence = [
        [a["cite"], a["document"], a["page"], hashlib.sha256(a["excerpt"].encode()).hexdigest()] for a in articles
    ]
    evidence += [[item["cite"], item["url"]] for item in decisions["items"]]
    raw = {"q": _normalise(query), "year": year, "mode": decisions["match"], "evidence": evidence}
    return hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()


def _source_blocks(year: int, articles: list[dict], decisions: dict) -> list[str]:
    blocks = [
        f"[{a['cite']}] FIA {year} F1 Regulations, {a['source']}, page {a['page']}, "
        f"articles {', '.join(a['codes'])}:\n{a['excerpt']}"
        for a in articles
    ]
    for item in decisions["items"]:
        driver = f" ({item['driver']})" if item["driver"] else ""
        blocks.append(
            f"[{item['cite']}] Stewards' decision, {item['event']} {year}, document {item['number']}, "
            f"car {item['car']}{driver}, articles {', '.join(item['articles'])}, "
            f'offence: {item["offence"]}, decision: "{item["decision"]}"'
        )
    return blocks


def _messages(query: str, year: int, articles: list[dict], decisions: dict) -> list[BaseMessage]:
    from langchain_core.messages import HumanMessage, SystemMessage

    system = _SYSTEM + (_KEYWORD_NOTE if decisions["match"] == "keyword" else "")
    sources = "\n\n".join(_source_blocks(year, articles, decisions))
    return [SystemMessage(content=system), HumanMessage(content=f"Question: {query}\n\nSources:\n{sources}")]


def parse_reply(text: str) -> tuple[str, str]:
    """The heading and paragraph of a model reply; raises ``ValueError`` when it is not the asked-for JSON."""
    try:
        reply = json.loads(_FENCE.sub("", text.strip()))
    except json.JSONDecodeError as exc:
        raise ValueError("the reply is not JSON") from exc
    heading, paragraph = (reply.get(key) if isinstance(reply, dict) else None for key in ("heading", "paragraph"))
    if not isinstance(heading, str) or not isinstance(paragraph, str):
        raise ValueError("the reply lacks a heading or paragraph")
    if not 1 <= len(heading) <= HEADING_MAX or "[" in heading or "*" in heading:
        raise ValueError("the heading is empty, too long or carries markup")
    if not 1 <= len(paragraph) <= PARAGRAPH_MAX:
        raise ValueError("the paragraph is empty or too long")
    return heading, paragraph


def check_reply(heading: str, paragraph: str, articles: list[dict], decisions: dict) -> list[str]:
    """What the reply claims that the evidence does not hold; empty when it passes.

    A claim is checked only against the rows the answer was built from.
    # shortcut: penalty values, names and times are not checked; upgrade by checking every number against the evidence if a bad one is seen.
    """
    items = decisions["items"]
    cited = {a["cite"] for a in articles} | {item["cite"] for item in items}
    evidence_codes = {code for a in articles for code in a["codes"]} | {c for item in items for c in item["articles"]}
    text = f"{heading} {paragraph}"
    markers = [int(n) for n in _MARKER.findall(paragraph)]
    problems = [f"source [{n}] does not exist" for n in markers if n not in cited]
    if not markers:
        problems.append("no source marker")
    problems += [
        f"article {code} is not in the sources"
        for code in dict.fromkeys(ARTICLE_CODE.findall(text))
        if not any(cites(known, code) for known in evidence_codes)
    ]
    problems += [
        f"Article {number} is not in the decisions"
        for number in dict.fromkeys(_ISC_ARTICLE.findall(text))
        if not any(number in article for item in items for article in item["articles"])
    ]
    problems += [
        f"document {number} is not in the decisions"
        for number in dict.fromkeys(_DOCUMENT.findall(text))
        if int(number) not in {item["number"] for item in items}
    ]
    problems += [
        f"car {number} is not in the decisions"
        for number in dict.fromkeys(_CAR.findall(text))
        if int(number) not in {item["car"] for item in items}
    ]
    spans = len(_BOLD.findall(paragraph))
    if spans > BOLD_MAX or paragraph.count("**") != 2 * spans:
        problems.append("bold spans are unbalanced or too many")
    return problems


def _ask(messages: list[BaseMessage]) -> str | None:
    """The first engine's reply, or ``None`` when no engine could answer."""
    try:
        providers = available_providers()
    except RuntimeError as exc:
        logger.warning("rulebook.answer.llm_failed", provider=None, error_type=type(exc).__name__)
        return None
    for provider in providers:
        try:
            return message_text(build_chat_llm(provider).invoke(messages))
        except Exception as exc:
            logger.warning("rulebook.answer.llm_failed", provider=provider.name, error_type=type(exc).__name__)
            if not is_provider_failure(exc):
                return None
            mark_unavailable(provider, exc)
    return None


def _computed(year: int, articles: list[dict], decisions: dict, why: str) -> dict:
    text = (
        keyword_summary(year, decisions)
        if decisions["match"] == "keyword"
        else computed_summary(year, articles, decisions)
    )
    return {"heading": text["heading"], "paragraph": text["paragraph"], "written_by": "computed", "why": why}


def write_summary(query: str, year: int, articles: list[dict], decisions: dict) -> dict:
    """The answer's heading and paragraph: the model's checked reply, else the computed text."""
    if decisions["match"] == "keyword" and not decisions["items"]:
        return {**keyword_summary(year, decisions)}
    key = _cache_key(query, year, articles, decisions)
    kept = analysis_cache.get(CACHE_KIND, key, ANSWER_VERSION)
    if kept is not None:
        return kept
    reply = _ask(_messages(query, year, articles, decisions))
    if reply is None:
        return _computed(year, articles, decisions, "ai_unavailable")
    try:
        heading, paragraph = parse_reply(reply)
        problems = check_reply(heading, paragraph, articles, decisions)
    except ValueError as exc:
        problems = [str(exc)]
    if problems:
        logger.warning("rulebook.answer.check_failed", problems=problems)
        return _computed(year, articles, decisions, "check_failed")
    answer = {"heading": heading, "paragraph": paragraph, "written_by": "ai", "why": None}
    analysis_cache.put(CACHE_KIND, key, ANSWER_VERSION, answer)
    return answer
