"""
lod_enrich.py
Week 4 — LOD Enrichment

Queries DBpedia Lookup API for each unique skos:Concept label in the graph.
Adds owl:sameAs and skos:exactMatch triples when a high-confidence match is found.
Outputs: outputs/lod_enrichment.ttl  (new triples only — originals untouched)

Matching strategy:
  - Only accepts matches where DBpedia label is an exact case-insensitive match
    to the concept's prefLabel (no fuzzy guessing)
  - Skips single-word generic labels (e.g. "Notes", "Links", "Other")
  - Rate-limited to 1 req/sec to be polite to DBpedia
"""

import time
import re
import requests
from rdflib import Graph, URIRef, Namespace
from rdflib.namespace import SKOS, OWL
import pyoxigraph

# ── Config ────────────────────────────────────────────────────────────────────
STORE_PATH   = "/Users/chunnodu/projects/graphrag/pkg_store"
OUT_TTL      = "/Users/chunnodu/projects/graphrag/outputs/lod_enrichment.ttl"
DBPEDIA_API  = "https://lookup.dbpedia.org/api/search"
DELAY        = 1.0   # seconds between requests
MIN_LABEL_WORDS = 2  # skip labels shorter than this many words

# Generic labels that produce noisy DBpedia matches — skip them
SKIP_LABELS = {
    "notes", "links", "other", "resources", "todo", "done", "next", "projects",
    "tasks", "goals", "reference", "general", "misc", "ideas", "actions",
    "someday", "waiting", "reading", "books", "courses", "tools", "events",
}

PKG  = Namespace("https://pkg.chunnodu.com/ontology#")
PKGC = Namespace("https://pkg.chunnodu.com/concept/")


def get_all_concepts(store_path):
    """Pull every (concept_uri, prefLabel) pair from the Oxigraph store."""
    store = pyoxigraph.Store(store_path)
    q = """
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT DISTINCT ?concept ?label WHERE {
        ?concept a skos:Concept ;
                 skos:prefLabel ?label .
    }
    """
    results = []
    for row in store.query(q):
        uri   = str(row["concept"])
        label = str(row["label"].value) if hasattr(row["label"], "value") else str(row["label"])
        results.append((uri, label))
    print(f"Found {len(results):,} concepts in store.")
    return results


def should_skip(label):
    words = label.strip().split()
    if len(words) < MIN_LABEL_WORDS:
        return True
    if label.strip().lower() in SKIP_LABELS:
        return True
    # Skip labels that look like Freeplane IDs or URLs
    if re.match(r'^(ID_|http)', label):
        return True
    return False


def lookup_dbpedia(label):
    """
    Query DBpedia Lookup API.
    Returns the top DBpedia URI if the label matches exactly, else None.
    """
    try:
        resp = requests.get(
            DBPEDIA_API,
            params={"query": label, "maxResults": 3, "format": "json"},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        docs = data.get("docs", [])
        for doc in docs:
            # DBpedia label field is a list
            db_labels = doc.get("label", [])
            for db_label in db_labels:
                if db_label.strip().lower() == label.strip().lower():
                    uri = doc.get("resource", [None])[0]
                    return uri
        return None
    except Exception as e:
        print(f"  [warn] DBpedia request failed for '{label}': {e}")
        return None


def build_enrichment_graph(concepts):
    """
    For each concept, query DBpedia and collect owl:sameAs + skos:exactMatch triples.
    Returns an rdflib Graph of the new triples.
    """
    g = Graph()
    g.bind("owl",  OWL)
    g.bind("skos", SKOS)

    matched   = 0
    skipped   = 0
    no_match  = 0

    total = len(concepts)
    for i, (uri, label) in enumerate(concepts):
        if i % 100 == 0:
            print(f"  [{i}/{total}] matched so far: {matched}")

        if should_skip(label):
            skipped += 1
            continue

        db_uri = lookup_dbpedia(label)
        time.sleep(DELAY)

        if db_uri:
            concept_ref = URIRef(uri)
            db_ref      = URIRef(db_uri)
            g.add((concept_ref, OWL.sameAs,          db_ref))
            g.add((concept_ref, SKOS.exactMatch,     db_ref))
            matched += 1
        else:
            no_match += 1

    print(f"\nResults:")
    print(f"  Matched:  {matched:,}")
    print(f"  Skipped:  {skipped:,}  (too short / generic)")
    print(f"  No match: {no_match:,}")
    print(f"  Total new triples: {len(g):,}")
    return g


def main():
    print("=== Week 4: LOD Enrichment — DBpedia ===\n")
    concepts = get_all_concepts(STORE_PATH)

    print(f"\nQuerying DBpedia Lookup API (this will take a while)...")
    g = build_enrichment_graph(concepts)

    g.serialize(destination=OUT_TTL, format="turtle")
    print(f"\nEnrichment triples saved to: {OUT_TTL}")


if __name__ == "__main__":
    main()
