from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from pathlib import Path
from typing import Any


_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Clause:
    clause_id: str
    title: str
    tags: tuple[str, ...]
    text: str
    version: str = "1"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Clause":
        return cls(
            clause_id=str(payload["clause_id"]),
            title=str(payload.get("title") or payload["clause_id"]),
            tags=tuple(str(tag) for tag in (payload.get("tags") or ())),
            text=str(payload.get("text") or ""),
            version=str(payload.get("version") or "1"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "clause_id": self.clause_id,
            "title": self.title,
            "tags": list(self.tags),
            "text": self.text,
            "version": self.version,
        }


class ClauseLibrary:
    def get(self, clause_id: str) -> Clause | None:
        raise NotImplementedError

    def by_tag(self, tag: str) -> list[Clause]:
        raise NotImplementedError

    def search(self, query: str, *, tags: list[str] | None = None, limit: int = 5) -> list[Clause]:
        raise NotImplementedError


class InMemoryClauseLibrary(ClauseLibrary):
    def __init__(self, clauses: list[Clause | dict[str, Any]], embedding_client: Any = None):
        self._clauses = [item if isinstance(item, Clause) else Clause.from_dict(item) for item in clauses]
        self._by_id = {item.clause_id: item for item in self._clauses}
        self._embedding_client = embedding_client
        self._embedding_cache: dict[str, list[float]] = {}

    def get(self, clause_id: str) -> Clause | None:
        return self._by_id.get(str(clause_id))

    def by_tag(self, tag: str) -> list[Clause]:
        needle = str(tag).strip().lower()
        return sorted(
            [clause for clause in self._clauses if needle in {item.lower() for item in clause.tags}],
            key=lambda clause: clause.clause_id,
        )

    def search(self, query: str, *, tags: list[str] | None = None, limit: int = 5) -> list[Clause]:
        pool = self._clauses
        if tags:
            expected = {str(tag).strip().lower() for tag in tags}
            pool = [clause for clause in pool if expected.intersection({tag.lower() for tag in clause.tags})]
        if not query.strip():
            return sorted(pool, key=lambda clause: clause.clause_id)[:limit]
        if self._embedding_client is not None:
            return self._search_with_embeddings(pool, query, limit)
        return self._search_deterministically(pool, query, limit)

    def _search_deterministically(self, clauses: list[Clause], query: str, limit: int) -> list[Clause]:
        query_terms = set(_TOKEN_RE.findall(query.lower()))
        ranked = []
        for clause in clauses:
            haystack = " ".join((clause.clause_id, clause.title, " ".join(clause.tags), clause.text)).lower()
            score = sum(1 for token in query_terms if token in haystack)
            ranked.append((score, clause.clause_id, clause))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [clause for score, _, clause in ranked if score > 0][:limit] or [
            clause for _, _, clause in ranked[:limit]
        ]

    def _embedding_for(self, text: str) -> list[float]:
        cached = self._embedding_cache.get(text)
        if cached is not None:
            return cached
        client = self._embedding_client
        vector = client.embed(text) if hasattr(client, "embed") else client(text)
        output = [float(item) for item in vector]
        self._embedding_cache[text] = output
        return output

    def _search_with_embeddings(self, clauses: list[Clause], query: str, limit: int) -> list[Clause]:
        query_vector = self._embedding_for(query)
        ranked = []
        for clause in clauses:
            clause_vector = self._embedding_for(clause.text)
            score = _cosine_similarity(query_vector, clause_vector)
            ranked.append((score, clause.clause_id, clause))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [clause for _, _, clause in ranked[:limit]]


class JSONClauseLibrary(InMemoryClauseLibrary):
    def __init__(self, path: str | Path, embedding_client: Any = None):
        payload = json.loads(Path(path).read_text())
        clauses = payload.get("clauses") if isinstance(payload, dict) else payload
        super().__init__(clauses or [], embedding_client=embedding_client)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)
