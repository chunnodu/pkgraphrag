"""
retrieve.py
Week 7 — Hybrid Retrieval Pipeline

Architecture:
  Question (NL)
      ↓
  [1] Vector Search (LanceDB) → top-K concept URIs, labels, similarity scores
      ↓
  [2] Graph Expansion (rdflib SPARQL) → for each URI, pull:
        - parent label + siblings
        - children (up to N)
        - personal notes
        - web resources
        - LOD links (DBpedia / Wikidata)
      ↓
  [3] Merge + Deduplicate + Rank by relevance
      ↓
  [4] Format as structured context block (ready for LLM prompt)

Usage (CLI):
    python retrieve.py "What do I know about business model design?"
    python retrieve.py "machine learning pipelines" --top-k 10 --map data.mm
    python retrieve.py "career goals" --format json

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
DEFAULT_TOP_K        = 8   # semantic hits to fetch
DEFAULT_EXPAND_DEPTH = 2   # graph hops to expand from each hit
DEFAULT_MAX_CHILDREN = 5   # max child concepts per hit
DEFAULT_MAX_NOTES    = 2   # max personal notes per hit
DEFAULT_MAX_RESOURCES = 3  # max web resources per hit


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConceptContext:
    uri:        str
    label:      str
    source_map: str
    score:      float           # semantic similarity (0–1)
    parent:     Optional[str]   = None
    children:   list[str]       = field(default_factory=list)
    siblings:   list[str]       = field(default_factory=list)
    notes:      list[str]       = field(default_factory=list)
    resources:  list[str]       = field(default_factory=list)
    lod_links:  list[str]       = field(default_factory=list)


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
            lines.append(f"[{i}] {c.label}  (map: {c.source_map}, relevance: {c.score:.3f})")
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
# 1. Semantic retriever (LanceDB)
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
        top_k: int = DEFAULT_TOP_K,
        source_map: Optional[str] = None,
    ) -> list[dict]:
        """Return top-k semantic hits as raw dicts (uri, label, source_map, _distance)."""
        vector = list(self._model.embed([query]))[0].tolist()
        q = self._table.search(vector).limit(top_k)
        if source_map:
            q = q.where(f"source_map = '{source_map}'", prefilter=True)
        return q.to_list()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Graph retriever (rdflib + SPARQL)
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
        excluded = {f"outputs/{e}" for e in EXCLUDED_MAPS}  # belt-and-suspenders

        print(f"  Loading {len(ttl_files)} TTL files into graph...", end=" ", flush=True)
        for path in ttl_files:
            name = os.path.basename(path)
            # Skip excluded maps at every level
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
        max_children: int  = DEFAULT_MAX_CHILDREN,
        max_notes:    int  = DEFAULT_MAX_NOTES,
        max_resources: int = DEFAULT_MAX_RESOURCES,
    ) -> dict:
        """Pull structured context for a single concept URI."""
        # Parent
        parent_rows = self._sparql(self._Q_PARENT % uri)
        parent = str(parent_rows[0][0]) if parent_rows else None

        # Children
        child_rows = self._sparql(self._Q_CHILDREN % (uri, max_children))
        children   = [str(r[0]) for r in child_rows]

        # Siblings
        sib_rows = self._sparql(self._Q_SIBLINGS % (uri, uri))
        siblings  = [str(r[0]) for r in sib_rows]

        # Personal notes
        note_rows = self._sparql(self._Q_NOTES % (uri, max_notes))
        notes     = [str(r[0]).strip() for r in note_rows]

        # Web resources
        res_rows  = self._sparql(self._Q_RESOURCES % (uri, max_resources))
        resources = [str(r[0]) for r in res_rows]

        # LOD links
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
# 3. Hybrid retriever (orchestrator)
# ─────────────────────────────────────────────────────────────────────────────

class HybridRetriever:
    """
    Combines semantic (LanceDB) and graph (rdflib) retrieval into a single
    ranked, deduplicated context object.
    """

    def __init__(
        self,
        db_path:     str = DB_PATH,
        outputs_dir: str = OUTPUTS_DIR,
        verbose:     bool = True,
    ):
        if verbose:
            print("\n── Initialising HybridRetriever ────────────────────────────────")
        self._sem   = SemanticRetriever(db_path)
        self._graph = GraphRetriever(outputs_dir)
        if verbose:
            print("── Ready ───────────────────────────────────────────────────────\n")

    def retrieve(
        self,
        query:       str,
        top_k:       int  = DEFAULT_TOP_K,
        source_map:  Optional[str] = None,
        max_children: int = DEFAULT_MAX_CHILDREN,
        max_notes:   int  = DEFAULT_MAX_NOTES,
        max_resources: int = DEFAULT_MAX_RESOURCES,
    ) -> RetrievalResult:
        """
        Run hybrid retrieval for a natural language query.

        Returns a RetrievalResult with fully-expanded ConceptContext objects.
        """

        # ── Step 1: Semantic search ───────────────────────────────────────────
        hits = self._sem.search(query, top_k=top_k, source_map=source_map)
        if not hits:
            return RetrievalResult(query=query, concepts=[])

        # Deduplicate by URI (in case LanceDB returns duplicates)
        seen_uris: set[str] = set()
        deduped_hits = []
        for h in hits:
            if h["uri"] not in seen_uris:
                seen_uris.add(h["uri"])
                deduped_hits.append(h)

        # ── Step 2: Graph expansion ────────────────────────────────────────────
        concepts: list[ConceptContext] = []
        for h in deduped_hits:
            score = round(1.0 - h.get("_distance", 0.0), 4)
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
                score      = score,
                **expansion,
            ))

        # ── Step 3: Sort by semantic score descending ─────────────────────────
        concepts.sort(key=lambda c: c.score, reverse=True)

        return RetrievalResult(query=query, concepts=concepts)


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(
        description="Hybrid GraphRAG retrieval — semantic + graph expansion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Examples:
              python retrieve.py "What do I know about business model design?"
              python retrieve.py "machine learning pipelines" --top-k 10
              python retrieve.py "career goals" --map careerDevelopment.mm
              python retrieve.py "linked data" --format json
        """),
    )
    p.add_argument("query",                        help="Natural language question or topic")
    p.add_argument("--top-k",      type=int, default=DEFAULT_TOP_K,
                   help=f"Number of semantic hits (default: {DEFAULT_TOP_K})")
    p.add_argument("--map",        default=None,
                   help="Filter to a specific source map (e.g. data.mm)")
    p.add_argument("--format",     choices=["text", "json"], default="text",
                   help="Output format (default: text)")
    p.add_argument("--max-children", type=int, default=DEFAULT_MAX_CHILDREN)
    p.add_argument("--max-notes",    type=int, default=DEFAULT_MAX_NOTES)
    p.add_argument("--max-resources",type=int, default=DEFAULT_MAX_RESOURCES)
    return p.parse_args()


def main():
    args = _parse_args()

    retriever = HybridRetriever()
    result    = retriever.retrieve(
        query        = args.query,
        top_k        = args.top_k,
        source_map   = args.map,
        max_children = args.max_children,
        max_notes    = args.max_notes,
        max_resources= args.max_resources,
    )

    if args.format == "json":
        print(result.as_json())
    else:
        print(result.as_text())


if __name__ == "__main__":
    main()
