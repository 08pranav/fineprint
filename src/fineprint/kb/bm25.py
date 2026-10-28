"""Okapi BM25, written from scratch (about 30 lines). Used for the knowledge base and for Q&A over clauses."""
from __future__ import annotations

import math
import re
from collections import Counter

TOKEN = re.compile(r"[a-z0-9₹%]+|[ऀ-ॿ]+")
STOP = {
    "the", "a", "an", "of", "to", "and", "or", "in", "on", "for", "is", "are", "be", "will", "shall", "by", "with",
    "at", "as", "this", "that", "any", "if", "it", "its", "you", "your", "from", "which", "such", "per", "all", "may",
    "what", "how", "when", "do", "does", "i", "my", "me", "can", "there", "about",
}


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.n = len(docs)
        self.avgdl = (sum(self.len) / self.n) if self.n else 0.0
        df = Counter(t for d in docs for t in set(d))
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = [0.0] * self.n
        if not self.n or not self.avgdl:
            return out
        for i, tf in enumerate(self.tf):
            norm = self.k1 * (1 - self.b + self.b * self.len[i] / self.avgdl)
            for term in query:
                f = tf.get(term, 0)
                if f:
                    out[i] += self.idf.get(term, 0.0) * f * (self.k1 + 1) / (f + norm)
        return out

    def top(self, query: list[str], k: int = 3, min_score: float = 0.0) -> list[tuple[int, float]]:
        s = self.scores(query)
        ranked = sorted(range(self.n), key=lambda i: s[i], reverse=True)
        return [(i, s[i]) for i in ranked[:k] if s[i] > min_score]
