"""CLI shim — delegates to retrieval.hybrid. Also re-exports for backward compatibility."""

from retrieval import HybridRetriever, DEFAULT_TOP_K, ConceptContext, RetrievalResult  # noqa: F401
from retrieval.hybrid import main

if __name__ == "__main__":
    main()
