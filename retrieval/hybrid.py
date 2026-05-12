"""HybridRetriever: RRF orchestrator + CLI entry point."""

from __future__ import annotations

import argparse
import textwrap
from typing import Optional

from .fusion import rrf_fuse
from .graph import GraphRetriever
from .keyword import KeywordRetriever
from .models import (
    DB_PATH, OUTPUTS_DIR,
    DEFAULT_TOP_K, DEFAULT_FETCH_K, RRF_K,
    DEFAULT_MAX_CHILDREN, DEFAULT_MAX_NOTES, DEFAULT_MAX_RESOURCES,
    ConceptContext, RetrievalResult,
)
from .semantic import SemanticRetriever


class HybridRetriever:
    """
    Two independent retrieval signals fused via RRF, then SPARQL graph-expanded.

    Signal A — SemanticRetriever: LanceDB cosine vector search
    Signal B — KeywordRetriever:  LanceDB FTS on concept labels

    Falls back to vector-only if the FTS index is absent.
    """

    def __init__(
        self,
        db_path:     str  = DB_PATH,
        outputs_dir: str  = OUTPUTS_DIR,
        verbose:     bool = True,
    ):
        if verbose:
            print("\n── Initialising HybridRetriever (RRF) ─────────────────────────")
        self._sem     = SemanticRetriever(db_path)
        self._kw      = KeywordRetriever(db_path)
        self._graph   = GraphRetriever(outputs_dir)
        self._verbose = verbose
        if verbose:
            status = "✓ FTS enabled" if self._kw._enabled else "⚠ FTS disabled (vector-only fallback)"
            print(f"  {status}")
            print("── Ready ───────────────────────────────────────────────────────\n")

    def retrieve(
        self,
        query:         str,
        top_k:         int           = DEFAULT_TOP_K,
        source_map:    Optional[str] = None,
        max_children:  int           = DEFAULT_MAX_CHILDREN,
        max_notes:     int           = DEFAULT_MAX_NOTES,
        max_resources: int           = DEFAULT_MAX_RESOURCES,
        debug:         bool          = False,
    ) -> RetrievalResult:
        fetch_k  = max(top_k * 2, DEFAULT_FETCH_K)
        vec_hits = self._sem.search(query, top_k=fetch_k, source_map=source_map)
        kw_hits  = self._kw.search(query,  top_k=fetch_k, source_map=source_map)

        if debug or self._verbose:
            print(f"  Vector hits : {len(vec_hits):>3}  Keyword hits: {len(kw_hits):>3}")

        if debug:
            print("\n  [Vector top-5]")
            for i, h in enumerate(vec_hits[:5], 1):
                score = round(1.0 - h.get("_distance", 0.0), 4)
                print(f"    {i}. [{h['source_map']}] {h['label']}  ({score:.4f})")
            print("\n  [Keyword top-5]")
            for i, h in enumerate(kw_hits[:5], 1):
                print(f"    {i}. [{h['source_map']}] {h['label']}")
            print()

        if not vec_hits and not kw_hits:
            return RetrievalResult(query=query, concepts=[])

        fused    = rrf_fuse(vec_hits, kw_hits, k=RRF_K, top_n=top_k)
        concepts = []
        for h in fused:
            expansion = self._graph.expand(
                h["uri"],
                max_children=max_children,
                max_notes=max_notes,
                max_resources=max_resources,
            )
            concepts.append(ConceptContext(
                uri        = h["uri"],
                label      = h["label"],
                source_map = h["source_map"],
                score      = h["rrf_score"],
                in_vector  = h["in_vector"],
                in_keyword = h["in_keyword"],
                **expansion,
            ))

        return RetrievalResult(query=query, concepts=concepts)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(
        description="GraphRAG hybrid retrieval — RRF (vector + FTS) + graph expansion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Examples:
              python retrieve.py "What do I know about business model design?"
              python retrieve.py "machine learning pipelines" --top-k 10
              python retrieve.py "DLVR" --debug
              python retrieve.py "linked data" --format json
        """),
    )
    p.add_argument("query")
    p.add_argument("--top-k",          type=int, default=DEFAULT_TOP_K)
    p.add_argument("--map",            default=None)
    p.add_argument("--format",         choices=["text", "json"], default="text")
    p.add_argument("--debug",          action="store_true")
    p.add_argument("--max-children",   type=int, default=DEFAULT_MAX_CHILDREN)
    p.add_argument("--max-notes",      type=int, default=DEFAULT_MAX_NOTES)
    p.add_argument("--max-resources",  type=int, default=DEFAULT_MAX_RESOURCES)
    return p.parse_args()


def main():
    args      = _parse_args()
    retriever = HybridRetriever(verbose=True)
    result    = retriever.retrieve(
        query         = args.query,
        top_k         = args.top_k,
        source_map    = args.map,
        max_children  = args.max_children,
        max_notes     = args.max_notes,
        max_resources = args.max_resources,
        debug         = args.debug,
    )
    print(result.as_json() if args.format == "json" else result.as_text())


if __name__ == "__main__":
    main()
