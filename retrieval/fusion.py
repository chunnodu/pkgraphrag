"""Reciprocal Rank Fusion over two ranked URI lists."""

from __future__ import annotations

from .models import DEFAULT_TOP_K, RRF_K


def rrf_fuse(
    list_a: list[dict],
    list_b: list[dict],
    k:      int = RRF_K,
    top_n:  int = DEFAULT_TOP_K,
) -> list[dict]:
    """
    Merge two ranked lists using RRF: score(d) = Σ 1 / (k + rank(d)).

    Returns top_n dicts sorted by rrf_score descending, each with:
        uri, label, source_map, rrf_score, in_vector, in_keyword
    """
    scores: dict[str, float] = {}
    meta:   dict[str, dict]  = {}

    for rank, hit in enumerate(list_a, start=1):
        uri = hit["uri"]
        scores[uri] = scores.get(uri, 0.0) + 1.0 / (k + rank)
        if uri not in meta:
            meta[uri] = {
                "label":      hit.get("label", ""),
                "source_map": hit.get("source_map", ""),
                "in_vector":  True,
                "in_keyword": False,
            }
        else:
            meta[uri]["in_vector"] = True

    for rank, hit in enumerate(list_b, start=1):
        uri = hit["uri"]
        scores[uri] = scores.get(uri, 0.0) + 1.0 / (k + rank)
        if uri not in meta:
            meta[uri] = {
                "label":      hit.get("label", ""),
                "source_map": hit.get("source_map", ""),
                "in_vector":  False,
                "in_keyword": True,
            }
        else:
            meta[uri]["in_keyword"] = True

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [
        {
            "uri":        uri,
            "label":      meta[uri]["label"],
            "source_map": meta[uri]["source_map"],
            "rrf_score":  round(score, 6),
            "in_vector":  meta[uri]["in_vector"],
            "in_keyword": meta[uri]["in_keyword"],
        }
        for uri, score in fused
    ]
