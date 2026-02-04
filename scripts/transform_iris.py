#!/usr/bin/env python3
"""Transform nf:dataType literals to IRIs using SKOS lookup.

This script:
1. Loads the RML output RDF
2. Builds a lookup dictionary from SKOS vocabulary
3. Reports any unmatched dataType literals (data quality check)
4. Transforms matched literals to IRIs via direct triple manipulation
5. Writes the transformed RDF

Usage:
    python scripts/transform_iris.py [--input FILE] [--output FILE] [--check-only]

Examples:
    # Transform with defaults
    python scripts/transform_iris.py

    # Check for unmatched literals only (no transformation)
    python scripts/transform_iris.py --check-only

    # Custom input/output
    python scripts/transform_iris.py --input data/rdf/studies.ttl --output data/rdf/studies_transformed.ttl
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pyoxigraph import Store, serialize, NamedNode, Literal as OxiLiteral, Quad, DefaultGraph
from pyoxigraph import RdfFormat


LOOKUP_FILE = Path("mappings/data_lookup.ttl")
DEFAULT_INPUT = Path("data/rdf/portal_studies.ttl")
DEFAULT_OUTPUT = Path("data/rdf/portal_studies.ttl")

NF_DATATYPE = NamedNode("http://nf-osi.github.com/terms#dataType")
SKOS_EXACT_MATCH = NamedNode("http://www.w3.org/2004/02/skos/core#exactMatch")
SKOS_PREF_LABEL = NamedNode("http://www.w3.org/2004/02/skos/core#prefLabel")
SKOS_ALT_LABEL = NamedNode("http://www.w3.org/2004/02/skos/core#altLabel")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class TransformStats:
    """Statistics from a transformation run."""

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    input_file: str = ""
    output_file: str = ""
    lookup_file: str = ""
    check_only: bool = False

    # Counts
    lookup_entries: int = 0
    input_triples: int = 0
    output_triples: int = 0
    datatype_literals_found: int = 0
    transformed_count: int = 0
    unmatched_unique: int = 0
    unmatched_total: int = 0

    # Timing (seconds)
    time_load_lookup: float = 0.0
    time_load_data: float = 0.0
    time_check: float = 0.0
    time_transform: float = 0.0
    time_write: float = 0.0
    time_total: float = 0.0

    # Details
    unmatched: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        """Serialize stats to JSON."""
        return json.dumps(asdict(self), indent=indent)


class Timer:
    """Context manager for timing code blocks."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self.elapsed = time.perf_counter() - self._start


def build_lookup_dict(lookup_file: Path, stats: TransformStats) -> dict[str, NamedNode]:
    """Build a case-insensitive lookup dict from SKOS vocabulary.

    Maps lowercase label strings to target IRIs.
    """
    with Timer() as t:
        logger.info("Loading lookup from %s", lookup_file)
        store = Store()

        # Load lookup file
        with open(lookup_file, 'rb') as f:
            store.bulk_load(f, RdfFormat.TURTLE)

        lookup = {}
        # Find all concepts with skos:exactMatch
        for quad in store.quads_for_pattern(None, SKOS_EXACT_MATCH, None):
            concept = quad.subject
            target_iri = quad.object

            if not isinstance(target_iri, NamedNode):
                continue

            # Add prefLabel
            for label_quad in store.quads_for_pattern(concept, SKOS_PREF_LABEL, None):
                if isinstance(label_quad.object, OxiLiteral):
                    lookup[str(label_quad.object.value).lower()] = target_iri

            # Add altLabels
            for label_quad in store.quads_for_pattern(concept, SKOS_ALT_LABEL, None):
                if isinstance(label_quad.object, OxiLiteral):
                    lookup[str(label_quad.object.value).lower()] = target_iri

    stats.time_load_lookup = t.elapsed
    stats.lookup_entries = len(lookup)
    logger.info("Built lookup with %d entries in %.2fs", len(lookup), t.elapsed)
    return lookup


def check_and_transform_datatypes(
    store: Store, lookup: dict[str, NamedNode], stats: TransformStats, transform: bool = True
) -> list[tuple[str, int]]:
    """Check for unmatched dataType literals and optionally transform them.

    Combined check + transform operation for better performance.
    Single pass through the triples instead of two separate iterations.

    Args:
        store: Oxigraph store to process
        lookup: Dictionary mapping lowercase literals to target IRIs
        stats: Statistics tracker
        transform: If True, transform matched literals; if False, only check

    Returns:
        List of (literal, count) tuples for unmatched values
    """
    with Timer() as t:
        unmatched_counts: Counter[str] = Counter()
        to_remove = []
        to_add = []
        total_literals = 0
        transformed = 0

        # Single pass: check and collect transformations
        for quad in store.quads_for_pattern(None, NF_DATATYPE, None):
            obj = quad.object
            if isinstance(obj, OxiLiteral):
                total_literals += 1
                key = str(obj.value).lower()
                target_iri = lookup.get(key)

                if target_iri and transform:
                    # Matched - prepare transformation
                    to_remove.append(quad)
                    to_add.append(Quad(quad.subject, quad.predicate, target_iri, quad.graph_name))
                    transformed += 1
                elif not target_iri:
                    # Unmatched - track for reporting
                    unmatched_counts[str(obj.value)] += 1

        # Apply transformations in bulk
        if transform and to_remove:
            for quad in to_remove:
                store.remove(quad)
            for quad in to_add:
                store.add(quad)

        # Sort unmatched by count descending
        unmatched = sorted(unmatched_counts.items(), key=lambda x: -x[1])

    elapsed = t.elapsed

    # Update stats
    stats.datatype_literals_found = total_literals
    stats.unmatched_unique = len(unmatched)
    stats.unmatched_total = sum(count for _, count in unmatched)
    stats.unmatched = [{"value": lit, "count": cnt} for lit, cnt in unmatched]

    if transform:
        stats.time_check = elapsed
        stats.time_transform = elapsed
        stats.transformed_count = transformed
        logger.info(
            "Processed %d dataType literals in %.2fs: %d transformed, %d unmatched (%d unique)",
            total_literals, elapsed, transformed, stats.unmatched_total, len(unmatched)
        )
    else:
        stats.time_check = elapsed
        logger.info(
            "Checked %d dataType literals in %.2fs: %d unmatched (%d unique values)",
            total_literals, elapsed, stats.unmatched_total, len(unmatched)
        )

    return unmatched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input RDF file (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output RDF file (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--lookup",
        type=Path,
        default=LOOKUP_FILE,
        help=f"SKOS lookup file (default: {LOOKUP_FILE})",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check for unmatched literals, don't transform",
    )
    parser.add_argument(
        "--stats-file",
        type=Path,
        help="Write JSON stats to this file",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console output (still writes to stats file)",
    )
    args = parser.parse_args(argv)

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    total_timer = Timer()
    total_timer.__enter__()

    # Initialize stats
    stats = TransformStats(
        input_file=str(args.input),
        output_file=str(args.output),
        lookup_file=str(args.lookup),
        check_only=args.check_only,
    )

    if not args.input.exists():
        logger.error("Input file not found: %s", args.input)
        return 1

    if not args.lookup.exists():
        logger.error("Lookup file not found: %s", args.lookup)
        return 1

    # Build lookup dictionary
    lookup = build_lookup_dict(args.lookup, stats)

    # Load data graph
    with Timer() as t:
        logger.info("Loading data from %s", args.input)
        store = Store()
        with open(args.input, 'rb') as f:
            store.bulk_load(f, RdfFormat.TURTLE)
        stats.input_triples = len(store)
    stats.time_load_data = t.elapsed
    logger.info("Loaded %d triples in %.2fs", len(store), t.elapsed)

    # Check and optionally transform in single pass
    unmatched = check_and_transform_datatypes(store, lookup, stats, transform=not args.check_only)

    if unmatched:
        logger.warning("Found %d unmatched dataType values:", len(unmatched))
        for literal, count in unmatched:
            logger.warning('  - "%s" (%d occurrences)', literal, count)
        logger.info("Consider adding these to mappings/data_lookup.ttl")

    if args.check_only:
        total_timer.__exit__(None, None, None)
        stats.time_total = total_timer.elapsed
        _write_stats(stats, args.stats_file)
        return 1 if unmatched else 0

    # Save
    with Timer() as t:
        logger.info("Writing output to %s", args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Get all triples from default graph and serialize to Turtle with prefixes
        triples = (quad.triple for quad in store.quads_for_pattern(None, None, None, DefaultGraph()))
        prefixes = {
            "nf": "http://nf-osi.github.com/terms#",
            "syn": "https://www.synapse.org/Synapse:",
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "edam": "http://edamontology.org/",
        }
        serialize(triples, output=str(args.output), format=RdfFormat.TURTLE, prefixes=prefixes)
        stats.output_triples = len(store)
    stats.time_write = t.elapsed
    logger.info("Wrote %d triples in %.2fs", len(store), t.elapsed)

    total_timer.__exit__(None, None, None)
    stats.time_total = total_timer.elapsed
    logger.info("Total time: %.2fs", stats.time_total)

    _write_stats(stats, args.stats_file)
    return 0


def _write_stats(stats: TransformStats, stats_file: Path | None) -> None:
    """Write stats to file and/or stdout."""
    if stats_file:
        stats_file.parent.mkdir(parents=True, exist_ok=True)
        stats_file.write_text(stats.to_json())
        logger.info("Stats written to %s", stats_file)


if __name__ == "__main__":
    raise SystemExit(main())
