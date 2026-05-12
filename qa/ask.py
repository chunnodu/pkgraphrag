"""Claude API integration: retrieves context then answers via Claude."""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
import time
from typing import Optional

import anthropic

from retrieval import HybridRetriever, RetrievalResult, DEFAULT_TOP_K

DEFAULT_MODEL      = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TOKENS = 1024

SYSTEM_PROMPT = """You are a personal knowledge assistant with access to the user's \
personal knowledge graph — a structured RDF graph built from their Freeplane mind maps \
spanning topics like data engineering, career development, business strategy, linked data, \
geospatial, personal life goals, books, and more.

You will be given CONTEXT retrieved from that graph: concept labels, parent/child \
relationships, personal notes, and web resources the user has saved. Your job is to \
synthesise that context into a clear, direct answer.

Rules:
- Ground your answer in the retrieved context. If the context is thin or off-topic, \
say so honestly rather than hallucinating.
- Be concise. The user knows their own domain — skip basic definitions unless the \
context specifically warrants them.
- When the context includes personal notes, treat them as the user's own words and \
reference them directly.
- Never reference pitchstone.mm or neogov.mm — these maps are permanently excluded \
and should never appear in answers.
- If you cite a concept, mention which source map it came from (e.g. "from data.mm").
"""


def ask(
    query: str,
    retriever: HybridRetriever,
    *,
    model:      str          = DEFAULT_MODEL,
    top_k:      int          = DEFAULT_TOP_K,
    source_map: Optional[str] = None,
    max_tokens: int          = DEFAULT_MAX_TOKENS,
    verbose:    bool         = True,
    debug:      bool         = False,
) -> dict:
    """Retrieve context then call Claude. Returns a result dict."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set.\n"
            "Export it before running: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    t0 = time.perf_counter()
    result: RetrievalResult = retriever.retrieve(
        query=query, top_k=top_k, source_map=source_map, debug=debug
    )
    context_text = result.as_text()

    if verbose:
        print(f"  Retrieved {len(result.concepts)} concept(s) in {time.perf_counter() - t0:.2f}s")

    t1     = time.perf_counter()
    client = anthropic.Anthropic(api_key=api_key)
    resp   = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"{context_text}\n\nQUESTION: {query}"}],
    )
    answer  = resp.content[0].text
    elapsed = round(time.perf_counter() - t0, 2)

    if verbose:
        print(f"  Claude answered in {time.perf_counter() - t1:.2f}s (total: {elapsed}s)\n")

    return {
        "query":         query,
        "context_text":  context_text,
        "answer":        answer,
        "model":         model,
        "top_k":         top_k,
        "source_map":    source_map,
        "elapsed_sec":   elapsed,
        "n_concepts":    len(result.concepts),
        "input_tokens":  resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(
        description="GraphRAG Q&A — hybrid retrieval + Claude API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Examples:
              python ask.py "What do I know about business model design?"
              python ask.py "DLVR strategy" --debug --show-context
              python ask.py "career goals" --map careerDevelopment.mm
              python ask.py "linked data" --model claude-sonnet-4-6
        """),
    )
    p.add_argument("query")
    p.add_argument("--top-k",        type=int, default=DEFAULT_TOP_K)
    p.add_argument("--map",          default=None)
    p.add_argument("--model",        default=DEFAULT_MODEL)
    p.add_argument("--max-tokens",   type=int, default=DEFAULT_MAX_TOKENS)
    p.add_argument("--show-context", action="store_true")
    p.add_argument("--debug",        action="store_true")
    return p.parse_args()


def main():
    args      = _parse_args()
    retriever = HybridRetriever(verbose=True)
    try:
        result = ask(
            query      = args.query,
            retriever  = retriever,
            model      = args.model,
            top_k      = args.top_k,
            source_map = args.map,
            max_tokens = args.max_tokens,
            verbose    = True,
            debug      = args.debug,
        )
    except EnvironmentError as e:
        print(f"\n❌  {e}", file=sys.stderr)
        sys.exit(1)

    if args.show_context:
        print("\n── Retrieved Context ───────────────────────────────────────────")
        print(result["context_text"])

    print("── Answer ──────────────────────────────────────────────────────")
    print(result["answer"])
    print(
        f"\n── Stats: {result['n_concepts']} concepts | "
        f"{result['input_tokens']} in / {result['output_tokens']} out tokens | "
        f"{result['elapsed_sec']}s total ──"
    )


if __name__ == "__main__":
    main()
