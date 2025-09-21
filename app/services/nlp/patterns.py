from __future__ import annotations

import hashlib
import logging
import math
import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from app.models import Item

try:  # pragma: no cover - optional dependency
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    SentenceTransformer = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from sklearn.cluster import MiniBatchKMeans  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    MiniBatchKMeans = None  # type: ignore


LOGGER = logging.getLogger(__name__)
_TOKEN_PATTERN = re.compile(r"[a-zA-Z]{3,}")


@dataclass(slots=True)
class EmbeddedItem:
    item_id: int
    text: str
    tokens: List[str]
    vector: List[float]


@dataclass(slots=True)
class PatternCandidate:
    label: str
    top_terms: List[str]
    anomaly_score: float
    item_ids: List[int]
    meta: dict


def _tokenize(text: str) -> List[str]:
    return [match.group(0).lower() for match in _TOKEN_PATTERN.finditer(text or "")]


def _hash_embed(text: str, *, dimensions: int = 16) -> List[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [int.from_bytes(digest[i : i + 2], "big") for i in range(0, dimensions * 2, 2)]
    max_value = max(values) or 1
    return [value / max_value for value in values[:dimensions]]


def embed_items(
    items: Iterable[Item],
    *,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> List[EmbeddedItem]:
    items_list = list(items)
    texts = [(item.title or item.raw_json or "") for item in items_list]
    vectors: List[List[float]]

    if SentenceTransformer is not None:
        try:  # pragma: no cover - heavy dependency path
            model = SentenceTransformer(model_name)
            vectors = model.encode(texts, normalize_embeddings=True).tolist()
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("SentenceTransformer failed, falling back to hash embeddings: %s", exc)
            vectors = [_hash_embed(text) for text in texts]
    else:
        vectors = [_hash_embed(text) for text in texts]

    embedded: List[EmbeddedItem] = []
    for item, text, vector in zip(items_list, texts, vectors):
        tokens = _tokenize(text)
        embedded.append(
            EmbeddedItem(
                item_id=item.id,
                text=text,
                tokens=tokens,
                vector=vector,
            )
        )
    return embedded


def _frequency_label(tokens: Sequence[str]) -> str:
    if not tokens:
        return "pattern"
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return max(counts, key=counts.get)


def _top_terms(all_tokens: Sequence[Sequence[str]], limit: int = 5) -> List[str]:
    scores: dict[str, int] = {}
    for tokens in all_tokens:
        for token in tokens:
            scores[token] = scores.get(token, 0) + 1
    return [term for term, _ in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:limit]]


def _fallback_clusters(items: List[EmbeddedItem], *, min_cluster_size: int) -> List[PatternCandidate]:
    buckets: dict[str, List[EmbeddedItem]] = {}
    for embedded in items:
        label = embedded.tokens[0] if embedded.tokens else _frequency_label([])
        buckets.setdefault(label, []).append(embedded)

    patterns: List[PatternCandidate] = []
    total = len(items) or 1
    for label, bucket in buckets.items():
        if len(bucket) < min_cluster_size:
            continue
        top_terms = _top_terms([b.tokens for b in bucket])
        anomaly = 1.0 - (len(bucket) / total)
        patterns.append(
            PatternCandidate(
                label=label,
                top_terms=top_terms,
                anomaly_score=round(anomaly, 4),
                item_ids=[b.item_id for b in bucket],
                meta={"size": len(bucket)},
            )
        )
    return patterns


def cluster_embeddings(
    items: Sequence[EmbeddedItem],
    *,
    min_cluster_size: int = 2,
    max_clusters: int = 5,
    random_state: int = 42,
) -> List[PatternCandidate]:
    if not items:
        return []
    if len(items) < min_cluster_size:
        return []

    if MiniBatchKMeans is None:
        return _fallback_clusters(list(items), min_cluster_size=min_cluster_size)

    n_clusters = max(1, min(max_clusters, len(items) // min_cluster_size))
    vectors = [item.vector for item in items]

    try:  # pragma: no cover - heavy dependency path
        model = MiniBatchKMeans(n_clusters=n_clusters, random_state=random_state)
        labels = model.fit_predict(vectors)
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("MiniBatchKMeans failed, falling back to naive clustering: %s", exc)
        return _fallback_clusters(list(items), min_cluster_size=min_cluster_size)

    clustered: dict[int, List[EmbeddedItem]] = {}
    for embedded, label in zip(items, labels):
        clustered.setdefault(int(label), []).append(embedded)

    patterns: List[PatternCandidate] = []
    total = len(items)
    for label, bucket in clustered.items():
        if len(bucket) < min_cluster_size:
            continue
        top_terms = _top_terms([b.tokens for b in bucket])
        cluster_label = top_terms[0] if top_terms else f"cluster-{label}"
        anomaly = 1.0 - (len(bucket) / total)
        patterns.append(
            PatternCandidate(
                label=cluster_label,
                top_terms=top_terms,
                anomaly_score=round(anomaly, 4),
                item_ids=[b.item_id for b in bucket],
                meta={"size": len(bucket)},
            )
        )

    return sorted(patterns, key=lambda candidate: candidate.anomaly_score, reverse=True)
