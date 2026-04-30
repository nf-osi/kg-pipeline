#!/usr/bin/env python3
"""Convert NF KG RDF (Turtle) files to an edgelist for node embedding with PecanPy.

Extracts all triples where both subject and object are IRIs, producing a
weighted edgelist where edge weight is the number of distinct predicates
connecting each (subject, object) pair. Literal-object triples are skipped
since literals are not embeddable graph nodes.

PecanPy (https://github.com/krishnanlab/PecanPy) expects:
    node1 node2 [weight]

Usage:
    python scripts/rdf_to_edgelist.py
    python scripts/rdf_to_edgelist.py --rdf-dir data/rdf --output data/embeddings/kg.edgelist
    python scripts/rdf_to_edgelist.py --exclude rdf:type --unweighted

Examples:
    # Generate weighted edgelist (default)
    python scripts/rdf_to_edgelist.py

    # Skip rdf:type edges (class membership) to focus on domain relations
    python scripts/rdf_to_edgelist.py --exclude http://www.w3.org/1999/02/22-rdf-syntax-ns#type
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

from pyoxigraph import NamedNode, RdfFormat, Store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_RDF_DIR = Path("data/rdf")
DEFAULT_OUTPUT = Path("data/embeddings/kg.edgelist")


def load_rdf(rdf_dir: Path) -> Store:
    store = Store()
    ttl_files = sorted(rdf_dir.glob("*.ttl"))
    if not ttl_files:
        logger.error("No .ttl files found in %s", rdf_dir)
        sys.exit(1)
    for ttl in ttl_files:
        logger.info("Loading %s", ttl.name)
        with open(ttl, "rb") as f:
            try:
                store.bulk_load(f, RdfFormat.TURTLE)
            except Exception as exc:
                logger.warning("Skipping %s — parse error: %s", ttl.name, exc)
    logger.info("Loaded %d total triples", len(store))
    return store


def extract_edges(
    store: Store, exclude: set[str]
) -> dict[tuple[str, str], int]:
    """Return {(src, dst): edge_weight} where weight = # distinct predicates."""
    edge_predicates: dict[tuple[str, str], set[str]] = defaultdict(set)
    skipped_excluded = 0
    skipped_literals = 0

    for quad in store.quads_for_pattern(None, None, None):
        subj = quad.subject
        obj = quad.object
        pred = quad.predicate

        if not isinstance(obj, NamedNode):
            skipped_literals += 1
            continue

        pred_str = pred.value
        if pred_str in exclude:
            skipped_excluded += 1
            continue

        edge_predicates[(subj.value, obj.value)].add(pred_str)

    logger.info(
        "Extracted %d unique (src, dst) pairs; skipped %d literals, %d excluded-predicate triples",
        len(edge_predicates),
        skipped_literals,
        skipped_excluded,
    )
    return {pair: len(preds) for pair, preds in edge_predicates.items()}


def write_edgelist(
    edges: dict[tuple[str, str], int], output: Path, weighted: bool
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for (src, dst), weight in edges.items():
            if weighted:
                f.write(f"{src}\t{dst}\t{weight}\n")
            else:
                f.write(f"{src}\t{dst}\n")
    logger.info("Wrote %d edges to %s", len(edges), output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--rdf-dir",
        type=Path,
        default=DEFAULT_RDF_DIR,
        help=f"Directory containing .ttl files (default: {DEFAULT_RDF_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output edgelist path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        metavar="IRI",
        help="Predicate IRIs to exclude (full IRI strings)",
    )
    parser.add_argument(
        "--unweighted",
        action="store_true",
        help="Omit edge weights (default: include weights)",
    )
    args = parser.parse_args(argv)

    if not args.rdf_dir.exists():
        logger.error("RDF directory not found: %s", args.rdf_dir)
        return 1

    store = load_rdf(args.rdf_dir)
    edges = extract_edges(store, exclude=set(args.exclude))
    write_edgelist(edges, args.output, weighted=not args.unweighted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
