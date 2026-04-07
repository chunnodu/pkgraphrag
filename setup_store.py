"""
setup_store.py
Loads all 10 .ttl output files + the ontology into a persistent Oxigraph store.
Run once to build the store; query with query_store.py afterwards.
"""

import pyoxigraph
import os
import glob

OUTPUTS_DIR = "/Users/chunnodu/projects/graphrag/outputs"
ONTOLOGY    = "/Users/chunnodu/projects/graphrag/pkg_ontology.ttl"
STORE_PATH  = "/Users/chunnodu/projects/graphrag/pkg_store"

def load_store():
    os.makedirs(STORE_PATH, exist_ok=True)
    store = pyoxigraph.Store(STORE_PATH)

    total_before = len(store)

    # Load ontology first
    print(f"Loading ontology: {ONTOLOGY}")
    store.bulk_load(open(ONTOLOGY, "rb"), format=pyoxigraph.RdfFormat.TURTLE)
    print(f"  ✓ ontology loaded")

    # Load each .ttl output file
    ttl_files = sorted(glob.glob(os.path.join(OUTPUTS_DIR, "*.ttl")))
    for ttl_path in ttl_files:
        name = os.path.basename(ttl_path)
        before = len(store)
        store.bulk_load(open(ttl_path, "rb"), format=pyoxigraph.RdfFormat.TURTLE)
        added = len(store) - before
        print(f"  ✓ {name}: +{added:,} triples")

    total_after = len(store)
    print(f"\nStore ready at: {STORE_PATH}")
    print(f"Total triples: {total_after:,} (+{total_after - total_before:,} added)")
    return store

if __name__ == "__main__":
    load_store()
