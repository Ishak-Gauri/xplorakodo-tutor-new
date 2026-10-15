"""JLPT level estimator: a trained character n-gram classifier + a JLPT lexicon.

Model     multinomial logistic regression (softmax) over hashed character 1-3 grams, trained with
          mini-batch Adam in numpy. Small (~2.6 MB), CPU-only, deterministic given a seed.
Lexicon   N5-N1 vocabulary (7.9k words) and kanji (2.2k) lists; greedy longest-match over the text.
Estimator combines both: known words/kanji decide when the text is well covered, the model fills in
          for unseen words, and the result explains itself (hardest words found, per-level probabilities).
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

LEVELS = ["N5", "N4", "N3", "N2", "N1"]
DATA = Path(__file__).resolve().parent.parent.parent / "data"
DIM = 1 << 15
_JA = re.compile(r"[぀-ヿ一-鿿々ー]")
_KANJI = re.compile(r"[一-鿿々]")


def _h(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "little") % DIM


_KMETA: dict | None = None


def kanji_meta() -> dict:
    """KANJIDIC newspaper frequency rank, stroke count and school grade per kanji (no JLPT labels)."""
    global _KMETA
    if _KMETA is None:
        path = DATA / "kb" / "kanji_meta.json.gz"
        _KMETA = json.loads(gzip.open(path, "rt", encoding="utf-8").read()) if path.exists() else {}
    return _KMETA


def _bucket(v, edges):
    if v is None:
        return "none"
    for e in edges:
        if v <= e:
            return str(e)
    return "max"


def features(text: str) -> tuple[np.ndarray, np.ndarray]:
    """Sparse (indices, values) for hashed character 1-3 grams, L2-normalised. Only Japanese characters count."""
    t = "".join(ch for ch in (text or "") if _JA.match(ch))
    t = f"^{t}$" if t else ""
    counts: dict[int, float] = {}
    for n in (1, 2, 3):
        for i in range(len(t) - n + 1):
            g = t[i:i + n]
            if g in ("^", "$"):
                continue
            k = _h(f"{n}:{g}")
            counts[k] = counts.get(k, 0.0) + 1.0
    # coarse length / script features help separate kana-only basic words from dense kanji text
    nk = len(_KANJI.findall(t))
    for name, on in (("len_short", len(t) <= 4), ("len_long", len(t) > 12), ("kanji_0", nk == 0),
                     ("kanji_1", nk == 1), ("kanji_2+", nk >= 2), ("kanji_dense", nk > 0.5 * max(1, len(t) - 2))):
        if on:
            counts[_h(f"f:{name}")] = counts.get(_h(f"f:{name}"), 0.0) + 1.0
    # kanji statistics: rarer, more complex, later-grade kanji -> harder levels
    meta = kanji_meta()
    ks = [meta.get(ch) for ch in t if _KANJI.match(ch)]
    if ks:
        freqs = [k[0] if k and k[0] else 3000 for k in ks]
        strokes = [k[1] if k and k[1] else 15 for k in ks]
        grades = [k[2] if k and k[2] else 10 for k in ks]
        for name, v, edges in (("fmax", max(freqs), (100, 300, 600, 1000, 1500, 2000, 2500)),
                               ("fmin", min(freqs), (100, 300, 600, 1000, 1500, 2000, 2500)),
                               ("smax", max(strokes), (4, 7, 10, 13, 16, 20)),
                               ("gmax", max(grades), (1, 2, 3, 4, 5, 6, 8, 9)),
                               ("gmin", min(grades), (1, 2, 3, 4, 5, 6, 8, 9))):
            key = _h(f"m:{name}:{_bucket(v, edges)}")
            counts[key] = counts.get(key, 0.0) + 2.0
    if not counts:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)
    idx = np.fromiter(counts.keys(), dtype=np.int64)
    val = np.fromiter(counts.values(), dtype=np.float32)
    return idx, val / np.linalg.norm(val)


@dataclass
class SoftmaxModel:
    W: np.ndarray = field(default_factory=lambda: np.zeros((DIM, len(LEVELS)), dtype=np.float32))
    b: np.ndarray = field(default_factory=lambda: np.zeros(len(LEVELS), dtype=np.float32))
    meta: dict = field(default_factory=dict)

    def logits(self, idx: np.ndarray, val: np.ndarray) -> np.ndarray:
        return (self.W[idx] * val[:, None]).sum(axis=0) + self.b if len(idx) else self.b.copy()

    def predict_proba(self, text: str) -> np.ndarray:
        z = self.logits(*features(text))
        z = z - z.max()
        p = np.exp(z)
        return p / p.sum()

    # ---------------- training
    @classmethod
    def train(cls, texts: list[str], labels: list[int], epochs: int = 3, lr: float = 0.05, l2: float = 1e-4,
              batch: int = 64, seed: int = 7, class_weight: bool = True, log=print) -> "SoftmaxModel":
        rng = np.random.default_rng(seed)
        feats = [features(t) for t in texts]
        y = np.asarray(labels)
        cw = np.ones(len(LEVELS), dtype=np.float32)
        if class_weight:
            counts = np.bincount(y, minlength=len(LEVELS)).astype(np.float32)
            cw = (counts.sum() / (len(LEVELS) * np.maximum(counts, 1))).astype(np.float32)
        m = cls()
        mW, vW = np.zeros_like(m.W), np.zeros_like(m.W)
        mb, vb = np.zeros_like(m.b), np.zeros_like(m.b)
        b1, b2, eps, step = 0.9, 0.999, 1e-8, 0
        order = np.arange(len(feats))
        for ep in range(epochs):
            rng.shuffle(order)
            loss_sum = 0.0
            for s in range(0, len(order), batch):
                ids = order[s:s + batch]
                gW: dict[int, np.ndarray] = {}
                gb = np.zeros_like(m.b)
                for i in ids:
                    idx, val = feats[i]
                    z = m.logits(idx, val)
                    z = z - z.max()
                    p = np.exp(z)
                    p /= p.sum()
                    loss_sum += -np.log(p[y[i]] + 1e-12) * cw[y[i]]
                    d = p.copy()
                    d[y[i]] -= 1.0
                    d *= cw[y[i]]
                    gb += d
                    for k, v in zip(idx, val):
                        g = gW.get(int(k))
                        gW[int(k)] = (g if g is not None else 0) + v * d
                step += 1
                n = len(ids)
                keys = np.fromiter(gW.keys(), dtype=np.int64)
                G = np.stack([gW[int(k)] for k in keys]) / n + l2 * m.W[keys]
                # lazy (sparse) Adam on touched rows
                mW[keys] = b1 * mW[keys] + (1 - b1) * G
                vW[keys] = b2 * vW[keys] + (1 - b2) * G * G
                mhat = mW[keys] / (1 - b1 ** step)
                vhat = vW[keys] / (1 - b2 ** step)
                m.W[keys] -= (lr * mhat / (np.sqrt(vhat) + eps)).astype(np.float32)
                gb /= n
                mb = b1 * mb + (1 - b1) * gb
                vb = b2 * vb + (1 - b2) * gb * gb
                m.b -= (lr * (mb / (1 - b1 ** step)) / (np.sqrt(vb / (1 - b2 ** step)) + eps)).astype(np.float32)
            log(f"  epoch {ep + 1}/{epochs}  loss {loss_sum / len(order):.4f}")
        return m

    # ---------------- persistence
    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        rows = np.flatnonzero(np.abs(self.W).sum(axis=1) > 0)
        np.savez_compressed(buf, rows=rows, W=self.W[rows].astype(np.float16), b=self.b,
                            meta=np.frombuffer(json.dumps(self.meta).encode(), dtype=np.uint8))
        return buf.getvalue()

    @classmethod
    def from_bytes(cls, data: bytes) -> "SoftmaxModel":
        z = np.load(io.BytesIO(data))
        m = cls()
        m.W[z["rows"]] = z["W"].astype(np.float32)
        m.b = z["b"].astype(np.float32)
        m.meta = json.loads(bytes(z["meta"]).decode())
        return m


class Lexicon:
    """JLPT word and kanji lists with greedy longest-match lookup."""

    def __init__(self, words: dict[str, int], kanji: dict[str, int]):
        self.words, self.kanji = words, kanji
        self.maxlen = max((len(w) for w in words), default=1)

    @classmethod
    def from_bundled(cls) -> "Lexicon":
        words, kanji = {}, {}
        for name, target in (("vocab", words), ("kanji", kanji)):
            path = DATA / "kb" / f"{name}.jsonl.gz"
            if path.exists():
                with gzip.open(path, "rt", encoding="utf-8") as f:
                    for line in f:
                        r = json.loads(line)
                        lv = LEVELS.index(r["level"])
                        key = r["title"]
                        target[key] = min(lv, target.get(key, lv))
        return cls(words, kanji)

    def analyze(self, text: str) -> list[tuple[str, int, str]]:
        """[(token, level_index, 'word'|'kanji')] for known words; leftover kanji are looked up singly."""
        out, i, t = [], 0, text or ""
        while i < len(t):
            if not _JA.match(t[i]):
                i += 1
                continue
            for n in range(min(self.maxlen, len(t) - i), 0, -1):
                w = t[i:i + n]
                if w in self.words and (n > 1 or _KANJI.match(w)):
                    out.append((w, self.words[w], "word"))
                    i += n
                    break
            else:
                if t[i] in self.kanji:
                    out.append((t[i], self.kanji[t[i]], "kanji"))
                i += 1
        return out


class LevelEstimator:
    name = "Leveler"

    def __init__(self, model: SoftmaxModel, lexicon: Lexicon):
        self.model, self.lexicon = model, lexicon

    @classmethod
    def load_default(cls) -> "LevelEstimator":
        path = DATA / "models" / "jlpt_level.npz"
        model = SoftmaxModel.from_bytes(path.read_bytes()) if path.exists() else SoftmaxModel()
        return cls(model, Lexicon.from_bundled())

    def estimate(self, text: str) -> dict:
        ja = "".join(ch for ch in (text or "") if _JA.match(ch))
        if not ja:
            return {"level": None, "confidence": 0.0, "japanese": False, "method": "none", "probs": None, "hardest": []}
        probs = self.model.predict_proba(text)
        found = self.lexicon.analyze(text)
        # coverage: share of kanji explained by known words/kanji (kana grammar is not in the lists)
        n_kanji = len(_KANJI.findall(ja))
        if n_kanji:
            covered = sum(len(_KANJI.findall(tok)) for tok, _, _ in found) / n_kanji
        else:
            covered = sum(len(tok) for tok, _, _ in found) / max(1, len(ja))
        if found:
            lex_levels = sorted(lv for _, lv, _ in found)
            # the hardest ~20% of known items set the level (one hard word makes a sentence harder)
            lex = lex_levels[min(len(lex_levels) - 1, int(0.8 * len(lex_levels)))]
            lex_p = np.full(len(LEVELS), 0.02)
            lex_p[lex] = 1.0
            lex_p /= lex_p.sum()
            w = min(0.85, 0.3 + 0.6 * covered)
            p = w * lex_p + (1 - w) * probs
            method = "lexicon+model"
        else:
            p, method = probs, "model"
        k = int(np.argmax(p))
        hardest = sorted({(tok, lv) for tok, lv, _ in found}, key=lambda x: -x[1])[:5]
        return {"level": LEVELS[k], "confidence": round(float(p[k]), 3), "japanese": True, "method": method,
                "coverage": round(covered, 2), "probs": {LEVELS[i]: round(float(x), 3) for i, x in enumerate(p)},
                "hardest": [{"text": tok, "level": LEVELS[lv]} for tok, lv in hardest]}
