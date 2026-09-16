"""Loads the versioned model artifact once and turns linear-model weights into highlighted spans.

Artifact layout (written by `python -m ml.train`):
    models/scamshield-<version>.joblib       features + binary model + category model
    models/scamshield-<version>.card.json    model card: data, params, metrics, operating points

Explanation method
------------------
For a linear model the log-odds is  b + sum_j w_j * x_j  where x_j is the tf-idf value
of feature j in this message. Each feature's contribution c_j = w_j * x_j is split
evenly over every place the n-gram occurs in the message and then over the characters
it covers. Summing per character and then per word gives a score for each word;
adjacent high-scoring words are merged into phrases.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

from ml.models import linear_coef
from ml.preprocess import WORD_RE, normalize

from ..config import get_settings

log = logging.getLogger("scamshield.model")
SPAN_WORD_RE = re.compile(r"\S+")
STOPWORDS = {"a", "an", "and", "the", "to", "of", "in", "on", "at", "is", "are", "for", "from", "by", "or", "you",
             "your", "ur", "u", "me", "my", "we", "our", "it", "this", "that", "with", "be", "will", "has", "have",
             "dear", "hi", "hello", "call", "ko", "ke", "ki", "ka", "hai", "se", "sent", "pay"}
REQUIRED_OPS = ("model_threshold", "suspicious_score", "scam_score", "uncertain_band")


class ModelUnavailable(RuntimeError):
    """Raised when analysis is requested but no model could be loaded."""


@dataclass
class Prediction:
    scam_probability: float
    category: str
    category_probs: dict[str, float]
    spans: list[dict]


def artifact_paths(version: str, model_dir: Path) -> tuple[Path, Path]:
    return model_dir / f"scamshield-{version}.joblib", model_dir / f"scamshield-{version}.card.json"


class ScamModel:
    def __init__(self, path: Path, card_path: Path | None = None):
        if not path.exists():
            raise FileNotFoundError(f"{path.name} not found - run `python -m ml.train` first")
        card_path = card_path or path.with_name(path.name.replace(".joblib", ".card.json"))
        if not card_path.exists():
            raise FileNotFoundError(f"model card {card_path.name} not found next to the artifact")
        self.card = json.loads(card_path.read_text())
        ops = self.card.get("operating_points", {})
        missing = [k for k in REQUIRED_OPS if k not in ops]
        if missing:
            raise ValueError(f"model card is missing operating points: {missing}")
        self.ops = ops
        bundle = joblib.load(path)
        self.version = bundle["version"]
        if self.version != self.card.get("model_version"):
            raise ValueError(f"artifact version {self.version} does not match card {self.card.get('model_version')}")
        self.features = bundle["features"]
        self.binary = bundle["binary"]
        self.category = bundle["category"]
        self.classes = list(self.category.classes_)
        self.word_vocab = self.features.transformer_list[0][1].vocabulary_
        char_vec = self.features.transformer_list[1][1]
        self.char_vocab = char_vec.vocabulary_
        self.char_range = char_vec.ngram_range
        self.n_word = len(self.word_vocab)
        self.bin_coef = linear_coef(self.binary)

    # ------------------------------------------------------------------ predict
    def predict(self, text: str) -> Prediction:
        X = self.features.transform([text])
        p_scam = float(self.binary.predict_proba(X)[0, 1])
        cprobs = self.category.predict_proba(X)[0]
        cat = self.classes[int(np.argmax(cprobs))]
        spans = self._spans(text, X, self.bin_coef)
        return Prediction(p_scam, cat, {c: float(p) for c, p in zip(self.classes, cprobs)}, spans)

    # ---------------------------------------------------------- explanations
    def _occurrences(self, norm: str):
        """Yield (feature_index, start, end) for every word / char n-gram in the text."""
        toks = [(m.start(), m.end(), m.group()) for m in WORD_RE.finditer(norm)]
        for i, (s, e, t) in enumerate(toks):
            j = self.word_vocab.get(t)
            if j is not None:
                yield j, s, e
            if i + 1 < len(toks):
                j = self.word_vocab.get(t + " " + toks[i + 1][2])
                if j is not None:
                    yield j, s, toks[i + 1][1]
        lo, hi = self.char_range
        for m in re.finditer(r"\S+", norm):  # char_wb: n-grams inside " word "
            padded = " " + m.group() + " "
            base = m.start() - 1
            for n in range(lo, hi + 1):
                for k in range(len(padded) - n + 1):
                    j = self.char_vocab.get(padded[k:k + n])
                    if j is not None:
                        s = max(base + k, m.start())
                        e = min(base + k + n, m.end())
                        yield self.n_word + j, s, e

    def _spans(self, text: str, X, coef: np.ndarray, top_k: int = 6) -> list[dict]:
        norm = normalize(text)
        occ = list(self._occurrences(norm))
        if not occ:
            return []
        x = X.toarray()[0]
        counts: dict[int, int] = {}
        for j, _, _ in occ:
            counts[j] = counts.get(j, 0) + 1
        char_score = np.zeros(len(text))
        for j, s, e in occ:
            if e <= s:
                continue
            c = coef[j] * x[j] / counts[j]
            char_score[s:e] += c / (e - s)
        words = []
        for m in SPAN_WORD_RE.finditer(text):
            s, e = m.start(), m.end()
            while s < e and not text[s].isalnum():
                s += 1
            while e > s and not text[e - 1].isalnum() and text[e - 1] not in "/":
                e -= 1
            if e > s:
                words.append([s, e, float(char_score[s:e].sum())])
        if not words:
            return []
        scores = np.array([w[2] for w in words])
        positive = scores[scores > 0]
        if positive.size == 0:
            return []
        thresh = max(0.08, float(np.sort(positive)[::-1][: max(top_k * 2, 1)][-1]))
        picked = [w for w in words if w[2] >= thresh]
        merged: list[list] = []  # [start, end, score, n_words]
        for s, e, sc in picked:
            if merged and merged[-1][3] < 4 and re.fullmatch(r"[\s,:\-]{0,3}", text[merged[-1][1]:s]):
                merged[-1][1] = e
                merged[-1][2] += sc
                merged[-1][3] += 1
            else:
                merged.append([s, e, sc, 1])
        merged = [m for m in merged if m[3] > 1 or text[m[0]:m[1]].lower() not in STOPWORDS]
        if not merged:
            return []
        merged.sort(key=lambda m: -m[2])
        mx = merged[0][2]
        top = [m for m in merged[:top_k] if m[2] >= 0.2 * mx]
        return sorted(
            ({"start": s, "end": e, "text": text[s:e], "weight": round(sc / mx, 3), "source": "model"}
             for s, e, sc, _ in top),
            key=lambda d: d["start"],
        )


_model: ScamModel | None = None
_load_error: str | None = None


def load_model(path: Path | None = None) -> ScamModel | None:
    """Try to load the configured artifact; remember the error instead of crashing."""
    global _model, _load_error
    s = get_settings()
    if path is None:
        path, _ = artifact_paths(s.model_version, Path(s.model_dir))
    try:
        _model = ScamModel(path)
        _load_error = None
        log.info("model loaded version=%s", _model.version)
    except Exception as e:  # corrupt pickle, missing file, bad card ...
        _model = None
        _load_error = f"{type(e).__name__}: {e}"
        log.error("model not loaded: %s", _load_error)
    return _model


def get_model() -> ScamModel:
    if _model is None:
        if _load_error is None:
            load_model()
        if _model is None:
            raise ModelUnavailable(_load_error or "model not loaded")
    return _model


def model_status() -> dict:
    return {"loaded": _model is not None, "version": _model.version if _model else None, "error": _load_error}


def set_model(model: ScamModel | None, error: str | None = None) -> None:
    """Swap the in-process model (used by evaluation code and tests)."""
    global _model, _load_error
    _model, _load_error = model, error
