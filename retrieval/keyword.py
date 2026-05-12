"""LanceDB full-text search on concept labels."""

from __future__ import annotations

import sys
from typing import Optional

import lancedb

from .models import DB_PATH, DEFAULT_FETCH_K, EXCLUDED_MAPS


class KeywordRetriever:
    """
    Wraps LanceDB FTS on the 'label' column.
    Falls back gracefully to an empty list if the FTS index is absent.
    Build the index by running: python -m ingest.embed
    """

    def __init__(self, db_path: str = DB_PATH):
        self._db      = lancedb.connect(db_path)
        self._table   = self._db.open_table("concepts")
        self._enabled = self._check_fts()

    def _check_fts(self) -> bool:
        try:
            indices = self._table.list_indices()
            has_fts = any(
                getattr(idx, "index_type", None) == "FTS" or "FTS" in str(idx)
                for idx in indices
            )
            if not has_fts:
                print(
                    "  ⚠  No FTS index on 'label'. "
                    "Run `python -m ingest.embed` to build it. "
                    "Falling back to vector-only retrieval.",
                    file=sys.stderr,
                )
            return has_fts
        except Exception as e:
            print(f"  ⚠  FTS check failed ({e}). Keyword path disabled.", file=sys.stderr)
            return False

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_FETCH_K,
        source_map: Optional[str] = None,
    ) -> list[dict]:
        if not self._enabled:
            return []
        try:
            q = self._table.search(query, query_type="fts").limit(top_k)
            if source_map:
                q = q.where(f"source_map = '{source_map}'")
            results = q.to_list()
            return [r for r in results if r.get("source_map", "") not in EXCLUDED_MAPS]
        except Exception as e:
            print(f"  ⚠  FTS search failed ({e}). Skipping keyword path.", file=sys.stderr)
            return []
