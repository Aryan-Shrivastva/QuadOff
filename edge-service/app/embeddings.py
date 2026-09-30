from __future__ import annotations

import hashlib
import math
import os
import re
from collections import Counter
from typing import Iterable


class LocalEmbedder:
    """Offline-safe embedding interface.

    The default hashing encoder is deliberately deterministic and needs no
    model download, which makes the demo reproducible on an airplane. The
    adapter loads a locally cached EmbeddingGemma/SentenceTransformer model
    when ``EMBEDDING_BACKEND=embeddinggemma`` (or
    ``sentence-transformers``) is configured.
    """

    def __init__(self, size: int = 384) -> None:
        self.size = size
        self.backend = os.getenv("EMBEDDING_BACKEND", "hashing").lower()
        self.model_name = os.getenv("EMBEDDING_MODEL", "google/embeddinggemma-300m")
        self._model = None
        self._load_error: str | None = None
        if self.backend in {"sentence-transformers", "embeddinggemma"}:
            self._try_load_model()

    @property
    def description(self) -> str:
        if self._model is not None:
            return f"{self.backend}:{self.model_name} ({self.size}d)"
        if self._load_error:
            return f"hashing-fallback ({self._load_error}) ({self.size}d)"
        return f"hashing-local (EmbeddingGemma adapter available) ({self.size}d)"

    def _try_load_model(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self.model_name, local_files_only=True, device="cpu")
            self.size = int(self._model.get_sentence_embedding_dimension())
        except Exception as exc:  # pragma: no cover - optional dependency path
            self._load_error = str(exc).splitlines()[0][:140]
            self._model = None

    def encode(self, text: str, role: str = "document") -> list[float]:
        if self._model is not None:
            encoder = getattr(self._model, "encode_query" if role == "query" else "encode_document", None)
            vector = (encoder(text) if encoder else self._model.encode(text, normalize_embeddings=True)).tolist()
            return [float(value) for value in vector]
        return self._hash_encode(text)

    def _hash_encode(self, text: str) -> list[float]:
        values = [0.0] * self.size
        normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        tokens = normalized.split()
        features: list[str] = tokens[:]
        features.extend(f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1))
        features.extend(normalized[i : i + 3] for i in range(max(0, len(normalized) - 2)))
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.size
            sign = 1.0 if digest[4] % 2 else -1.0
            weight = 1.0 + min(len(feature), 12) / 24
            values[index] += sign * weight
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]


def lexical_score(query: str, text: str) -> float:
    query_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    text_tokens = Counter(re.findall(r"[a-z0-9]+", text.lower()))
    if not query_tokens:
        return 0.0
    overlap = sum(1 for token in query_tokens if token in text_tokens)
    phrase_bonus = 0.2 if query.lower().strip() in text.lower() else 0.0
    return min(1.0, overlap / max(1, len(query_tokens)) + phrase_bonus)


def cosine(left: Iterable[float], right: Iterable[float]) -> float:
    a = list(left)
    b = list(right)
    denominator = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / denominator if denominator else 0.0
