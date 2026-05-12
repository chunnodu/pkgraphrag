"""LanceDB vector similarity search."""

from __future__ import annotations

from typing import Optional

import lancedb
from fastembed import TextEmbedding

from .models import DB_PATH, DEFAULT_FETCH_K


class SemanticRetriever:
    """Wraps LanceDB for fast vector similarity search."""

    def __init__(self, db_path: str = DB_PATH):
        self._db    = lancedb.connect(db_path)
        self._table = self._db.open_table("concepts")
        self._model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_FETCH_K,
        source_map: Optional[str] = None,
    ) -> list[dict]:
        vector = list(self._model.embed([query]))[0].tolist()
        q = self._table.search(vector).limit(top_k)
        if source_map:
            q = q.where(f"source_map = '{source_map}'", prefilter=True)
        return q.to_list()
