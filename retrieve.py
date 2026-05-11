"""
retrieve.py
Week 9 — RRF Hybrid Retrieval Pipeline

Architecture:
  Question (NL)
      ├─ Path A → Embedder → Vector Search (LanceDB) → Ranked List A (cosine similarity)
      └─ Path B → Tokeniser → FTS on labels (LanceDB) → Ranked List B (keyword match)
                      ↓
             RRF Fusion: score_i = Σ 1 / (k + rank_i),  k=60
                      ↓
             Top-N fused URIs → Graph Expansion (rdflib SPARQL)
                      ↓
             Context Block → Language Model

Why RRF: parameter-free, no manual weight tuning.  Fixes the known weakness where
exact concept labels (proper nouns, acronyms, initialisms) have poor vector
representations but match perfectly via full-text search.

Usage (CLI):
    python retrieve.py "What do I know about business model design?"
    python retrieve.py "machine learning pipelines" --top-k 10 --map data.mm
    python retrieve.py "career goals" --format json
    python retrieve.py "DLVR" --debug          # show per-path hits before fusion

⚠️  pitchstone.mm and neogov.mm are permanently excluded.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import textwrap
from dataclasses import dataclass, field, asdict
from typing import Optional

import lancedb
from fastembed import TextEmbedding
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import SKOS, OWL, RDF

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR  = os.path.join(BASE_DIR, "outputs")
DB_PATH      = os.path.join(BASE_DIR, "pkg_lancedb")

# ── Namespaces ────────────────────────────────────────────────────────────────
PKG    = Namespace("https://pkg.chunnodu.com/ontology#")
PKGC   = Namespace("https://pkg.chunnodu.com/concept/")
SCHEMA = Namespace("https://schema.org/")
DC     = Namespace("http://purl.org/dc/elements/1.1/")

# ── Excluded maps (proprietary employer data) ─────────────────────────────────
EXCLUDED_MAPS = {"pitchstone.mm", "neogov.mm"}

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_TOP_K         = 8    # final fused hits passed to graph expansion
DEFAULT_FETCH_K       = 20   # per-path fetch size (before fusion); wider net
RRF_K                 = 60   # RRF smoothing constant (standard value)
DEFAULT_EXPAND_DEPTH  = 2    # graph hops to expand from each hit (unused directly)
DEFAULT_MAX_CHILDREN  = 5    # max child concepts per hit
DEFAULT_MAX_NOTES     = 2    # max personal notes per hit
DEFAULT_MAX_RESOURCES = 3    # max web resources per hit


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConceptContext:
    uri:        str
    label:      str
    source_map: str
    score:      float           # RRF-fused score (week 9+); raw cosine in week 7–8
    parent:     Optional[str]   = None
    children:   list[str]       = field(default_factory=list)
    siblings:   list[str]       = field(default_factory=list)
    notes:      list[str]       = field(default_factory=list)
    resources:  list[str]       = field(default_factory=list)
    lod_links:  list[str]       = field(default_factory=list)
    in_vector:  bool            = True   # present in vector-search path
    in_keyword: bool            = False  # present in FTS keyword path


@dataclass
class RetrievalResult:
    query:    str
    concepts: list[ConceptContext]

    def as_text(self) -> str:
        """Render as a plain-text context block for LLM prompts."""
        lines = [
            f'CONTEXT FOR QUERY: "{self.query}"',
            "=" * 70,
            f"Retrieved {len(self.concepts)} relevant concept(s) from your personal knowledge graph.\n",
        ]
        for i, c in enumerate(self.concepts, 1):
            src_tag = f"vector+keyword" if (c.in_vector and c.in_keyword) else (
                      "keyword" if c.in_keyword else "vector")
            lines.append(
                f"[{i}] {c.label}  "
                f"(map: {c.source_map}, rrf: {c.score:.4f}, src: {src_tag})"
            )
            if c.parent:
                lines.append(f"    Parent   : {c.parent}")
            if c.children:
                lines.append(f"    Children : {', '.join(c.children)}")
            if c.siblings:
                lines.append(f"    Siblings : {', '.join(c.siblings)}")
            if c.notes:
                for note in c.notes:
                    lines.append(f"    Note     : {textwrap.shorten(note, 200)}")
            if c.resources:
                for url in c.resources:
                    lines.append(f"    Resource : {url}")
            if c.lod_links:
                lines.append(f"    LOD      : {', '.join(c.lod_links)}")
            lines.append("")
        return "\n".join(lines)

    def as_json(self) -> str:
        return json.dumps(
            {"query": self.query, "concepts": [asdict(c) for c in self.concepts]},
            indent=2,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Semantic retriever (LanceDB vector search)
# ─────────────────────────────────────────────────────────────────────────────

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
        """Return top-k semantic hits as raw dicts (uri, label, source_map, _distance)."""
        vector = list(self._model.embed([query]))[0].tolist()
        q = self._table.search(vector).limit(top_k)
        if source_map:
            q = q.where(f"source_map = '{source_map}'", prefilter=True)
        return q.to_list()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Keyword retriever (LanceDB full-text search)
# ─────────────────────────────────────────────────────────────────────────────

class KeywordRetriever:
    """
    Wraps LanceDB full-text search (FTS) on the 'label' column.

    Requires the FTS index to have been built on the table:
        table.create_fts_index("label", replace=True)

    This is done automatically by embed_to_lancedb.py (Week 9+).
    Falls back gracefully (returns empty list + warning) if the index
    is absent so the pipeline degrades to vector-only rather than crashing.
    """

    def __init__(self, db_path: str = DB_PATH):
        self._db      = lancedb.connect(db_path)
        self._table   = self._db.open_table("concepts")
        self._enabled = self._check_fts()

    def _check_fts(self) -> bool:
        try:
            indices = self._table.list_indices()
            has_fts = any(
                getattr(idx, "index_type", None) == "FTS"
                or "FTS" in str(idx)
                for idx in indices
            )
            if not has_fts:
                print(
                    "  ⚠  No FTS index found on 'label'. "
                    "Run embed_to_lancedb.py to build it. "
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
        """Return top-k FTS hits as raw dicts (uri, label, source_map, _score)."""
        if not self._enabled:
            return []
        try:
            q = self._table.search(query, query_type="fts").limit(top_k)
            if source_map:
                q = q.where(f"source_map = '{source_map}'")
            results = q.to_list()
            # Filter excluded maps (belt-and-suspenders)
            return [r for r in results if r.get("source_map", "") not in EXCLUDED_MAPS]
        except Exception as e:
            print(f"  ⚠  FTS search failed ({e}). Skipping keyword path.", file=sys.stderr)
            return []


# ─────────────────────────────────────────────────────────────────────────────
# 3. RRF fusion
# ─────────────────────────────────────────────────────────────────────────────

def rrf_fuse(
    list_a: list[dict],
    list_b: list[dict],
    k:      int = RRF_K,
    top_n:  int = DEFAULT_TOP_K,
) -> list[dict]:
    """
    Reciprocal Rank Fusion over two ranked URI lists.

    Formula: rrf_score(d) = Σ_list  1 / (k + rank(d, list))
    Only lists where d appears contribute a term; absent → no contribution.

    Args:
        list_a: vector-search hits (dicts with "uri", "label", "source_map")
        list_b: keyword-search hits (same schema)
        k:      smoothing constant (default 60)
        top_n:  number of fused results to return

    Returns:
        List of top_n dicts sorted by rrf_score descending, each with:
            uri, label, source_map, rrf_score, in_vector, in_keyword
    """
    scores: dict[str, float] = {}
    meta:   dict[str, dict]  = {}

    for rank, hit in enumerate(list_a, start=1):
        uri = hit["uri"]
        scores[uri] = scores.get(uri, 0.0) + 1.0 / (k + rank)
        if uri not in meta:
            meta[uri] = {
                "label":      hit.get("label", ""),
                "source_map": hit.get("source_map", ""),
                "in_vector":  True,
                "in_keyword": False,
            }
        else:
            meta[uri]["in_vector"] = True

    for rank, hit in enumerate(list_b, start=1):
        uri = hit["uri"]
        scores[uri] = scores.get(uri, 0.0) + 1.0 / (k + rank)
        if uri not in meta:
            meta[uri] = {
                "label":      hit.get("label", ""),
                "source_map": hit.get("source_map", ""),
                "in_vector":  False,
                "in_keyword": True,
            }
        else:
            meta[uri]["in_keyword"] = True

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [
        {
            "uri":        uri,
            "label":      meta[uri]["label"],
            "source_map": meta[uri]["source_map"],
            "rrf_score":  round(score, 6),
            "in_vector":  meta[uri]["in_vector"],
            "in_keyword": meta[uri]["in_keyword"],
        }
        for uri, score in fused
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Graph retriever (rdflib + SPARQL)
# ─────────────────────────────────────────────────────────────────────────────

class GraphRetriever:
    """Loads all TTL files and expands concept URIs into structured context."""

    # SPARQL templates ─────────────────────────────────────────────────────────

    _Q_PARENT = """
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?parentLabel WHERE {
        ?parent pkg:hasSubTopic <%s> ;
                skos:prefLabel  ?parentLabel .
    } LIMIT 1
    """

    _Q_CHILDREN = """
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?childLabel WHERE {
        <%s> pkg:hasSubTopic ?child .
        ?child skos:prefLabel ?childLabel .
    } LIMIT %d
    """

    _Q_SIBLINGS = """
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?sibLabel WHERE {
        ?parent pkg:hasSubTopic <%s> ;
                pkg:hasSubTopic ?sib .
        ?sib skos:prefLabel ?sibLabel .
        FILTER (?sib != <%s>)
    } LIMIT 5
    """

    _Q_NOTES = """
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    SELECT ?text WHERE {
        <%s> pkg:hasNote ?note .
        ?note pkg:noteText ?text .
    } LIMIT %d
    """

    _Q_RESOURCES = """
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    SELECT ?url WHERE {
        <%s> pkg:hasResource ?res .
        ?res pkg:url ?url .
    } LIMIT %d
    """

    _Q_LOD = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    SELECT ?external WHERE {
        <%s> owl:sameAs ?external .
    }
    """

    def __init__(self, outputs_dir: str = OUTPUTS_DIR):
        self._g = self._load_graph(outputs_dir)

    def _load_graph(self, outputs_dir: str) -> Graph:
        g = Graph()
        g.bind("pkg",    PKG)
        g.bind("pkgc",   PKGC)
        g.bind("skos",   SKOS)
        g.bind("owl",    OWL)
        g.bind("schema", SCHEMA)
        g.bind("dc",     DC)

        ttl_files = sorted(glob.glob(os.path.join(outputs_dir, "*.ttl")))

        print(f"  Loading {len(ttl_files)} TTL files into graph...", end=" ", flush=True)
        for path in ttl_files:
            name = os.path.basename(path)
            if any(ex in name for ex in EXCLUDED_MAPS):
                continue
            sub = Graph()
            sub.parse(path, format="turtle")
            g += sub

        print(f"{len(g):,} triples loaded.")
        return g

    def _sparql(self, query: str) -> list:
        return list(self._g.query(query))

    def expand(
        self,
        uri: str,
        max_children:  int = DEFAULT_MAX_CHILDREN,
        max_notes:     int = DEFAULT_MAX_NOTES,
        max_resources: int = DEFAULT_MAX_RESOURCES,
    ) -> dict:
        """Pull structured context for a single concept URI."""
        parent_rows = self._sparql(self._Q_PARENT % uri)
        parent      = str(parent_rows[0][0]) if parent_rows else None

        child_rows = self._sparql(self._Q_CHILDREN % (uri, max_children))
        children   = [str(r[0]) for r in child_rows]

        sib_rows = self._sparql(self._Q_SIBLINGS % (uri, uri))
        siblings  = [str(r[0]) for r in sib_rows]

        note_rows = self._sparql(self._Q_NOTES % (uri, max_notes))
        notes     = [str(r[0]).strip() for r in note_rows]

        res_rows  = self._sparql(self._Q_RESOURCES % (uri, max_resources))
        resources = [str(r[0]) for r in res_rows]

        lod_rows  = self._sparql(self._Q_LOD % uri)
        lod_links = [str(r[0]) for r in lod_rows]

        return {
            "parent":    parent,
            "children":  children,
            "siblings":  siblings,
            "notes":     notes,
            "resources": resources,
            "lod_links": lod_links,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 5. HybridRetriever (RRF orchestrator)
# ─────────────────────────────────────────────────────────────────────────────

class HybridRetriever:
    """
    True hybrid retrieval: two independent signals fused via RRF, then
    graph-expanded.

    Signal A — semantic vector search (LanceDB, cosine distance)
    Signal B — full-text search on concept labels (LanceDB FTS)

    If FTS index is absent, falls back to vector-only (behaviour identical
    to the Week 7 implementation).
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
            fts_status = "✓ FTS enabled" if self._kw._enabled else "⚠ FTS disabled (vector-only fallback)"
            print(f"  {fts_status}")
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
        """
        Run RRF hybrid retrieval for a natural language query.

        Steps:
          1. Vector search  (top FETCH_K hits)
          2. Keyword search (top FETCH_K hits)
          3. RRF fusion     → top_k fused URIs
          4. Graph expansion of each URI
          5. Return RetrievalResult sorted by RRF score

        Returns a RetrievalResult with fully-expanded ConceptContext objects.
        """
        fetch_k = max(top_k * 2, DEFAULT_FETCH_K)   # wider net for fusion

        # ── Step 1: Semantic search ───────────────────────────────────────────
        vec_hits = self._sem.search(query, top_k=fetch_k, source_map=source_map)

        # ── Step 2: Keyword search ────────────────────────────────────────────
        kw_hits = self._kw.search(query, top_k=fetch_k, source_map=source_map)

        if debug or self._verbose:
            print(f"  Vector hits : {len(vec_hits):>3}  "
                  f"Keyword hits: {len(kw_hits):>3}")

        if debug:
            print("\n  [Vector top-5]")
            for i, h in enumerate(vec_hits[:5], 1):
                score = round(1.0 - h.get("_distance", 0.0), 4)
                print(f"    {i}. [{h['source_map']}] {h['label']}  ({score:.4f})")
            print("\n  [Keyword top-5]")
            for i, h in enumerate(kw_hits[:5], 1):
                print(f"    {i}. [{h['source_map']}] {h['label']}")
            print()

        # ── Step 3: RRF fusion ────────────────────────────────────────────────
        if not vec_hits and not kw_hits:
            return RetrievalResult(query=query, concepts=[])

        fused = rrf_fuse(vec_hits, kw_hits, k=RRF_K, top_n=top_k)

        # ── Step 4: Graph expansion ────────────────────────────────────────────
        concepts: list[ConceptContext] = []
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

        # Already sorted by RRF score from rrf_fuse; just return
        return RetrievalResult(query=query, concepts=concepts)


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(
        description="GraphRAG hybrid retrieval — RRF (vector + FTS) + graph expansion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Examples:
              python retrieve.py "What do I know about business model design?"
              python retrieve.py "machine learning pipelines" --top-k 10
              python retrieve.py "career goals" --map careerDevelopment.mm
              python retrieve.py "DLVR" --debug
              python retrieve.py "linked data" --format json
        """),
    )
    p.add_argument("query",   help="Natural language question or topic")
    p.add_argument("--top-k", type=int, default=DEFAULT_TOP_K,
                   help=f"Final number of fused hits (default: {DEFAULT_TOP_K})")
    p.add_argument("--map",   default=None,
                   help="Filter to a specific source map (e.g. data.mm)")
    p.add_argument("--format", choices=["text", "json"], default="text",
                   help="Output format (default: text)")
    p.add_argument("--debug",  action="store_true",
                   help="Show per-path hits before fusion")
    p.add_argument("--max-children",  type=int, default=DEFAULT_MAX_CHILDREN)
    p.add_argument("--max-notes",     type=int, default=DEFAULT_MAX_NOTES)
    p.add_argument("--max-resources", type=int, default=DEFAULT_MAX_RESOURCES)
    return p.parse_args()


def main():
    args = _parse_args()

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

    if args.format == "json":
        print(result.as_json())
    else:
        print(result.as_text())


if __name__ == "__main__":
    main()
