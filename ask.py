"""CLI shim — delegates to qa.ask. Also re-exports for backward compatibility."""

from qa.ask import ask, DEFAULT_MODEL, main  # noqa: F401

if __name__ == "__main__":
    main()
