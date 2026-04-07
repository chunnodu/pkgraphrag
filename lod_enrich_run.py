"""
lod_enrich_run.py
Week 4 — LOD Enrichment (session-adapted runner)

Same logic as lod_enrich.py but reads concepts directly from the .ttl output
files using rdflib, instead of the Oxigraph store (which lives on the Mac).
Outputs: outputs/lod_enrichment.ttl  (new triples only — originals untouched)
"""

import time
import re
import requests
from rdflib import Graph, URIRef, Namespace
from rdflib.namespace import SKOS, OWL
import glob
import os

# ── Config ────────────────────────────────────────────────────────────────────
BASE         = "/sessions/fervent-festive-franklin/mnt/graphrag"
OUTPUTS_DIR  = os.path.join(BASE, "outputs")
OUT_TTL      = os.path.join(OUTPUTS_DIR, "lod_enrichment.ttl")
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


def get_all_concepts():
    """Load all .ttl files and collect every (concept_uri, prefLabel) pair."""
    combined = Graph()
    ttl_files = sorted(glob.glob(os.path.join(OUTPUTS_DIR, "*.ttl")))
    for path in ttl_files:
        name = os.path.basename(path)
        if name == "lod_enrichment.ttl":
            continue
        g = Graph()
        g.parse(path, format="turtle")
        combined += g
        print(f"  loaded {name}: {len(g):,} triples")

    q = """
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT DISTINCT ?concept ?label WHERE {
        ?concept a skos:Concept ;
                 skos:prefLabel ?label .
    }
    """
    results = []
    for row in combined.query(q):
        uri   = str(row["concept"])
        label = str(row["label"])
        results.append((uri, label))

    print(f"\nFound {len(results):,} unique concepts across all maps.")
    return results


def should_skip(label):
    words = label.strip().split()
    # Too short or too long for a named entity
    if len(words) < MIN_LABEL_WORDS or len(words) > 6:
        return True
    if label.strip().lower() in SKIP_LABELS:
        return True
    if re.match(r'^(ID_|http)', label):
        return True
    # Skip sentence fragments (ends in punctuation)
    if label.rstrip().endswith(('?', '.', ',', ':')):
        return True
    # Skip if looks like a screenshot filename
    if re.search(r'\d{4}-\d{2}-\d{2}', label):
        return True
    # Skip if majority of words are lowercase (sentence fragments, not named entities)
    lowercase_words = sum(1 for w in words if w.islower() and len(w) > 2)
    if lowercase_words / len(words) > 0.5:
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
    g = Graph()
    g.bind("owl",  OWL)
    g.bind("skos", SKOS)

    matched  = 0
    skipped  = 0
    no_match = 0
    total    = len(concepts)

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
            g.add((concept_ref, OWL.sameAs,      db_ref))
            g.add((concept_ref, SKOS.exactMatch, db_ref))
            matched += 1
        else:
            no_match += 1

    print(f"\nResults:")
    print(f"  Matched:  {matched:,}")
    print(f"  Skipped:  {skipped:,}  (too short / generic)")
    print(f"  No match: {no_match:,}")
    print(f"  Total new triples: {len(g):,}")
    return g, matched


def main():
    print("=== Week 4: LOD Enrichment — DBpedia ===\n")
    print("Loading TTL files...")
    concepts = get_all_concepts()

    print(f"\nQuerying DBpedia Lookup API...")
    print(f"(1 req/sec rate limit — this will take a while for large sets)\n")
    g, matched = build_enrichment_graph(concepts)

    g.serialize(destination=OUT_TTL, format="turtle")
    print(f"\nEnrichment triples saved to: {OUT_TTL}")
    print(f"Run complete. {matched:,} concepts linked to DBpedia.")


if __name__ == "__main__":
    main()
