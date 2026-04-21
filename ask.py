"""
ask.py
Week 8 — Claude API Integration

Wires the HybridRetriever into Claude for grounded Q&A over the personal
knowledge graph. Retrieval context is injected into the system prompt so
Claude answers from *your* knowledge, not general training data.

Usage (CLI):
    python ask.py "What do I know about business model design?"
    python ask.py "machine learning pipelines" --top-k 10
    python ask.py "career goals" --map careerDevelopment.mm
    python ask.py "linked data" --model claude-haiku-4-5-20251001

Environment:
    ANTHROPIC_API_KEY  — required

⚠️  pitchstone.mm and neogov.mm are permanently excluded.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
import time
from typing import Optional

import anthropic

from retrieve import HybridRetriever, RetrievalResult, DEFAULT_TOP_K

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_MODEL      = "claude-haiku-4-5-20251001"   # fast + cheap for test runs
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


# ─────────────────────────────────────────────────────────────────────────────
# Core ask function
# ─────────────────────────────────────────────────────────────────────────────

def ask(
    query: str,
    retriever: HybridRetriever,
    *,
    model:        str = DEFAULT_MODEL,
    top_k:        int = DEFAULT_TOP_K,
    source_map:   Optional[str] = None,
    max_tokens:   int = DEFAULT_MAX_TOKENS,
    verbose:      bool = True,
) -> dict:
    """
    Retrieve context then call Claude. Returns a dict with:
        query, context_text, answer, model, top_k, elapsed_sec, n_concepts
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set.\n"
            "Export it before running: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    # ── 1. Retrieve ───────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    result: RetrievalResult = retriever.retrieve(
        query=query, top_k=top_k, source_map=source_map
    )
    context_text = result.as_text()

    if verbose:
        print(f"  Retrieved {len(result.concepts)} concept(s) in "
              f"{time.perf_counter() - t0:.2f}s")

    # ── 2. Build user message ─────────────────────────────────────────────────
    user_message = f"{context_text}\n\nQUESTION: {query}"

    # ── 3. Call Claude ────────────────────────────────────────────────────────
    t1 = time.perf_counter()
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    answer = response.content[0].text
    elapsed = round(time.perf_counter() - t0, 2)

    if verbose:
        print(f"  Claude answered in {time.perf_counter() - t1:.2f}s "
              f"(total: {elapsed}s)\n")

    return {
        "query":        query,
        "context_text": context_text,
        "answer":       answer,
        "model":        model,
        "top_k":        top_k,
        "source_map":   source_map,
        "elapsed_sec":  elapsed,
        "n_concepts":   len(result.concepts),
        "input_tokens":  response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(
        description="GraphRAG Q&A — hybrid retrieval + Claude API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Examples:
              python ask.py "What do I know about business model design?"
              python ask.py "machine learning pipelines" --top-k 10
              python ask.py "career goals" --map careerDevelopment.mm
              python ask.py "linked data" --model claude-sonnet-4-6
        """),
    )
    p.add_argument("query",   help="Natural language question")
    p.add_argument("--top-k", type=int, default=DEFAULT_TOP_K,
                   help=f"Retrieval breadth (default: {DEFAULT_TOP_K})")
    p.add_argument("--map",   default=None,
                   help="Scope retrieval to one source map (e.g. data.mm)")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Claude model (default: {DEFAULT_MODEL})")
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    p.add_argument("--show-context", action="store_true",
                   help="Print the full retrieval context before the answer")
    return p.parse_args()


def main():
    args   = _parse_args()
    print("\n── Initialising retriever ──────────────────────────────────────")
    retriever = HybridRetriever(verbose=True)

    print(f"── Asking: {args.query!r} ──")
    try:
        result = ask(
            query      = args.query,
            retriever  = retriever,
            model      = args.model,
            top_k      = args.top_k,
            source_map = args.map,
            max_tokens = args.max_tokens,
            verbose    = True,
        )
    except EnvironmentError as e:
        print(f"\n❌  {e}", file=sys.stderr)
        sys.exit(1)

    if args.show_context:
        print("\n── Retrieved Context ───────────────────────────────────────────")
        print(result["context_text"])

    print("── Answer ──────────────────────────────────────────────────────")
    print(result["answer"])
    print(f"\n── Stats: {result['n_concepts']} concepts | "
          f"{result['input_tokens']} in / {result['output_tokens']} out tokens | "
          f"{result['elapsed_sec']}s total ──")


if __name__ == "__main__":
    main()
