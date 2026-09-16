"""Step 2: text -> sparse features.

Word 1-2-gram TF-IDF captures phrases ("collect request", "kyc update"); char_wb 3-5-gram
TF-IDF is robust to typos, Hinglish spelling variation and obfuscated URLs / handles.
Both use the same length-preserving normaliser (ml.preprocess.normalize).
"""
from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion

from .preprocess import WORD_TOKEN_PATTERN, normalize

DEFAULTS = {"word_max_features": 12000, "char_max_features": 20000, "word_min_df": 2, "char_min_df": 3,
            "sublinear_tf": True}


def make_features(params: dict | None = None) -> FeatureUnion:
    p = {**DEFAULTS, **(params or {})}
    word = TfidfVectorizer(preprocessor=normalize, token_pattern=WORD_TOKEN_PATTERN, ngram_range=(1, 2),
                           min_df=p["word_min_df"], max_features=p["word_max_features"],
                           sublinear_tf=p["sublinear_tf"], dtype=np.float32)
    char = TfidfVectorizer(preprocessor=normalize, analyzer="char_wb", ngram_range=(3, 5),
                           min_df=p["char_min_df"], max_features=p["char_max_features"],
                           sublinear_tf=p["sublinear_tf"], dtype=np.float32)
    return FeatureUnion([("word", word), ("char", char)])


def fit_features(texts: list[str], params: dict | None = None):
    feats = make_features(params)
    X = feats.fit_transform(texts)
    for _, vec in feats.transformer_list:
        vec.stop_words_ = None  # only needed for introspection; large when pickled
    return feats, X
