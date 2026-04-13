# PKGraphRAG — Personal Knowledge Graph RAG System

A hybrid GraphRAG system built from personal Freeplane mindmaps. Combines deterministic SPARQL querying over an RDF knowledge graph with semantic vector search via LanceDB to enable grounded, natural-language Q&A over a personal knowledge base.

**Status:** Weeks 1–7 of 12 complete · Active development

---

## Architecture

```
Freeplane .mm files (10 maps)
        │
        ▼
parse_mm_to_rdf.py          ← .mm XML → RDF triples (rdflib)
        │
        ▼
outputs/*.ttl               ← 142,796 triples across 10 maps
        │
   ┌────┴────┐
   ▼         ▼
validate_rdf.py        embed_to_lancedb.py
(SPARQL queries)       (fastembed → LanceDB)
   │                         │
   ▼                         ▼
pkg_store/             pkg_lancedb/
(RDF triple store)     (31,983 vectors, 384-dim)
        │
        ▼
retrieve.py                 ← Hybrid retrieval (SPARQL + LanceDB)
        │
        ▼
   [Week 8] Claude API → grounded Q&A
```

---

## Knowledge Base

| Map | Domain | Concepts |
|---|---|---|
| `dlvr.mm` | Business / Ventures | 5,763 |
| `ajared.mm` | Ajared Research | 4,538 |
| `careerDevelopment.mm` | Career & Job Search | 4,131 |
| `new product Development Professional.mm` | Product Management | 4,199 |
| `data.mm` | Data Engineering | 2,187 |
| `life.mm` | Personal / Life | 2,826 |
| `Books.mm` | Library & Learning | 2,198 |
| `linkeddataSemanticWeb.mm` | AI + Linked Data | 1,912 |
| `blog.mm` | Blog Content | 729 |
| `geospatial.mm` | Geospatial | 172 |

**Total: 31,983 embedded concepts · 142,796 RDF triples**

> `pitchstone.mm` and `neogov.mm` are permanently excluded (employer-proprietary data).

---

## Scripts

| Script | Purpose |
|---|---|
| `parse_mm_to_rdf.py` | Parses all `.mm` files → `.ttl` RDF (rdflib). Handles node hierarchy, URLs, notes, tasks, timestamps, LOD exclusions. |
| `validate_rdf.py` | Runs 12 SPARQL queries to validate graph coverage, structure, and quality. |
| `lod_enrich.py` | Enriches root + depth-1/2 concept nodes with DBpedia / Wikidata `owl:sameAs` links. |
| `embed_to_lancedb.py` | Extracts concept labels from TTLs, prepends parent context, embeds via `BAAI/bge-small-en-v1.5`, stores in LanceDB. |
| `retrieve.py` | Hybrid retrieval: LanceDB semantic search → SPARQL graph expansion. Usable as CLI tool or importable module. |
| `visualise_ontology.py` | Renders the PKG ontology as a graph diagram. |
| `setup_store.py` | Initialises the RDF triple store. |

---

## Ontology

Namespace: `https://pkg.chunnodu.com/ontology#`

Built on standard vocabularies — `skos:` for concept hierarchy, `schema:` for typed resources, `dc:` for metadata — with a minimal custom `pkg:` namespace for project-specific types and properties.

Key custom types: `pkg:Task`, `pkg:PersonalNote`, `pkg:Resource`, `pkg:LogEntry`, `pkg:Goal`, `pkg:Project`

Key custom properties: `pkg:hasSubTopic`, `pkg:sourceMap`, `pkg:status`, `pkg:dateLogged`

See `pkg_ontology.ttl` for the full schema.

---

## Outputs

| Path | Contents |
|---|---|
| `outputs/*.ttl` | 10 RDF graphs (one per map) + `lod_enrichment.ttl` |
| `pkg_lancedb/` | LanceDB vector store — 31,983 concepts, 384-dim, 85 MB |
| `pkg_ontology.ttl` | Full PKG ontology in Turtle |
| `LOD_Concept_Inventory.xlsx` | 292-row inventory of LOD-enriched concepts |

---

## Roadmap

| Week | Focus | Status |
|---|---|---|
| 1–6 | Foundations, parsing, enrichment, SPARQL, embeddings | ✅ Done |
| 7 | Hybrid retrieval: SPARQL + LanceDB in a single pipeline | ✅ Done |
| 8 | Claude API integration: NL → retrieval → grounded answer | 🔄 Next |
| 9 | Answer quality refinement (80%+ pass rate target) | ⬜ |
| 10 | CLI query interface | ⬜ |
| 11–12 | Final polish, architecture diagram, v2 roadmap | ⬜ |

---

## Tech Stack

- **Python 3.10+** · rdflib · fastembed · lancedb · pyarrow
- **Embeddings:** `BAAI/bge-small-en-v1.5` (384-dim, ONNX via fastembed)
- **Vector DB:** LanceDB (embedded, no server)
- **RDF:** Turtle serialisation, SPARQL via rdflib
- **Source format:** Freeplane `.mm` (XML)
