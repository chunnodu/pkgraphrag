"""MCP server — exposes the PKGraphRAG retrieval pipeline as Claude tools.

Register with Claude Code:
    claude mcp add pkgraphrag \
        /Users/chunnodu/projects/graphrag/.venv/bin/python \
        /Users/chunnodu/projects/graphrag/mcp_server.py

Then ask Claude: "What do I know about business model design?"
and it will call search_knowledge_graph automatically.
"""

from __future__ import annotations

import os
import sys

# Ensure project root is on the path when invoked directly by an MCP host
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from mcp.server.fastmcp import FastMCP
from retrieval import HybridRetriever, DEFAULT_TOP_K
from retrieval.models import EXCLUDED_MAPS, OUTPUTS_DIR

mcp = FastMCP(
    "PKGraphRAG",
    instructions=(
        "Tools for searching the user's personal knowledge graph — "
        "31,983 concepts from 10 Freeplane mind maps covering data engineering, "
        "career, business strategy, linked data, geospatial, life goals, books, and more. "
        "Call search_knowledge_graph whenever the user asks about something they might "
        "have noted or researched. Use list_source_maps first if you need to scope a "
        "query to a specific topic area."
    ),
)

# Load once at startup — this is the expensive step (~2-3 s for TTL + LanceDB)
_retriever: HybridRetriever | None = None


def _get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever(verbose=False)
    return _retriever


@mcp.tool()
def search_knowledge_graph(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    source_map: str = "",
) -> str:
    """Search the personal knowledge graph using hybrid RRF retrieval.

    Combines semantic vector search (meaning) with full-text search (exact labels,
    acronyms, proper nouns), fused via Reciprocal Rank Fusion, then expands each
    result through the RDF graph to include parent concepts, children, siblings,
    personal notes, saved resources, and Linked Open Data links.

    Args:
        query:      Natural-language question or keyword(s) to search for.
        top_k:      Number of concepts to retrieve (default 8, max ~20).
        source_map: Restrict search to one map (e.g. "dlvr.mm", "data.mm").
                    Leave empty to search all maps.

    Returns:
        Formatted context block ready to reason over — concept labels,
        hierarchy, notes, and resources from the user's own knowledge graph.
    """
    retriever = _get_retriever()
    result = retriever.retrieve(
        query=query,
        top_k=max(1, min(top_k, 20)),
        source_map=source_map or None,
    )
    if not result.concepts:
        return f'No concepts found for "{query}". Try broader keywords or a different source_map.'
    return result.as_text()


@mcp.tool()
def list_source_maps() -> str:
    """List the available source maps in the knowledge graph.

    Returns each map name with its domain, so you can pass the right
    source_map value to search_knowledge_graph when the user's question
    is clearly scoped to one topic area.
    """
    maps = [
        ("dlvr.mm",                               "Business / Ventures"),
        ("ajared.mm",                             "Ajared Research"),
        ("careerDevelopment.mm",                  "Career & Job Search"),
        ("new product Development Professional.mm", "Product Management"),
        ("data.mm",                               "Data Engineering"),
        ("life.mm",                               "Personal / Life"),
        ("Books.mm",                              "Library & Learning"),
        ("linkeddataSemanticWeb.mm",              "AI + Linked Data"),
        ("blog.mm",                               "Blog Content"),
        ("geospatial.mm",                         "Geospatial"),
    ]
    lines = ["Available source maps (pass the filename as source_map):\n"]
    for name, domain in maps:
        lines.append(f"  {name:<45} {domain}")
    lines.append(
        "\nNote: pitchstone.mm and neogov.mm are permanently excluded (proprietary)."
    )
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
