"""
Week 6 — LanceDB Embedding Pipeline
Extracts skos:Concept labels + ancestor context from all TTL files,
generates embeddings via fastembed, and stores in a LanceDB table.
"""

import os
import sys
import gc
import lancedb
import pyarrow as pa
from rdflib import Graph, Namespace, RDF
from rdflib.namespace import SKOS
from fastembed import TextEmbedding

# ── Paths ────────────────────────────────────────────────────────────────────
OUTPUTS_DIR = os.path.join(os.path.dirname(__file__), "outputs")
DB_PATH     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pkg_lancedb")

# ── Namespaces ────────────────────────────────────────────────────────────────
PKG  = Namespace("https://pkg.chunnodu.com/ontology#")
PKGC = Namespace("https://pkg.chunnodu.com/concept/")


def load_graph(outputs_dir: str) -> Graph:
    """Load all TTL files into a single rdflib graph."""
    g = Graph()
    g.bind("pkg",  PKG)
    g.bind("pkgc", PKGC)
    g.bind("skos", SKOS)

    ttl_files = [f for f in os.listdir(outputs_dir) if f.endswith(".ttl")]
    print(f"Loading {len(ttl_files)} TTL files...")
    for fname in sorted(ttl_files):
        fpath = os.path.join(outputs_dir, fname)
        g.parse(fpath, format="turtle")
        print(f"  ✓ {fname}")

    print(f"\n  Combined graph: {len(g):,} triples\n")
    return g


def build_parent_index(g: Graph) -> dict:
    """Map each concept URI → its parent's prefLabel (for context prepending)."""
    parent_label = {}
    for s, _, o in g.triples((None, PKG.hasSubTopic, None)):
        # s is parent, o is child
        labels = list(g.objects(s, SKOS.prefLabel))
        if labels:
            parent_label[str(o)] = str(labels[0])
    return parent_label


def extract_concepts(g: Graph) -> list[dict]:
    """Extract all skos:Concept instances with label, source map, and URI."""
    parent_index = build_parent_index(g)
    concepts = []

    for uri in g.subjects(RDF.type, SKOS.Concept):
        uri_str = str(uri)

        labels = list(g.objects(uri, SKOS.prefLabel))
        if not labels:
            continue
        label = str(labels[0]).strip()
        if not label or label == "[REDACTED]":
            continue

        source_maps = list(g.objects(uri, PKG.sourceMap))
        source_map = str(source_maps[0]) if source_maps else "unknown"

        # Prepend parent label for context (e.g. "Business Model > Canvas")
        parent = parent_index.get(uri_str, "")
        text_for_embedding = f"{parent} > {label}" if parent else label

        concepts.append({
            "uri":        uri_str,
            "label":      label,
            "context":    text_for_embedding,
            "source_map": source_map,
        })

    return concepts


def embed_and_store(concepts: list[dict], db_path: str, batch_size: int = 256):
    """Generate embeddings in batches and store incrementally in LanceDB."""
    print(f"Embedding {len(concepts):,} concepts using BAAI/bge-small-en-v1.5...")
    print(f"  Batch size: {batch_size} | Batches: {len(concepts) // batch_size + 1}\n")

    model  = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    db     = lancedb.connect(db_path)
    table  = None
    total  = 0

    for i in range(0, len(concepts), batch_size):
        batch    = concepts[i : i + batch_size]
        texts    = [c["context"] for c in batch]
        vectors  = list(model.embed(texts))
        dim      = len(vectors[0])

        rows = [
            {
                "uri":        c["uri"],
                "label":      c["label"],
                "context":    c["context"],
                "source_map": c["source_map"],
                "vector":     v.tolist(),
            }
            for c, v in zip(batch, vectors)
        ]

        if table is None:
            schema = pa.schema([
                pa.field("uri",        pa.string()),
                pa.field("label",      pa.string()),
                pa.field("context",    pa.string()),
                pa.field("source_map", pa.string()),
                pa.field("vector",     pa.list_(pa.float32(), dim)),
            ])
            table = db.create_table("concepts", data=rows, schema=schema, mode="overwrite")
        else:
            table.add(rows)

        total += len(rows)
        print(f"  Batch {i // batch_size + 1}: {total:,}/{len(concepts):,} stored", end="\r")

    print(f"\n\n  LanceDB table 'concepts' created at: {db_path}")
    print(f"  Total rows stored: {table.count_rows():,}")
    return table


def search(table, query: str, n: int = 10, source_map: str = None):
    """Semantic search — optionally filter by source map."""
    model  = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    vector = list(model.embed([query]))[0].tolist()

    q = table.search(vector).limit(n)
    if source_map:
        q = q.where(f"source_map = '{source_map}'", prefilter=True)

    results = q.to_list()
    return results


def print_results(results: list, query: str):
    print(f"\nTop results for: \"{query}\"")
    print("─" * 60)
    for r in results:
        score = round(1 - r.get("_distance", 0), 4)
        print(f"  [{r['source_map'].replace('.mm','')}]  {r['label']}  (score: {score})")


def process_one_ttl(fpath: str, model, db_path: str, first: bool, batch_size: int = 256):
    """Load a single TTL, extract concepts, embed, and append to LanceDB."""
    fname = os.path.basename(fpath)
    g = Graph()
    g.bind("pkg", PKG)
    g.bind("pkgc", PKGC)
    g.bind("skos", SKOS)
    g.parse(fpath, format="turtle")

    concepts = extract_concepts(g)
    del g
    gc.collect()  # force free rdflib memory before embedding

    if not concepts:
        print(f"  {fname}: 0 concepts, skipping")
        return 0

    db    = lancedb.connect(db_path)
    table = None
    total = 0

    if not first:
        try:
            table = db.open_table("concepts")
        except Exception:
            first = True

    for i in range(0, len(concepts), batch_size):
        batch   = concepts[i : i + batch_size]
        texts   = [c["context"] for c in batch]
        vectors = list(model.embed(texts))
        dim     = len(vectors[0])

        rows = [
            {
                "uri":        c["uri"],
                "label":      c["label"],
                "context":    c["context"],
                "source_map": c["source_map"],
                "vector":     v.tolist(),
            }
            for c, v in zip(batch, vectors)
        ]

        if first and table is None:
            schema = pa.schema([
                pa.field("uri",        pa.string()),
                pa.field("label",      pa.string()),
                pa.field("context",    pa.string()),
                pa.field("source_map", pa.string()),
                pa.field("vector",     pa.list_(pa.float32(), dim)),
            ])
            table = db.create_table("concepts", data=rows, schema=schema, mode="overwrite")
            first = False
        else:
            table.add(rows)

        total += len(rows)

    print(f"  ✓ {fname:<55} {total:>5} concepts")
    return total


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ttl_files = sorted([
        os.path.join(OUTPUTS_DIR, f)
        for f in os.listdir(OUTPUTS_DIR)
        if f.endswith(".ttl")
    ])

    print(f"Loading model...")
    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    print(f"Model ready.\n")
    print(f"Processing {len(ttl_files)} TTL files one at a time...\n")

    grand_total = 0
    for idx, fpath in enumerate(ttl_files):
        grand_total += process_one_ttl(fpath, model, DB_PATH, first=(idx == 0))
        gc.collect()

    print(f"\n  Total concepts embedded: {grand_total:,}")

    # Smoke-test
    db    = lancedb.connect(DB_PATH)
    table = db.open_table("concepts")
    print(f"  LanceDB rows confirmed: {table.count_rows():,}\n")

    for query in [
        "business model strategy",
        "machine learning and data pipelines",
        "career development job search",
        "personal finance and life goals",
    ]:
        results = search(table, query, n=5)
        print_results(results, query)

    print("\n✅ Week 6 complete — LanceDB embedding store ready.")
