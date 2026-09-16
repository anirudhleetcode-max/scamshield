"""Compatibility re-export: preprocessing now lives in `ml.preprocess`
(artifacts trained before phase 2 pickled `app.services.textprep.normalize`)."""
from ml.preprocess import WORD_RE, WORD_TOKEN_PATTERN, normalize  # noqa: F401
