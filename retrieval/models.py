"""Shared constants, namespaces, and data structures for the retrieval package."""

from __future__ import annotations

import json
import os
import textwrap
from dataclasses import asdict, dataclass, field
from typing import Optional

from rdflib import Namespace

# ── Paths (resolved relative to project root) ─────────────────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
BASE_DIR     = os.path.dirname(_HERE)
OUTPUTS_DIR  = os.path.join(BASE_DIR, "outputs")
DB_PATH      = os.path.join(BASE_DIR, "pkg_lancedb")

# ── RDF Namespaces ────────────────────────────────────────────────────────────
PKG    = Namespace("https://pkg.chunnodu.com/ontology#")
PKGC   = Namespace("https://pkg.chunnodu.com/concept/")
SCHEMA = Namespace("https://schema.org/")
DC     = Namespace("http://purl.org/dc/elements/1.1/")

# ── Excluded maps (employer-proprietary — never queried) ──────────────────────
EXCLUDED_MAPS = {"pitchstone.mm", "neogov.mm"}

# ── Retrieval defaults ────────────────────────────────────────────────────────
DEFAULT_TOP_K         = 8    # final fused hits passed to graph expansion
DEFAULT_FETCH_K       = 20   # per-path fetch size before fusion
RRF_K                 = 60   # RRF smoothing constant
DEFAULT_MAX_CHILDREN  = 5
DEFAULT_MAX_NOTES     = 2
DEFAULT_MAX_RESOURCES = 3


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ConceptContext:
    uri:        str
    label:      str
    source_map: str
    score:      float
    parent:     Optional[str] = None
    children:   list[str]     = field(default_factory=list)
    siblings:   list[str]     = field(default_factory=list)
    notes:      list[str]     = field(default_factory=list)
    resources:  list[str]     = field(default_factory=list)
    lod_links:  list[str]     = field(default_factory=list)
    in_vector:  bool          = True
    in_keyword: bool          = False


@dataclass
class RetrievalResult:
    query:    str
    concepts: list[ConceptContext]

    def as_text(self) -> str:
        lines = [
            f'CONTEXT FOR QUERY: "{self.query}"',
            "=" * 70,
            f"Retrieved {len(self.concepts)} relevant concept(s) from your personal knowledge graph.\n",
        ]
        for i, c in enumerate(self.concepts, 1):
            src_tag = (
                "vector+keyword" if (c.in_vector and c.in_keyword)
                else ("keyword" if c.in_keyword else "vector")
            )
            lines.append(
                f"[{i}] {c.label}  "
                f"(map: {c.source_map}, rrf: {c.score:.4f}, src: {src_tag})"
            )
            if c.parent:
                lines.append(f"    Parent   : {c.parent}")
            if c.children:
                lines.append(f"    Children : {', '.join(c.children)}")
            if c.siblings:
                lines.append(f"    Siblings : {', '.join(c.siblings)}")
            for note in c.notes:
                lines.append(f"    Note     : {textwrap.shorten(note, 200)}")
            for url in c.resources:
                lines.append(f"    Resource : {url}")
            if c.lod_links:
                lines.append(f"    LOD      : {', '.join(c.lod_links)}")
            lines.append("")
        return "\n".join(lines)

    def as_json(self) -> str:
        return json.dumps(
            {"query": self.query, "concepts": [asdict(c) for c in self.concepts]},
            indent=2,
        )
