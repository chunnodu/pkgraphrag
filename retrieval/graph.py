"""rdflib SPARQL graph expansion for concept URIs."""

from __future__ import annotations

import glob
import os

from rdflib import Graph
from rdflib.namespace import SKOS, OWL

from .models import (
    OUTPUTS_DIR, PKG, PKGC, SCHEMA, DC,
    EXCLUDED_MAPS,
    DEFAULT_MAX_CHILDREN, DEFAULT_MAX_NOTES, DEFAULT_MAX_RESOURCES,
)


class GraphRetriever:
    """Loads all TTL files once and expands concept URIs into structured context via SPARQL."""

    _Q_PARENT = """
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?parentLabel WHERE {
        ?parent pkg:hasSubTopic <%s> ;
                skos:prefLabel  ?parentLabel .
    } LIMIT 1
    """

    _Q_CHILDREN = """
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?childLabel WHERE {
        <%s> pkg:hasSubTopic ?child .
        ?child skos:prefLabel ?childLabel .
    } LIMIT %d
    """

    _Q_SIBLINGS = """
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?sibLabel WHERE {
        ?parent pkg:hasSubTopic <%s> ;
                pkg:hasSubTopic ?sib .
        ?sib skos:prefLabel ?sibLabel .
        FILTER (?sib != <%s>)
    } LIMIT 5
    """

    _Q_NOTES = """
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    SELECT ?text WHERE {
        <%s> pkg:hasNote ?note .
        ?note pkg:noteText ?text .
    } LIMIT %d
    """

    _Q_RESOURCES = """
    PREFIX pkg:  <https://pkg.chunnodu.com/ontology#>
    SELECT ?url WHERE {
        <%s> pkg:hasResource ?res .
        ?res pkg:url ?url .
    } LIMIT %d
    """

    _Q_LOD = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    SELECT ?external WHERE {
        <%s> owl:sameAs ?external .
    }
    """

    def __init__(self, outputs_dir: str = OUTPUTS_DIR):
        self._g = self._load_graph(outputs_dir)

    def _load_graph(self, outputs_dir: str) -> Graph:
        g = Graph()
        g.bind("pkg",    PKG)
        g.bind("pkgc",   PKGC)
        g.bind("skos",   SKOS)
        g.bind("owl",    OWL)
        g.bind("schema", SCHEMA)
        g.bind("dc",     DC)

        ttl_files = sorted(glob.glob(os.path.join(outputs_dir, "*.ttl")))
        print(f"  Loading {len(ttl_files)} TTL files into graph...", end=" ", flush=True)
        for path in ttl_files:
            if any(ex in os.path.basename(path) for ex in EXCLUDED_MAPS):
                continue
            sub = Graph()
            sub.parse(path, format="turtle")
            g += sub
        print(f"{len(g):,} triples loaded.")
        return g

    def _sparql(self, query: str) -> list:
        return list(self._g.query(query))

    def expand(
        self,
        uri: str,
        max_children:  int = DEFAULT_MAX_CHILDREN,
        max_notes:     int = DEFAULT_MAX_NOTES,
        max_resources: int = DEFAULT_MAX_RESOURCES,
    ) -> dict:
        parent   = next((str(r[0]) for r in self._sparql(self._Q_PARENT % uri)), None)
        children = [str(r[0]) for r in self._sparql(self._Q_CHILDREN % (uri, max_children))]
        siblings = [str(r[0]) for r in self._sparql(self._Q_SIBLINGS % (uri, uri))]
        notes    = [str(r[0]).strip() for r in self._sparql(self._Q_NOTES % (uri, max_notes))]
        resources = [str(r[0]) for r in self._sparql(self._Q_RESOURCES % (uri, max_resources))]
        lod_links = [str(r[0]) for r in self._sparql(self._Q_LOD % uri)]
        return {
            "parent": parent, "children": children, "siblings": siblings,
            "notes": notes, "resources": resources, "lod_links": lod_links,
        }
