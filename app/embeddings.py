"""Text embeddings for pgvector (256 dimensions).

hash    Offline, deterministic, multilingual. Hashes words and character n-grams
        (works for English, Nepali/Devanagari and Japanese kana/kanji) into 256 buckets.
        Good enough for "find my similar past mistakes" and keyword-ish retrieval, no API key.
openai  text-embedding-3-small with dimensions=256 (same column size, so you can switch
        providers and run `python -m app.reembed` without a schema change).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.request

DIM = 256
_WORD = re.compile(r"[\wऀ-ॿ぀-ヿ一-鿿]+", re.UNICODE)
_CJK = re.compile(r"[぀-ヿ一-鿿]")


def _bucket(token: str) -> tuple[int, float]:
    h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    n = int.from_bytes(h, "little")
    return n % DIM, (1.0 if (n >> 63) & 1 else -1.0)


def _normalize(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class HashEmbedder:
    name = "hash-256"

    def embed(self, text: str) -> list[float]:
        v = [0.0] * DIM
        text = (text or "").lower()
        for word in _WORD.findall(text):
            feats = [f"w:{word}"]
            if _CJK.search(word):
                feats += [f"c:{word[i:i + n]}" for n in (1, 2) for i in range(len(word) - n + 1)]
            else:
                padded = f"<{word}>"
                feats += [f"g:{padded[i:i + 3]}" for i in range(len(padded) - 2)]
            for f in feats:
                idx, sign = _bucket(f)
                v[idx] += sign * (2.0 if f.startswith("w:") else 1.0)
        return _normalize(v)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class OpenAIEmbedder:
    name = "openai-3-small-256"

    def __init__(self):
        self.key = os.environ["OPENAI_API_KEY"]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": "text-embedding-3-small", "input": texts, "dimensions": DIM}).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/embeddings", data=body,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def make_embedder(provider: str):
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        return OpenAIEmbedder()
    return HashEmbedder()
