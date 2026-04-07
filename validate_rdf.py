"""
validate_rdf.py
Week 5 — SPARQL Query Suite + Graph Validation

Loads all 10 parsed .ttl maps + lod_enrichment.ttl into a combined in-memory
graph and runs 12 SPARQL queries covering:
  1.  Graph coverage summary
  2.  Missing prefLabel detection
  3.  Concepts with no parent (roots)
  4.  Concept hierarchy traversal (top N concepts by subtopic count)
  5.  Cross-domain skos:related links
  6.  Resource / URL retrieval by keyword
  7.  Task status filtering (done vs pending)
  8.  Log entries with dc:date
  9.  Cross-map concept overlap (same label, different source maps)
  10. LOD-enriched concepts (owl:sameAs)
  11. Concepts with notes (richcontent)
  12. Orphaned concepts (no parent, no children, no type assertion)

Usage:
    python validate_rdf.py                  # uses default OUTPUTS_DIR
    python validate_rdf.py /path/to/outputs # custom outputs dir

⚠️  pitchstone.mm and neogov.mm are permanently excluded — never parsed,
    never referenced.
"""

import sys
import os
import glob
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import SKOS, OWL, RDF

# ── Namespaces ────────────────────────────────────────────────────────────────
PKG    = Namespace("https://pkg.chunnodu.com/ontology#")
PKGC   = Namespace("https://pkg.chunnodu.com/concept/")
SCHEMA = Namespace("https://schema.org/")
DC     = Namespace("http://purl.org/dc/elements/1.1/")

DIVIDER = "─" * 60

# ── Helpers ───────────────────────────────────────────────────────────────────

def section(title):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def load_graph(outputs_dir):
    """Load all .ttl files in outputs_dir into a single combined graph."""
    combined = Graph()
    combined.bind("pkg",    PKG)
    combined.bind("pkgc",   PKGC)
    combined.bind("skos",   SKOS)
    combined.bind("owl",    OWL)
    combined.bind("schema", SCHEMA)
    combined.bind("dc",     DC)

    ttl_files = sorted(glob.glob(os.path.join(outputs_dir, "*.ttl")))
    if not ttl_files:
        print(f"[error] No .ttl files found in {outputs_dir}")
        sys.exit(1)

    print(f"Loading {len(ttl_files)} TTL files from {outputs_dir} ...")
    for path in ttl_files:
        name = os.path.basename(path)
        g = Graph()
        g.parse(path, format="turtle")
        combined += g
        print(f"  ✓ {name:55s} {len(g):>8,} triples")

    print(f"\n  Combined graph: {len(combined):,} triples total")
    return combined


# ── Query 1: Graph Coverage Summary ──────────────────────────────────────────

def q1_coverage(g):
    section("Q1 · Graph Coverage Summary")
    queries = {
        "Total triples":          "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }",
        "skos:Concept instances": "SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE { ?c a <http://www.w3.org/2004/02/skos/core#Concept> }",
        "pkg:hasSubTopic edges":  "SELECT (COUNT(*) AS ?n) WHERE { ?s <https://pkg.chunnodu.com/ontology#hasSubTopic> ?o }",
        "skos:related links":     "SELECT (COUNT(*) AS ?n) WHERE { ?s <http://www.w3.org/2004/02/skos/core#related> ?o }",
        "pkg:Resource instances": "SELECT (COUNT(DISTINCT ?r) AS ?n) WHERE { ?r a <https://pkg.chunnodu.com/ontology#Resource> }",
        "pkg:Task instances":     "SELECT (COUNT(DISTINCT ?t) AS ?n) WHERE { ?t a <https://pkg.chunnodu.com/ontology#Task> }",
        "pkg:PersonalNote nodes": "SELECT (COUNT(DISTINCT ?n) AS ?n) WHERE { ?n a <https://pkg.chunnodu.com/ontology#PersonalNote> }",
        "owl:sameAs (LOD) links": "SELECT (COUNT(*) AS ?n) WHERE { ?s <http://www.w3.org/2002/07/owl#sameAs> ?o }",
        "Source maps (distinct)": "SELECT (COUNT(DISTINCT ?m) AS ?n) WHERE { ?c <https://pkg.chunnodu.com/ontology#sourceMap> ?m }",
    }
    for label, q in queries.items():
        result = list(g.query(q))
        count = int(result[0][0]) if result else 0
        print(f"  {label:<35s} {count:>10,}")


# ── Query 2: Missing prefLabel ────────────────────────────────────────────────

def q2_missing_labels(g):
    section("Q2 · Concepts Missing skos:prefLabel")
    q = """
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?concept WHERE {
        ?concept a skos:Concept .
        FILTER NOT EXISTS { ?concept skos:prefLabel ?label }
    }
    """
    results = list(g.query(q))
    if not results:
        print("  ✓ All skos:Concept instances have a prefLabel.")
    else:
        print(f"  ⚠ {len(results)} concepts missing prefLabel:")
        for row in results[:20]:
            print(f"    {row.concept}")
        if len(results) > 20:
            print(f"    ... and {len(results) - 20} more")


# ── Query 3: Root Concepts (no parent) ───────────────────────────────────────

def q3_roots(g):
    section("Q3 · Root Concepts (no pkg:hasSubTopic parent)")
    q = """
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    SELECT ?label ?source WHERE {
        ?concept a skos:Concept ;
                 skos:prefLabel ?label ;
                 pkg:sourceMap  ?source .
        FILTER NOT EXISTS { ?parent pkg:hasSubTopic ?concept }
    }
    ORDER BY ?source
    """
    results = list(g.query(q))
    print(f"  {len(results)} root concept(s) found:\n")
    for row in results:
        print(f"  [{row.source}]  {row.label}")


# ── Query 4: Top Concepts by Subtopic Count ───────────────────────────────────

def q4_top_by_breadth(g):
    section("Q4 · Top 20 Concepts by Direct Subtopic Count (Breadth)")
    q = """
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    SELECT ?label ?source (COUNT(?child) AS ?childCount) WHERE {
        ?concept a skos:Concept ;
                 skos:prefLabel ?label ;
                 pkg:sourceMap  ?source ;
                 pkg:hasSubTopic ?child .
    }
    GROUP BY ?concept ?label ?source
    ORDER BY DESC(?childCount)
    LIMIT 20
    """
    results = list(g.query(q))
    print(f"  {'Label':<45} {'Map':<35} {'Children':>8}")
    print(f"  {'─'*45} {'─'*35} {'─'*8}")
    for row in results:
        label  = str(row.label)[:44]
        source = str(row.source)[:34]
        print(f"  {label:<45} {source:<35} {int(row.childCount):>8,}")


# ── Query 5: Cross-domain skos:related Links ──────────────────────────────────

def q5_cross_domain(g):
    section("Q5 · Cross-domain skos:related Links")
    q = """
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    SELECT ?aLabel ?aSource ?bLabel ?bSource WHERE {
        ?a skos:related ?b .
        ?a skos:prefLabel ?aLabel ;
           pkg:sourceMap  ?aSource .
        ?b skos:prefLabel ?bLabel ;
           pkg:sourceMap  ?bSource .
        FILTER (?aSource != ?bSource)
    }
    ORDER BY ?aSource ?bSource
    LIMIT 30
    """
    results = list(g.query(q))
    if not results:
        print("  No cross-domain skos:related links found.")
    else:
        print(f"  {len(results)} cross-domain link(s) (showing up to 30):\n")
        for row in results:
            a_src = str(row.aSource).split("/")[-1]
            b_src = str(row.bSource).split("/")[-1]
            print(f"  [{a_src}] {row.aLabel}  ←→  [{b_src}] {row.bLabel}")


# ── Query 6: Resource / URL Retrieval by Keyword ─────────────────────────────

def q6_resources_by_keyword(g, keyword="knowledge graph"):
    section(f"Q6 · Resources / URLs for Keyword: '{keyword}'")
    q = f"""
    PREFIX skos:   <http://www.w3.org/2004/02/skos/core#>
    PREFIX pkg:    <https://pkg.chunnodu.com/ontology#>
    PREFIX schema: <https://schema.org/>
    SELECT ?conceptLabel ?url WHERE {{
        ?concept skos:prefLabel ?conceptLabel ;
                 pkg:hasResource ?res .
        ?res schema:url ?url .
        FILTER (CONTAINS(LCASE(STR(?conceptLabel)), LCASE("{keyword}")))
    }}
    LIMIT 20
    """
    results = list(g.query(q))
    if not results:
        print(f"  No resources found for '{keyword}'.")
    else:
        print(f"  {len(results)} resource(s):\n")
        for row in results:
            print(f"  [{row.conceptLabel}]\n    {row.url}\n")


# ── Query 7: Task Status Filtering ───────────────────────────────────────────

def q7_tasks(g):
    section("Q7 · Task Status Filtering")
    # Tasks are stored as separate _task URIs linked from the concept via pkg:hasTask.
    # Labels and sourceMap live on the parent concept, not the task node itself.
    for status_val, label in [("done", "Completed tasks"), ("open", "Open tasks")]:
        q = f"""
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
        SELECT ?taskLabel ?source WHERE {{
            ?concept skos:prefLabel ?taskLabel ;
                     pkg:sourceMap  ?source ;
                     pkg:hasTask    ?task .
            ?task a pkg:Task ;
                  pkg:status "{status_val}" .
        }}
        ORDER BY ?source
        LIMIT 15
        """
        results = list(g.query(q))
        print(f"\n  {label} ({len(results)} shown, up to 15):")
        if not results:
            print("    (none found)")
        for row in results:
            src = str(row.source).split("/")[-1]
            print(f"    [{src}]  {row.taskLabel}")


# ── Query 8: Log Entries with dc:date ────────────────────────────────────────

def q8_log_entries(g):
    section("Q8 · Concepts with dc:date (Log Entries / Timestamped Nodes)")
    q = """
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    PREFIX dc:   <http://purl.org/dc/elements/1.1/>
    SELECT ?label ?date ?source WHERE {
        ?concept skos:prefLabel ?label ;
                 dc:date        ?date ;
                 pkg:sourceMap  ?source .
    }
    ORDER BY DESC(?date)
    LIMIT 20
    """
    results = list(g.query(q))
    if not results:
        print("  No timestamped concepts found.")
    else:
        print(f"  {len(results)} timestamped concept(s) (most recent first):\n")
        print(f"  {'Date':<25} {'Map':<20} Label")
        print(f"  {'─'*25} {'─'*20} {'─'*30}")
        for row in results:
            src = str(row.source).split("/")[-1]
            print(f"  {str(row.date):<25} {src:<20} {row.label}")


# ── Query 9: Cross-map Concept Overlap ───────────────────────────────────────

def q9_cross_map_overlap(g):
    section("Q9 · Cross-map Concept Overlap (Same Label, Different Source Maps)")
    q = """
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    SELECT ?label (COUNT(DISTINCT ?source) AS ?mapCount) (GROUP_CONCAT(DISTINCT ?source; separator=" | ") AS ?maps)
    WHERE {
        ?concept a skos:Concept ;
                 skos:prefLabel ?label ;
                 pkg:sourceMap  ?source .
    }
    GROUP BY ?label
    HAVING (?mapCount > 1)
    ORDER BY DESC(?mapCount)
    LIMIT 30
    """
    results = list(g.query(q))
    if not results:
        print("  No overlapping concept labels found across maps.")
    else:
        print(f"  {len(results)} label(s) appear in multiple maps:\n")
        print(f"  {'Label':<40} {'Maps':>5}  Source Files")
        print(f"  {'─'*40} {'─'*5}  {'─'*40}")
        for row in results:
            maps_str = str(row.maps).replace("https://pkg.chunnodu.com/concept/", "")
            # shorten map filenames
            parts = [m.strip().split("/")[-1] for m in str(row.maps).split("|")]
            print(f"  {str(row.label):<40} {int(row.mapCount):>5}  {' | '.join(parts)}")


# ── Query 10: LOD-enriched Concepts ──────────────────────────────────────────

def q10_lod_enriched(g):
    section("Q10 · LOD-enriched Concepts (owl:sameAs links)")
    q = """
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    PREFIX owl:  <http://www.w3.org/2002/07/owl#>
    SELECT ?label ?source ?externalURI WHERE {
        ?concept skos:prefLabel ?label ;
                 pkg:sourceMap  ?source ;
                 owl:sameAs     ?externalURI .
    }
    ORDER BY ?label
    LIMIT 40
    """
    results = list(g.query(q))
    dbpedia  = sum(1 for r in results if "dbpedia.org" in str(r.externalURI))
    wikidata = sum(1 for r in results if "wikidata.org" in str(r.externalURI))
    print(f"  LOD links found: {len(results)} total ({dbpedia} DBpedia, {wikidata} Wikidata)\n")
    seen = set()
    for row in results:
        label = str(row.label)
        if label not in seen:
            seen.add(label)
            db_tag = "DBpedia" if "dbpedia.org" in str(row.externalURI) else "Wikidata"
            print(f"  {label:<40} → {db_tag}: {str(row.externalURI).split('/')[-1]}")


# ── Query 11: Concepts with Notes ────────────────────────────────────────────

def q11_notes(g):
    section("Q11 · Concepts with Personal Notes (richcontent)")
    q = """
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    PREFIX dc:   <http://purl.org/dc/elements/1.1/>
    SELECT ?conceptLabel ?source ?noteTitle WHERE {
        ?concept skos:prefLabel ?conceptLabel ;
                 pkg:sourceMap  ?source ;
                 pkg:hasNote    ?note .
        OPTIONAL { ?note dc:title ?noteTitle }
    }
    ORDER BY ?source
    LIMIT 20
    """
    results = list(g.query(q))
    if not results:
        print("  No concepts with personal notes found.")
    else:
        print(f"  {len(results)} concept(s) with notes (up to 20):\n")
        for row in results:
            src   = str(row.source).split("/")[-1]
            title = str(row.noteTitle)[:50] if row.noteTitle else "(no title)"
            print(f"  [{src}]  {row.conceptLabel}  →  \"{title}\"")


# ── Query 12: Orphaned Concepts ───────────────────────────────────────────────

def q12_orphans(g):
    section("Q12 · Orphaned Concepts (no parent, no children, no outgoing relations)")
    q = """
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    SELECT ?label ?source WHERE {
        ?concept a skos:Concept ;
                 skos:prefLabel ?label ;
                 pkg:sourceMap  ?source .
        FILTER NOT EXISTS { ?parent pkg:hasSubTopic ?concept }
        FILTER NOT EXISTS { ?concept pkg:hasSubTopic ?child }
        FILTER NOT EXISTS { ?concept skos:related ?other }
        FILTER NOT EXISTS { ?concept pkg:hasResource ?res }
    }
    ORDER BY ?source
    LIMIT 20
    """
    results = list(g.query(q))
    if not results:
        print("  ✓ No fully orphaned concepts found.")
    else:
        print(f"  ⚠ {len(results)} orphaned concept(s) (up to 20):")
        for row in results:
            src = str(row.source).split("/")[-1]
            print(f"    [{src}]  {row.label}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    outputs_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "outputs"
    )

    print("=" * 60)
    print("  Personal Knowledge Graph — Week 5 Validation Suite")
    print("  12 SPARQL Queries across all 10 source maps + LOD")
    print("=" * 60)

    g = load_graph(outputs_dir)

    q1_coverage(g)
    q2_missing_labels(g)
    q3_roots(g)
    q4_top_by_breadth(g)
    q5_cross_domain(g)
    q6_resources_by_keyword(g, keyword="knowledge graph")
    q6_resources_by_keyword(g, keyword="data")
    q7_tasks(g)
    q8_log_entries(g)
    q9_cross_map_overlap(g)
    q10_lod_enriched(g)
    q11_notes(g)
    q12_orphans(g)

    print(f"\n{'=' * 60}")
    print("  Validation complete — 12 queries run.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
