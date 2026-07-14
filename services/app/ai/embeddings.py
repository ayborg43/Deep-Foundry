"""Dependency-light text embeddings for the self-hosted MVP.

Feature hashing provides stable 1,536-dimensional normalized vectors without
shipping a large model or sending user memory to another provider. The
embedding seam is intentionally one function so a learned local model can
replace it later without changing stored-data callers.
"""

from __future__ import annotations

import hashlib
import math
import re

EMBEDDING_DIMENSIONS = 1536
_TOKEN_RE = re.compile(r"[\w'-]+", re.UNICODE)


def embed_text(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    tokens = [token.casefold() for token in _TOKEN_RE.findall(text)]
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        slot = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[slot] += sign
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector
