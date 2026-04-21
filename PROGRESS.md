# Personal Knowledge GraphRAG — Consolidation Progress Summary

**As of April 21, 2026 | Weeks 1–8 Complete · Week 9 In Progress**

> ⚠️ **`pitchstone.mm` and `neogov.mm` are permanently excluded** — both contain proprietary data from employers. They are never to be parsed, queried, embedded, or referenced in any pipeline output. The active working set is **10 maps**, not 12.

---

## Current Status

| Week | Focus | Status | Notes |
|---|---|---|---|
| 1 | Inventory & consolidate all .mm files | ✅ Complete | 117 → 12 active maps; 41,868 nodes |
| 2 | Design RDF ontology schema in Turtle | ✅ Complete | `pkg_ontology.ttl` created 2026-03-23 |
| 3 | Python parser: .mm XML → RDF triples | ✅ Complete | `parse_mm_to_rdf.py` written; all 10 maps parsed |
| 4 | Parse remaining domains + LOD enrichment | ✅ Complete | All 10 maps parsed to `.ttl`; LOD enrichment done — 63 concepts linked to DBpedia/Wikidata; `lod_enrichment.ttl` (216 triples) |
| 5 | SPARQL queries + graph validation | ✅ Complete | 12 SPARQL queries passing; 142,796 triples; 27,776 concepts; richcontent parser fix (970→277 missing labels) |
| 6 | Generate embeddings → LanceDB vector DB | ✅ Complete | 31,983 concepts embedded (BAAI/bge-small-en-v1.5, 384-dim); `pkg_lancedb/` 85MB |
| 7 | Build hybrid retrieval pipeline | ✅ Complete | `retrieve.py` — SPARQL graph expansion + LanceDB vector search; 5/5 smoke tests passing |
| 8 | Connect Claude API + 20 Q&A test pairs | ✅ Complete | `ask.py` + `test_qa.py`; 20/20 passed; avg 4.4s; 16,850 in / 6,242 out tokens |
| 9 | RRF upgrade + prompt refinement + ontology gap-filling | 🔄 In progress | |
| 10 | CLI query interface + documentation | ✅ Done early | `ask.py` complete; CLI working |
| 11 | Final polish + architecture diagram | ⬜ Pending | |
| 12 | Reflect + v2 roadmap | ⬜ Pending | |

---

## Week 9 Plan — RRF Upgrade + Quality Refinement 🔄

Week of April 20–26, 2026.

### Architecture Correction

Review of `retrieve.py` confirmed the retrieval path is **sequential, not parallel**: vector search runs first to identify the top-K entry-point URIs, then SPARQL expands each URI. There is only one ranked signal (vector similarity), so no fusion is occurring. The current "hybrid" label is a misnomer — it is retrieve-then-traverse.

### RRF Upgrade Plan

Add a second independent retrieval signal to enable true Reciprocal Rank Fusion:

```
User Question
    ├─ Path A → Query Embedder → Vector Search → Ranked List A (by cosine similarity)
    └─ Path B → Keyword Tokenizer → Full-Text Search on labels → Ranked List B (keyword match)
                        ↓
               RRF Fusion: score = Σ 1/(60 + rank)
                        ↓
               Graph Expansion (unchanged)
                        ↓
               Context Builder → Language Model
```

**Implementation (~20 lines + 1 config change):**
1. Enable LanceDB FTS index on the `label` column in `embed_to_lancedb.py`
2. Add `KeywordRetriever` class to `retrieve.py` (wraps `table.search(query, query_type="fts")`)
3. Add `rrf_fuse(list_a, list_b, k=60)` function — merges two ranked URI lists
4. Update `HybridRetriever.retrieve()` to call both retrievers and fuse before graph expansion

**Why RRF:** No manual weight tuning. Parameter-free. Consistently outperforms fixed-weight combinations across query types. Corrects a known weakness — queries where the exact concept label matches poorly to the vector (e.g. proper nouns, acronyms) will now surface via FTS.

See `architecture_rrf.svg` for the full diagram.

### Quality Targets (Week 9)
- 20/20 Q&A baseline already achieved (Week 8) — target is to hold at 20/20 after RRF change
- Fix ontology gaps flagged in Week 8: Q09 (data pipelines), Q11 (RDF/SPARQL depth), Q15 (explicit life goals)
- Prompt refinement: tighten system prompt to reduce verbosity on well-covered topics

---

## Week 8 Summary — Claude API Integration ✅

Completed April 17, 2026. Wired the hybrid retrieval pipeline into Claude for end-to-end grounded Q&A.

### New Scripts
- `ask.py` — core integration: retrieves context via `HybridRetriever`, injects it into a system prompt, calls Claude API, returns structured result (answer, tokens, timing). Works as CLI and importable module.
- `test_qa.py` — 20 test questions spanning all 10 source maps (2 per major map, cross-domain synthesis questions). Outputs `outputs/week8_qa_results.json` and `outputs/week8_qa_report.md`.

### Results (20/20 passed)

| Metric | Value |
|---|---|
| Questions run | 20 |
| Pass rate | 20/20 (100%) |
| Model | claude-haiku-4-5-20251001 |
| Avg response time | 4.4s |
| Total input tokens | 16,850 |
| Total output tokens | 6,242 |

### Key Observations
- Answers are grounded and honest — Claude correctly flagged thin coverage on data pipelines (Q09), RDF/SPARQL technical depth (Q11), and explicit life goals (Q15) rather than hallucinating
- Cross-domain synthesis (Q19, Q20) worked well — surfacing the Data & AI Strategy node and connecting enterprise AI product thinking across maps
- Personal notes surfaced naturally (DLVR "many dead bodies" note, AI "going through the motions" concern)
- System prompt tuned to answer from retrieved context, cite source maps, and stay concise

### CLI Usage
```bash
python ask.py "What do I know about business model design?"
python ask.py "machine learning pipelines" --top-k 10
python ask.py "career goals" --map careerDevelopment.mm
python test_qa.py                          # run all 20 test pairs
python test_qa.py --dry-run                # retrieval only, no API calls
```

---

## Week 7 Summary — Hybrid Retrieval Pipeline ✅

Completed April 12, 2026. Built `retrieve.py` — a fully working hybrid retrieval module that combines LanceDB semantic search with rdflib graph expansion.

### Architecture

```
NL Question
    ↓
[1] SemanticRetriever (LanceDB)
    → BAAI/bge-small-en-v1.5 embedding of query
    → top-K concept URIs + similarity scores (1 − _distance)

    ↓
[2] GraphRetriever (rdflib + SPARQL)
    → For each URI: parent, children, siblings, notes, resources, LOD links
    → 6 parameterised SPARQL templates per concept

    ↓
[3] HybridRetriever (orchestrator)
    → Deduplicates by URI
    → Sorts by semantic score descending
    → Returns RetrievalResult (list of ConceptContext dataclasses)

    ↓
[4] Formatted output
    → Plain-text context block (for LLM prompts)  or JSON (for programmatic use)
```

### Key Design Decisions

- **Retrieval-first**: Vector search runs first to identify the most relevant URIs; SPARQL then enriches those specific nodes — avoiding full-graph traversal on every query.
- **Dataclasses**: `ConceptContext` and `RetrievalResult` are typed, serialisable, and ready to pass directly to the Claude API in Week 8.
- **Dual output formats**: `.as_text()` renders a human-readable context block; `.as_json()` exports full structured data.
- **Source-map filtering**: Optional `--map` flag lets queries be scoped to a single mindmap (e.g. `careerDevelopment.mm`).
- **Exclusions enforced**: `pitchstone.mm` and `neogov.mm` are hard-excluded at the graph load level, same as all prior weeks.

### Smoke Test Results (5/5 ✅)

| Query | Top Hit | Score | Source |
|---|---|---|---|
| "business model design" | Ideation | 0.712 | Books.mm |
| "machine learning and data pipelines" | Generative Engine Optimization | 0.572 | ajared.mm |
| "career development and job search strategy" | Career Development and Support | 0.551 | ajared.mm |
| "linked data and semantic web" | Ontologies and Semantic Data Layer | 0.649 | ajared.mm |
| "personal finance and life goals" | mindmap life goals | 0.502 | Books.mm |

### CLI Usage

```bash
python retrieve.py "What do I know about business model design?"
python retrieve.py "machine learning pipelines" --top-k 10 --map data.mm
python retrieve.py "career goals" --format json
```

### Scripts
- `retrieve.py` — main hybrid retrieval module; usable as both CLI tool and importable Python module

---

## Week 6 Summary — LanceDB Embedding Pipeline ✅

Completed April 7, 2026. All 31,983 concepts from the 10 source maps embedded and stored in a local LanceDB vector database.

### Key Decisions
- **Model:** `BAAI/bge-small-en-v1.5` via `fastembed` (ONNX, lightweight — no PyTorch required)
- **Vector DB:** LanceDB (switched from Chroma — runs embedded with no server, columnar storage, fast metadata filtering by source map)
- **Context strategy:** Each concept label is prepended with its parent label (e.g. `"Business Model > Canvas"`) before embedding, so vectors carry hierarchical context rather than isolated words

### Stats

| Metric | Value |
|---|---|
| Total concepts embedded | 31,983 |
| Vector dimensions | 384 |
| DB size on disk | 85 MB |
| DB location | `pkg_lancedb/` |
| Filtering | By `source_map` field (e.g. `ajared.mm`, `dlvr.mm`) |

### Smoke Test Results

| Query | Top Hit |
|---|---|
| "business model strategy" | `Strategy` (Books, 0.863) |
| "machine learning and data pipelines" | `Supervised Learning` (NPD Professional, 0.725) |
| "career development job search" | `Target Job Description` (careerDevelopment, 0.723) |
| "personal finance and life goals" | `Major Life Goals` (life, 0.592) |

### Scripts
- `embed_to_lancedb.py` — main pipeline (extract → embed → store); processes one TTL at a time to stay within memory limits
- `embed_one.py` — single-file subprocess worker called by the pipeline

---

## Week 5 Summary — SPARQL Queries + Graph Validation ✅

Completed April 6, 2026. Extended `validate_rdf.py` to 12 SPARQL queries covering the full graph.

### Final Graph Stats

| Metric | Value |
|---|---|
| Total triples | 142,796 |
| `skos:Concept` instances | 27,776 |
| `pkg:hasSubTopic` edges | 27,810 |
| `pkg:Task` instances | 133 |
| `pkg:PersonalNote` nodes | 197 |
| `owl:sameAs` LOD links | 108 (40 distinct: 22 DBpedia, 18 Wikidata) |
| Source maps | 10 |

### Query Suite (Q1–Q12)

| Query | Focus | Result |
|---|---|---|
| Q1 | Graph coverage summary | ✅ |
| Q2 | Concepts missing `skos:prefLabel` | 277 remaining (down from 970 — genuine blanks) |
| Q3 | Root concepts (no parent) | 7 roots found |
| Q4 | Top 20 concepts by child count | ✅ |
| Q5 | Cross-domain `skos:related` links | 0 (none authored yet) |
| Q6 | Resources/URLs by keyword | ✅ |
| Q7 | Task status filtering | 15 completed, 0 open ✅ |
| Q8 | Timestamped nodes (dc:date) | Most recent: 2026-04-01 (linkeddataSemanticWeb) |
| Q9 | Cross-map concept label overlap | 0 overlapping labels |
| Q10 | LOD-enriched concepts | 40 distinct links ✅ |
| Q11 | Concepts with personal notes | ✅ |
| Q12 | Orphaned concepts | 0 orphans ✅ |

### Parser Fix Applied
`parse_mm_to_rdf.py` updated to fall back to `<richcontent TYPE="NODE">` HTML body when `TEXT=""`. Missing prefLabel count dropped from **970 → 277** (71% reduction).

---

## Week 4 Summary — LOD Enrichment ✅

Enriched entity URIs with links to DBpedia and Wikidata. `lod_enrich.py` queries DBpedia Spotlight and Wikidata SPARQL for root, depth-1, and depth-2 concept nodes across all 10 maps.

### Output
- `outputs/lod_enrichment.ttl` — 216 triples
- `LOD_Concept_Inventory.xlsx` — 292 rows (10 roots + 282 depth-1 nodes)
- 40 distinct LOD links: 22 DBpedia, 18 Wikidata
- All links use `owl:sameAs`

---

## Week 3 Summary — Python Parser ✅

Created `parse_mm_to_rdf.py`. Parser handles:
- Tree traversal (recursive), mapping every node to `skos:Concept` with `pkg:hasSubTopic` edges
- External HTTP links → `schema:WebPage` resource instances via `pkg:hasResource`
- Rich content notes (`<richcontent TYPE="NOTE">`) → `pkg:PersonalNote` via `pkg:hasNote`
- Freeplane arrowlinks → `skos:related` cross-links
- Icon detection (`button_ok`) → `pkg:Task` with `pkg:status "done"`
- CREATED epoch timestamps → `dc:date`
- Hard exclusion of `pitchstone.mm` and `neogov.mm`
- Fallback to `<richcontent TYPE="NODE">` HTML body when `TEXT=""` (added Week 5)

### Output Files Generated (`outputs/`)
All 10 maps → `.ttl`: `linkeddataSemanticWeb`, `ajared`, `careerDevelopment`, `dlvr`, `data`, `life`, `Books`, `new product Development Professional`, `blog`, `geospatial`

---

## Week 2 Summary — RDF Ontology Design ✅

Created `pkg_ontology.ttl` on 2026-03-23. Design decisions:
- Reuse `skos:` for concept hierarchy and lateral links
- Reuse `schema:` for typed resources (Book, Course, WebPage, etc.)
- Reuse `dc:` for descriptive metadata
- Custom `pkg:` namespace only for types/predicates with no standard fit
- All Freeplane nodes become `skos:Concept` instances; URLs become `pkg:Resource` instances
- Parent→child edges carry `pkg:hasSubTopic` (subproperty of `skos:narrower`)

### Custom Classes Defined
`pkg:Resource`, `pkg:LearningMaterial`, `pkg:HowTo`, `pkg:Presentation`, `pkg:WorkingGroup`, `pkg:PersonalNote`, `pkg:Event`, `pkg:Task`, `pkg:Project`, `pkg:Goal`, `pkg:LogEntry`, `pkg:BlogPost`, `pkg:Organization`

### Key Properties Defined
`pkg:hasSubTopic`, `pkg:hasResource`, `pkg:hasLearningMaterial`, `pkg:hasProcedure`, `pkg:hasPresentation`, `pkg:hasNote`, `pkg:hasTask`, `pkg:hasProject`, `pkg:hasGoal`, `pkg:hasLogEntry`, `pkg:hasOrganization`, `pkg:sourceMap`, `pkg:status`, `pkg:dueDate`, `pkg:dateLogged`

---

## Week 1 Summary — Inventory & Consolidation ✅

Started with 117 Freeplane `.mm` files spread across 9 domains — Books, Business/Ventures, Career, Data Engineering, GIS, Personal/Life, Product Management, Semantics/KG, and Other — containing 44,610 nodes in total, many of them duplicated across redundant files. Over 9 tracked iterations, brought that down to 12 clean, active master maps holding 41,868 nodes — a 90% reduction in file count with only a 6% reduction in content, almost entirely explained by intentional deduplication.

### Key Metrics

| Metric | Before | After | Change |
|---|---|---|---|
| File count | 117 | 12 | −90% |
| Total nodes | 44,610 | 41,868 | −6% |
| Average depth | 6.5 | 12.8 | +97% |
| Files with cross-links | 36 (31%) | 12 (100%) | All linked |

### Active Files (10 — post exclusions)

| File | Root Topic | Nodes | Depth |
|---|---|---|---|
| `dlvr.mm` | DLVR / Business | 5,864 | 12 |
| `ajared.mm` | Ajared | 4,588 | 12 |
| `careerDevelopment.mm` | Career Dev | 4,204 | 14 |
| `new product Development Professional.mm` | NPD Professional | 4,178 | 13 |
| `data.mm` | Data | 2,202 | 13 |
| `life.mm` | Life | 2,110 | 11 |
| `Books.mm` | Library & Learning | 2,204 | 10 |
| `linkeddataSemanticWeb.mm` | AI + Linked Data | 1,857 | 12 |
| `blog.mm` | Blog | 742 | 11 |
| `geospatial.mm` | Geospatial Knowledge | 174 | 7 |

**Total: ~27,923 nodes across 10 active files** (excl. pitchstone + neogov)
