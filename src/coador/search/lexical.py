"""BM25 search over the sections of a profile.

The index is rebuilt from ``profile.json`` on each use: a few thousand short
documents cost milliseconds to index, so there is nothing to persist, stale or
migrate.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from coador.model import Profile, Section
from coador.redact import sanitize_snippet
from coador.registry import detector_spec

# BM25 with the usual defaults: k1 controls term-frequency saturation, b how
# strongly a long section is penalised.
K1 = 1.5
B = 0.75

# A section that found something is a better answer than one reporting the same
# subject as absent, so it outranks it unless the other match is clearly stronger.
DETECTED_BOOST = 1.35

# Question words carry no signal in a corpus this small, and they let a long
# natural-language query drown the identifier the reader actually meant.
STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "any",
        "are",
        "be",
        "by",
        "can",
        "do",
        "does",
        "find",
        "for",
        "from",
        "get",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "of",
        "on",
        "or",
        "our",
        "show",
        "тhe",
        "that",
        "the",
        "their",
        "there",
        "this",
        "to",
        "use",
        "used",
        "uses",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "you",
        "your",
    }
)

_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def tokenize(text: str, *, drop_stop_words: bool = False) -> list[str]:
    """Split text the way code reads it.

    ``testInstrumentationRunner`` also yields ``test``, ``instrumentation`` and
    ``runner``; ``libs.versions.toml`` and ``:core:network`` split on their
    punctuation, so a query can use either the whole identifier or a word of it.
    """
    tokens: list[str] = []
    for raw in _SPLIT_RE.split(text):
        if not raw:
            continue
        lowered = raw.lower()
        tokens.append(lowered)
        parts = [part.lower() for part in _CAMEL_RE.split(raw) if part]
        if len(parts) > 1:
            tokens.extend(parts)

    if drop_stop_words:
        kept = [token for token in tokens if token not in STOP_WORDS]
        return kept or tokens
    return tokens


@dataclass(frozen=True)
class Hit:
    """One section that matched, with the score that ranked it."""

    layer_id: str
    layer_title: str
    section: Section
    score: float
    matched_terms: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        section = Section.from_dict(self.section.to_dict())
        return {
            "layer": sanitize_snippet(self.layer_id),
            "layer_title": sanitize_snippet(self.layer_title),
            "section": section.id,
            "title": section.title,
            "detected": section.detected,
            "summary": section.summary,
            "score": round(self.score, 3),
            "matched_terms": [sanitize_snippet(term) for term in self.matched_terms],
        }


@dataclass
class _Document:
    layer_id: str
    layer_title: str
    section: Section
    counts: Counter[str] = field(default_factory=Counter)
    length: int = 0


class LexicalRetriever:
    """A BM25 index over the sections of one profile."""

    def __init__(self, profile: Profile) -> None:
        profile = Profile.from_dict(profile.to_dict())
        self._documents = [
            self._document(layer.id, layer.title, s) for layer, s in profile.iter_sections()
        ]
        self._document_frequency: Counter[str] = Counter()
        for document in self._documents:
            self._document_frequency.update(document.counts.keys())
        self._average_length = (
            sum(document.length for document in self._documents) / len(self._documents)
            if self._documents
            else 0.0
        )

    def search(self, query: str, *, limit: int = 10, layer_id: str | None = None) -> list[Hit]:
        """Return the sections that best match ``query``, best first."""
        terms = tokenize(sanitize_snippet(query), drop_stop_words=True)
        if not terms or not self._documents:
            return []

        total = len(self._documents)
        hits: list[Hit] = []

        for document in self._documents:
            if layer_id is not None and document.layer_id != layer_id:
                continue

            score = 0.0
            matched: list[str] = []
            for term in dict.fromkeys(terms):
                frequency = document.counts.get(term, 0)
                if not frequency:
                    continue
                matched.append(term)
                appearances = self._document_frequency[term]
                idf = math.log(1 + (total - appearances + 0.5) / (appearances + 0.5))
                norm = 1 - B + B * (document.length / self._average_length or 1.0)
                score += idf * (frequency * (K1 + 1)) / (frequency + K1 * norm)

            if score > 0:
                if document.section.detected:
                    score *= DETECTED_BOOST
                hits.append(
                    Hit(
                        layer_id=document.layer_id,
                        layer_title=document.layer_title,
                        section=document.section,
                        score=score,
                        matched_terms=tuple(matched),
                    )
                )

        hits.sort(key=lambda hit: (-hit.score, hit.layer_id, hit.section.id))
        return hits[:limit]

    @staticmethod
    def _document(layer_id: str, layer_title: str, section: Section) -> _Document:
        spec = detector_spec(layer_id, section.id)
        # The title and the registry metadata describe what the section is about;
        # they are repeated so that a query naming the topic ranks above a section
        # that merely mentions the word once in an evidence line.
        parts = [
            section.title,
            section.title,
            section.id.replace("_", " "),
            layer_title,
            section.summary,
        ]
        if spec is not None:
            parts.append(spec.description)
            parts.extend(spec.keywords)
            parts.extend(spec.keywords)
        parts.extend(item for item in section.items)
        parts.extend(f"{evidence.path} {evidence.snippet}" for evidence in section.evidence)

        tokens = tokenize(" ".join(parts))
        return _Document(
            layer_id=layer_id,
            layer_title=layer_title,
            section=section,
            counts=Counter(tokens),
            length=len(tokens),
        )


def search(
    profile: Profile, query: str, *, limit: int = 10, layer_id: str | None = None
) -> list[Hit]:
    """Convenience wrapper that builds an index and runs one query."""
    return LexicalRetriever(profile).search(query, limit=limit, layer_id=layer_id)
