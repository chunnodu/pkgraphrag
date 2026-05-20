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

# Qwen via Dashscope (OpenAI-compatible)
export OPENAI_API_KEY=sk-...
python ask.py "career goals" --provider openai --model qwen-plus \
  --base-url https://dashscope.aliyuncs.com/compatible-mode/v1

# Local Ollama
python ask.py "career goals" --provider openai --model llama3 \
  --base-url http://localhost:11434/v1
```

| Flag | Default | Description |
|---|---|---|
| `--top-k` | 8 | Number of fused concepts passed to LLM |
| `--map` | all | Scope retrieval to one source map |
| `--model` | haiku-4-5 | Model name |
| `--provider` | anthropic | `anthropic` or `openai` (any OpenAI-compatible endpoint) |
| `--base-url` | — | Base URL for OpenAI-compatible endpoint (Qwen, Ollama, Groq…) |
| `--max-tokens` | 1024 | Max tokens in response |
| `--show-context` | off | Print retrieved context before the answer |
| `--debug` | off | Show per-path vector/keyword hits before RRF fusion |

### Retrieval only (`retrieve.py`)

```bash
python retrieve.py "What do I know about business model design?"
python retrieve.py "DLVR" --debug
python retrieve.py "linked data" --format json
python retrieve.py "career goals" --map careerDevelopment.mm --top-k 12
```

### MCP Server (`mcp_server.py`)

Use the knowledge graph as a tool directly inside **Claude Desktop** or **Claude Code** — no separate terminal needed.

```bash
# Register with Claude Code (one-time)
claude mcp add pkgraphrag \
  /Users/chunnodu/projects/graphrag/.venv/bin/python \
  /Users/chunnodu/projects/graphrag/mcp_server.py
```

For **Claude Desktop**, add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
"pkgraphrag": {
  "command": "/Users/chunnodu/projects/graphrag/.venv/bin/python",
  "args": ["/Users/chunnodu/projects/graphrag/mcp_server.py"]
}
```

Then restart Claude Desktop and ask questions naturally — Claude will call `search_knowledge_graph` automatically.

| Tool | Description |
|---|---|
| `search_knowledge_graph(query, top_k, source_map)` | Hybrid RRF retrieval → graph expansion → formatted context |
| `list_source_maps()` | Lists all 10 maps with domain labels |

> Cold start: ~3.5s on first query (TTL + LanceDB load). Subsequent queries are instant.

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
ingest/parse.py             ← .mm XML → RDF triples (rdflib)
        │
        ▼
outputs/*.ttl               ← 142,796 triples across 10 maps
        │
   ┌────┴────┐
   ▼         ▼
ingest/      ingest/
validate.py  embed.py       ← fastembed → LanceDB + FTS index
                             │
                             ▼
                       pkg_lancedb/          ← 31,983 vectors (384-dim) + FTS index
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
  retrieval/semantic.py        retrieval/keyword.py
  (cosine vector search)       (FTS on labels)
              │                             │
              └──────────┬──────────────────┘
                         ▼
              retrieval/fusion.py  ← RRF (k=60): score = Σ 1/(60 + rank)
                         │
                         ▼
              retrieval/graph.py   ← SPARQL expansion: parent, children,
              (top-8 fused URIs)      siblings, notes, resources, LOD links
                         │
                         ▼
                    qa/ask.py      ← Claude API → grounded Q&A
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

## Package Structure

```
retrieval/          Runtime retrieval pipeline
  models.py         Shared constants, namespaces, ConceptContext, RetrievalResult
  semantic.py       SemanticRetriever — LanceDB cosine vector search
  keyword.py        KeywordRetriever  — LanceDB FTS on concept labels
  fusion.py         rrf_fuse()        — Reciprocal Rank Fusion
  graph.py          GraphRetriever    — rdflib SPARQL graph expansion
  hybrid.py         HybridRetriever   — orchestrator + CLI entry point

qa/                 LLM layer
  ask.py            ask() function, SYSTEM_PROMPT, CLI entry point (multi-provider)
  test_qa.py        20-question regression test suite

mcp_server.py       MCP server — exposes retrieval as Claude tools (FastMCP)
reindex.py          Rebuild LanceDB index from TTL files + recreate FTS index

ingest/             Build-time pipeline (run once to rebuild the knowledge base)
  parse.py          .mm XML → RDF triples (rdflib)
  validate.py       12 SPARQL validation queries
  enrich.py         DBpedia / Wikidata owl:sameAs enrichment
  embed.py          fastembed → LanceDB vectors + FTS index

utils/
  visualise.py      Renders pkg_ontology.ttl as a graph diagram

docs/
  architecture.mermaid / architecture_final.html
  PROGRESS.md       Week-by-week log + v2 roadmap
  plan_and_context.md
```

Root-level `ask.py`, `retrieve.py`, and `test_qa.py` are thin shims that delegate to the packages above — existing CLI usage is unchanged.

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

- **Python 3.10+** · rdflib · fastembed · lancedb · pyarrow · anthropic · openai · mcp
- **Embeddings:** `BAAI/bge-small-en-v1.5` (384-dim, ONNX via fastembed — no PyTorch)
- **Vector DB:** LanceDB (embedded, no server)
- **RDF:** Turtle serialisation, SPARQL via rdflib
- **LLM providers:** Anthropic (default) or any OpenAI-compatible endpoint (Qwen, Ollama, Groq…)
- **MCP:** FastMCP server for Claude Desktop / Claude Code tool integration
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
