# Personal Knowledge Graph RAG — 12-Week Build Plan

## ⚠️ PERMANENT EXCLUSIONS — Employer-Proprietary Maps

The following maps are **permanently excluded** from all work in this project:

| File | Reason |
|---|---|
| `pitchstone.mm` | Proprietary data — former employer |
| `neogov.mm` | Proprietary data — current/former employer |

Both files must never be parsed, queried, converted to RDF, embedded, or referenced in any pipeline output. The parser (Week 3+) must explicitly skip both files by filename. They must not appear in any inventory updates, SPARQL results, or vector DB loads.

This exclusion applies to all future sessions, tools, scripts, and AI assistance on this project.

---

## Objective
Build a Hybrid GraphRAG system utilizing Freeplane mindmaps (.mm files) as the primary knowledge source. The system connects deterministic querying (SPARQL/RDF) with semantic search (Vector DB) to provide grounded LLM Q&A capabilities.

## Timeline & Deliverables

| Week | Dates | Phase | Weekly Focus | Key Deliverable | Done? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | Feb 23–Mar 1 | 🔍 Foundations | Inventory all FreeMind/Freeplane .mm files; categorize by domain (PM, GIS, Semantics, Books, Life) | Domain inventory doc + file list | [x] |
| **2** | Mar 2–8 | 🔍 Foundations | Study .mm XML structure; design RDF ontology schema in Turtle — map mind map nodes/edges to RDF classes/properties | Draft ontology .ttl file | [ ] |
| **3** | Mar 9–15 | 🛠 Build | Write Python parser: .mm XML → RDF triples (rdflib); run on first domain (e.g. Semantic web maps) | First domain loaded into QLever | [ ] |
| **4** | Mar 16–22 | 🛠 Build | Parse remaining domains; enrich entities with LOD links (DBpedia, Wikidata URIs where applicable) | All .mm files converted; cross-domain triples linked | [ ] |
| **5** | Mar 23–29 | 🛠 Build | Write and test SPARQL queries across domains; validate graph structure and coverage | 10+ working SPARQL queries | [ ] |
| **6** | Mar 30–Apr 5 | ⚙️ Integration | Generate embeddings for RDF node labels + literals; store in LanceDB vector DB | Embeddings stored + searchable | [ ] |
| **7** | Apr 6–12 | ⚙️ Integration | Build hybrid retrieval: SPARQL for structured traversal + semantic similarity for fuzzy NL matching | Retrieval pipeline returns grounded context | [ ] |
| **8** | Apr 13–19 | ⚙️ Integration | Connect Claude API: NL question → SPARQL + semantic retrieval → grounded answer; test with 20 real questions | 20 Q&A pairs evaluated | [ ] |
| **9** | Apr 20–26 | 📈 Expand | Improve answer quality: refine prompts, fix gaps in ontology, add missing triples from mind maps | Answer quality pass rate 80%+ | [ ] |
| **10** | Apr 27–May 3 | 📈 Expand | Add simple CLI query interface; document the ontology and query patterns | Working CLI: ask a question, get an answer from your own knowledge | [ ] |
| **11** | May 4–10 | 🚀 Ship | Final polish: README, architecture diagram, example queries | Repo documented + demo-ready ✅ | [ ] |
| **12** | May 11–17 | 🚀 Ship | Reflect + roadmap: what to add next (new domains, richer LOD links, UI) | v2 roadmap written | [ ] |

---

## Technical Context & Findings (As of April 6, 2026)

### Existing Project Assets

The `/Users/chunnodu/projects/graphrag` folder currently acts as the administrative and tracking hub for this project:

1. **`KG_W1_Inventory.xlsx`** (Knowledge Graph Inventory)
   - **Status:** **Completed (Week 1)**. 
   - **Contents:** Tracks 117 mindmap files containing 44,610 nodes. Domains mapped include *Business/Ventures* (~20k nodes), *Career/Job Search* (~6k nodes), *Books/Learning* (~2k nodes), *Product Management*, *Data Engineering*, and *Personal/Life*. Tracks metrics like Average Depth (6.5 overall), Cross-links (36 files), and size categorization.

2. **Freeplane Version & AI Context Setup**
   - **Application Version:** Freeplane v1.13.2.
   - **AI Integration (MCP Server):** An active Freeplane AI Context MCP connection has been successfully established on **port 6298**. This allows local scripts/AI agents to query the *currently active/open* mindmap in the Freeplane UI in real-time.
   - **API Configurations:** The Freeplane AI preferences are configured with OpenRouter, Gemini (using models like `gemini-2.5-pro` and `gemini-3-pro-preview`), and Ollama integration URLs.

3. **Virtual Environment**
   - A standard Python `.venv` environment exists in the root directory, ready for the upcoming Python parsing and RDF processing scripts (Week 3+).

### Technical Observations & Recommendations for Next Steps

*   **Tree vs. Graph Mapping (Week 3/4):** Freeplane XML defaults strictly to nested tree nodes. When mapping to an RDF Ontology, decide on strict structural conventions (e.g., *Is a child node a property of the parent, or a separate class instance?*).
*   **Vector Context Retention (Week 6):** Embeddings generated solely from a node's literal text can lose context (embedding the word "Testing" out of context). Consider prepending ancestor node context strings to each embedded leaf node.
*   **Live/MCP Agent Potential:** While the 12-week plan builds a batch pipeline to an external Triplestore (QLever), the active Freeplane MCP server connection opens doors for secondary capabilities, such as an AI agent writing *back* into Freeplane directly.

### Week 5 Completion Notes (April 6, 2026)

- **Parser re-run completed** — richcontent fix applied; missing prefLabel count dropped from 970 → 277 (71% reduction). Remaining 277 are genuinely unlabeled nodes with no TEXT or richcontent in the source `.mm` files.
- **12 SPARQL queries all passing** in `validate_rdf.py` — Q1 through Q12 across all 10 source maps.
- **Graph stats:** 142,796 total triples | 27,776 `skos:Concept` instances | 133 tasks | 197 personal notes | 108 LOD links (40 distinct: 22 DBpedia, 18 Wikidata).
- **Q9 (cross-map overlap):** 0 overlapping labels — concepts are sufficiently domain-specific across maps.
- **MindMaps folder** now available as a mounted Cowork directory for direct parser access — no more manual file copy needed.

### Week 6 Decision: LanceDB (not Chroma)

Vector DB choice changed from **Chroma → LanceDB** for the following reasons:
- Runs fully embedded (no server process) — files sit alongside the TTLs in the project folder
- Columnar format enables fast pre-filtering by source map before vector search
- Better fit for a single-user personal KG at ~27k concepts scale
- Alternatives considered: Weaviate (too heavy), Qdrant (solid but more setup than needed)
