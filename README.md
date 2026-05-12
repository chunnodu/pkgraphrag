# PKGraphRAG — Personal Knowledge Graph RAG System

A hybrid GraphRAG system built from personal Freeplane mindmaps. Combines deterministic SPARQL querying over an RDF knowledge graph with semantic vector search and full-text search via LanceDB, fused with Reciprocal Rank Fusion (RRF), to enable grounded natural-language Q&A over a personal knowledge base.

**Status:** All 12 weeks complete ✅ · 20/20 Q&A tests passing

---

## Quick Start

```bash
# 1. Install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Set API key
export ANTHROPIC_API_KEY=sk-ant-...

# 3. Ask a question
python ask.py "What do I know about business model design?"
```

---

## Usage

### Q&A (`ask.py`)

```bash
python ask.py "What do I know about business model design?"
python ask.py "DLVR strategy" --debug --show-context
python ask.py "machine learning pipelines" --top-k 10
python ask.py "career goals" --map careerDevelopment.mm
python ask.py "linked data" --model claude-sonnet-4-6 --max-tokens 2048
```

| Flag | Default | Description |
|---|---|---|
| `--top-k` | 8 | Number of fused concepts passed to Claude |
| `--map` | all | Scope retrieval to one source map |
| `--model` | haiku-4-5 | Claude model |
| `--max-tokens` | 1024 | Max tokens in Claude response |
| `--show-context` | off | Print retrieved context before the answer |
| `--debug` | off | Show per-path vector/keyword hits before RRF fusion |

### Retrieval only (`retrieve.py`)

```bash
python retrieve.py "What do I know about business model design?"
python retrieve.py "DLVR" --debug
python retrieve.py "linked data" --format json
python retrieve.py "career goals" --map careerDevelopment.mm --top-k 12
```

### Run all 20 Q&A tests

```bash
python test_qa.py                          # full run (calls Claude)
python test_qa.py --dry-run                # retrieval only, no API calls
python test_qa.py --model claude-sonnet-4-6
```

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
(SPARQL queries)       (fastembed → LanceDB + FTS index)
                             │
                             ▼
                       pkg_lancedb/          ← 31,983 vectors (384-dim) + FTS index
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
       Vector Search                  FTS on labels
       (cosine similarity)            (exact/keyword match)
              │                             │
              └──────────┬──────────────────┘
                         ▼
                   RRF Fusion (k=60)
                   score = Σ 1/(60 + rank)
                         │
                         ▼
                  SPARQL Graph Expansion      ← parent, children, siblings,
                  (top-8 fused URIs)             notes, resources, LOD links
                         │
                         ▼
                    ask.py                   ← Claude API → grounded Q&A
```

**Why RRF:** Vector search is great for semantic similarity but weak on exact labels — acronyms, proper nouns, initialisms. FTS catches these precisely. RRF merges both ranked lists with no manual weight tuning.

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
| `embed_to_lancedb.py` | Extracts concept labels from TTLs, prepends parent context, embeds via `BAAI/bge-small-en-v1.5`, stores in LanceDB with FTS index. |
| `retrieve.py` | RRF hybrid retrieval: vector search + FTS → RRF fusion → SPARQL graph expansion. Usable as CLI or importable module. |
| `ask.py` | End-to-end Q&A: calls `HybridRetriever`, assembles context, calls Claude API, returns structured result. |
| `test_qa.py` | Runs 20 test questions across all 10 maps, outputs JSON + markdown report. |
| `visualise_ontology.py` | Renders the PKG ontology as a graph diagram. |

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
| `pkg_lancedb/` | LanceDB vector store — 31,983 concepts, 384-dim, 85 MB + FTS index |
| `pkg_ontology.ttl` | Full PKG ontology in Turtle |
| `LOD_Concept_Inventory.xlsx` | 292-row inventory of LOD-enriched concepts |

---

## Tech Stack

- **Python 3.10+** · rdflib · fastembed · lancedb · pyarrow · anthropic
- **Embeddings:** `BAAI/bge-small-en-v1.5` (384-dim, ONNX via fastembed — no PyTorch)
- **Vector DB:** LanceDB (embedded, no server)
- **RDF:** Turtle serialisation, SPARQL via rdflib
- **Source format:** Freeplane `.mm` (XML)

---

## Roadmap

| Week | Focus | Status |
|---|---|---|
| 1–6 | Foundations, parsing, enrichment, SPARQL, embeddings | ✅ Done |
| 7 | Hybrid retrieval: vector search → SPARQL graph expansion | ✅ Done |
| 8 | Claude API integration: 20/20 Q&A tests passing (100%) | ✅ Done |
| 9 | RRF upgrade: KeywordRetriever + FTS index + rrf_fuse() | ✅ Done |
| 10 | CLI polish: --debug flag, requirements.txt, README | ✅ Done |
| 11–12 | Final architecture diagram, retrospective, v2 roadmap | ✅ Done |
