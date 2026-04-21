"""
test_qa.py
Week 8 — 20 Q&A Test Pairs

Runs 20 questions across all 10 source maps through the full GraphRAG pipeline
(HybridRetriever → Claude API) and writes:
  - outputs/week8_qa_results.json   (full structured results)
  - outputs/week8_qa_report.md      (human-readable pass/review report)

Usage:
    python test_qa.py
    python test_qa.py --model claude-sonnet-4-6
    python test_qa.py --dry-run       # retrieval only, no Claude calls

⚠️  Requires ANTHROPIC_API_KEY to be set (unless --dry-run).
⚠️  pitchstone.mm and neogov.mm are permanently excluded.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from retrieve import HybridRetriever, DEFAULT_TOP_K
from ask import ask, DEFAULT_MODEL

# ── Output paths ──────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
OUTPUTS_DIR = BASE_DIR / "outputs"
JSON_OUT    = OUTPUTS_DIR / "week8_qa_results.json"
MD_OUT      = OUTPUTS_DIR / "week8_qa_report.md"

# ─────────────────────────────────────────────────────────────────────────────
# 20 Test Questions — one grounded question per source map,
# plus cross-domain and meta questions
# ─────────────────────────────────────────────────────────────────────────────
# Format: (question, expected_source_map_hint, category)
# expected_source_map_hint is a soft label for reporting only — not used in
# retrieval, which is always open across all 10 maps unless --map is passed.

TEST_QUESTIONS = [
    # ── ajared.mm (Ajared Research / business) ────────────────────────────────
    (
        "What do I know about Ajared's core services and offerings?",
        "ajared.mm",
        "business",
    ),
    (
        "What are the key components of a go-to-market strategy in my notes?",
        "ajared.mm",
        "business",
    ),

    # ── dlvr.mm (DLVR / business operations) ─────────────────────────────────
    (
        "What do I know about DLVR and how the business operates?",
        "dlvr.mm",
        "business",
    ),
    (
        "What content distribution or social media automation concepts have I mapped?",
        "dlvr.mm",
        "business",
    ),

    # ── careerDevelopment.mm ──────────────────────────────────────────────────
    (
        "What strategies have I noted for job searching and career advancement?",
        "careerDevelopment.mm",
        "career",
    ),
    (
        "What interview preparation techniques have I captured?",
        "careerDevelopment.mm",
        "career",
    ),

    # ── new product Development Professional.mm ───────────────────────────────
    (
        "What frameworks do I have for new product development and stage-gate processes?",
        "new product Development Professional.mm",
        "product",
    ),
    (
        "What do I know about product launch planning and go-to-market execution?",
        "new product Development Professional.mm",
        "product",
    ),

    # ── data.mm ───────────────────────────────────────────────────────────────
    (
        "What data engineering concepts and pipeline architectures have I mapped?",
        "data.mm",
        "data",
    ),
    (
        "What do I know about machine learning model evaluation and deployment?",
        "data.mm",
        "data",
    ),

    # ── linkeddataSemanticWeb.mm ──────────────────────────────────────────────
    (
        "What do I know about RDF, SPARQL, and the semantic web stack?",
        "linkeddataSemanticWeb.mm",
        "semantics",
    ),
    (
        "What knowledge graph tools and ontology design patterns have I captured?",
        "linkeddataSemanticWeb.mm",
        "semantics",
    ),

    # ── Books.mm ──────────────────────────────────────────────────────────────
    (
        "What books have I mapped on business strategy or innovation?",
        "Books.mm",
        "learning",
    ),
    (
        "What key ideas from books on personal productivity or habits have I noted?",
        "Books.mm",
        "learning",
    ),

    # ── life.mm ───────────────────────────────────────────────────────────────
    (
        "What are my major personal life goals and priorities?",
        "life.mm",
        "personal",
    ),
    (
        "What financial concepts or personal finance strategies have I mapped?",
        "life.mm",
        "personal",
    ),

    # ── blog.mm ───────────────────────────────────────────────────────────────
    (
        "What blog post ideas or content themes have I captured in my notes?",
        "blog.mm",
        "content",
    ),

    # ── geospatial.mm ─────────────────────────────────────────────────────────
    (
        "What geospatial tools, techniques, or GIS concepts have I mapped?",
        "geospatial.mm",
        "geospatial",
    ),

    # ── Cross-domain ──────────────────────────────────────────────────────────
    (
        "Where do data engineering and business strategy intersect in my knowledge?",
        "cross-domain",
        "synthesis",
    ),
    (
        "What do I know about AI applications in my areas of work or interest?",
        "cross-domain",
        "synthesis",
    ),
]

assert len(TEST_QUESTIONS) == 20, f"Expected 20 questions, got {len(TEST_QUESTIONS)}"


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_tests(
    model:   str  = DEFAULT_MODEL,
    top_k:   int  = DEFAULT_TOP_K,
    dry_run: bool = False,
) -> list[dict]:
    """Run all 20 questions, return list of result dicts."""
    print("\n── Initialising HybridRetriever ────────────────────────────────")
    retriever = HybridRetriever(verbose=True)
    print(f"── Running {len(TEST_QUESTIONS)} test questions "
          f"({'DRY RUN — retrieval only' if dry_run else f'model: {model}'}) ──\n")

    results = []
    for i, (question, expected_map, category) in enumerate(TEST_QUESTIONS, 1):
        print(f"[{i:02d}/{len(TEST_QUESTIONS)}] {question[:80]}...")

        if dry_run:
            from retrieve import RetrievalResult
            result_obj = retriever.retrieve(query=question, top_k=top_k)
            rec = {
                "index":        i,
                "question":     question,
                "expected_map": expected_map,
                "category":     category,
                "answer":       "[DRY RUN — no Claude call]",
                "n_concepts":   len(result_obj.concepts),
                "context_text": result_obj.as_text(),
                "elapsed_sec":  None,
                "input_tokens":  None,
                "output_tokens": None,
                "model":        None,
            }
        else:
            try:
                r = ask(
                    query     = question,
                    retriever = retriever,
                    model     = model,
                    top_k     = top_k,
                    verbose   = True,
                )
                rec = {
                    "index":        i,
                    "question":     question,
                    "expected_map": expected_map,
                    "category":     category,
                    **r,
                }
            except Exception as e:
                print(f"  ❌ Error: {e}")
                rec = {
                    "index":        i,
                    "question":     question,
                    "expected_map": expected_map,
                    "category":     category,
                    "answer":       f"ERROR: {e}",
                    "n_concepts":   0,
                    "elapsed_sec":  None,
                    "input_tokens":  None,
                    "output_tokens": None,
                    "model":        model,
                    "error":        str(e),
                }

        results.append(rec)

        # Brief pause between API calls to avoid rate limits
        if not dry_run and i < len(TEST_QUESTIONS):
            time.sleep(0.5)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Output writers
# ─────────────────────────────────────────────────────────────────────────────

def write_json(results: list[dict], path: Path) -> None:
    path.parent.mkdir(exist_ok=True)
    with open(path, "w") as f:
        json.dump(
            {
                "run_date": datetime.now().isoformat(),
                "n_questions": len(results),
                "results": results,
            },
            f,
            indent=2,
        )
    print(f"\n  ✅ JSON results → {path}")


def write_markdown(results: list[dict], path: Path) -> None:
    errors   = [r for r in results if "error" in r]
    dry_run  = results[0].get("model") is None if results else False
    answered = [r for r in results if "error" not in r and not dry_run]

    total_in  = sum(r.get("input_tokens")  or 0 for r in results)
    total_out = sum(r.get("output_tokens") or 0 for r in results)
    avg_time  = (
        sum(r["elapsed_sec"] for r in answered if r.get("elapsed_sec")) / len(answered)
        if answered else 0
    )

    lines = [
        "# Week 8 Q&A Test Report",
        f"\n**Run date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Model:** {results[0].get('model', 'N/A') if results else 'N/A'}  ",
        f"**Questions:** {len(results)}  ",
        f"**Errors:** {len(errors)}  ",
    ]

    if not dry_run and answered:
        lines += [
            f"**Avg response time:** {avg_time:.1f}s  ",
            f"**Total tokens:** {total_in:,} in / {total_out:,} out  ",
        ]

    lines.append("\n---\n")

    # Group by category
    categories: dict[str, list[dict]] = {}
    for r in results:
        categories.setdefault(r["category"], []).append(r)

    for cat, cat_results in categories.items():
        lines.append(f"\n## {cat.title()}\n")
        for r in cat_results:
            status = "❌" if "error" in r else "✅"
            lines.append(f"### {status} Q{r['index']:02d}: {r['question']}")
            lines.append(f"*Expected map: `{r['expected_map']}` | "
                         f"Concepts retrieved: {r['n_concepts']}*\n")
            lines.append("**Answer:**\n")
            lines.append(r["answer"])
            if r.get("elapsed_sec"):
                lines.append(
                    f"\n*{r['elapsed_sec']}s | "
                    f"{r.get('input_tokens',0):,} in / "
                    f"{r.get('output_tokens',0):,} out tokens*"
                )
            lines.append("\n---")

    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines))
    print(f"  ✅ Markdown report → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(description="Week 8 — 20 Q&A test runner")
    p.add_argument("--model",   default=DEFAULT_MODEL,
                   help=f"Claude model (default: {DEFAULT_MODEL})")
    p.add_argument("--top-k",  type=int, default=DEFAULT_TOP_K)
    p.add_argument("--dry-run", action="store_true",
                   help="Run retrieval only — skip Claude API calls")
    return p.parse_args()


def main():
    args    = _parse_args()
    results = run_tests(model=args.model, top_k=args.top_k, dry_run=args.dry_run)

    write_json(results, JSON_OUT)
    write_markdown(results, MD_OUT)

    errors = [r for r in results if "error" in r]
    print(f"\n{'='*60}")
    print(f"  Done — {len(results) - len(errors)}/{len(results)} passed")
    if errors:
        print(f"  ⚠️  {len(errors)} error(s):")
        for r in errors:
            print(f"    Q{r['index']:02d}: {r['error']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
