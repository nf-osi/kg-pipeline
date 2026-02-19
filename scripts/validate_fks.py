#!/usr/bin/env python3
"""Validate foreign key constraints across portal CSV tables.

Reads processed CSVs and checks that every FK value exists in the
referenced table's primary key column.  Reports violations without
stopping the pipeline (exit 0) unless --strict is passed.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set

# Re-use the authoritative schema
from prepare_portal_tables import TABLES


@dataclass
class FKConstraint:
    """A single FK relationship to check."""

    source_table: str
    source_column: str
    target_table: str
    target_column: str


@dataclass
class FKResult:
    """Outcome of checking one FK constraint."""

    constraint: FKConstraint
    populated: int = 0
    orphaned: int = 0
    unique_orphans: int = 0
    sample_values: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.orphaned == 0

    @property
    def orphan_pct(self) -> float:
        if self.populated == 0:
            return 0.0
        return 100.0 * self.orphaned / self.populated


def discover_constraints() -> List[FKConstraint]:
    """Scan TABLES for columns with a ``references`` key."""
    constraints: List[FKConstraint] = []
    for table_name, table_def in TABLES.items():
        for col in table_def["columns"]:
            ref = col.get("references")
            if ref is None:
                continue
            constraints.append(
                FKConstraint(
                    source_table=table_name,
                    source_column=col["target"],
                    target_table=ref["table"],
                    target_column=ref["column"],
                )
            )
    return constraints


def _load_column(csv_path: Path, column: str) -> List[str]:
    """Read a single column from a CSV, returning non-empty values."""
    values: List[str] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            val = (row.get(column) or "").strip()
            if val:
                values.append(val)
    return values


def _load_pk_set(csv_path: Path, column: str) -> Set[str]:
    """Load the set of primary key values from a CSV."""
    return set(_load_column(csv_path, column))


def _csv_path_for(table_name: str, data_dir: Path) -> Path:
    """Resolve the CSV path for a table, respecting a custom data dir."""
    configured = TABLES[table_name]["csv_path"]
    return data_dir / Path(configured).name


def check_constraint(
    constraint: FKConstraint,
    data_dir: Path,
    pk_cache: Dict[str, Set[str]],
) -> FKResult:
    """Check a single FK constraint and return the result."""
    # Load target PK set (with caching)
    cache_key = f"{constraint.target_table}.{constraint.target_column}"
    if cache_key not in pk_cache:
        target_path = _csv_path_for(constraint.target_table, data_dir)
        if not target_path.exists():
            # Cannot validate — target CSV missing
            return FKResult(constraint=constraint)
        pk_cache[cache_key] = _load_pk_set(target_path, constraint.target_column)
    pk_set = pk_cache[cache_key]

    # Load source FK values
    source_path = _csv_path_for(constraint.source_table, data_dir)
    if not source_path.exists():
        return FKResult(constraint=constraint)

    fk_values = _load_column(source_path, constraint.source_column)

    orphans = [v for v in fk_values if v not in pk_set]
    unique_orphans = sorted(set(orphans))

    return FKResult(
        constraint=constraint,
        populated=len(fk_values),
        orphaned=len(orphans),
        unique_orphans=len(unique_orphans),
        sample_values=unique_orphans[:10],
    )


def validate_all(data_dir: Path) -> List[FKResult]:
    """Run all FK checks and return results."""
    constraints = discover_constraints()
    pk_cache: Dict[str, Set[str]] = {}
    return [check_constraint(c, data_dir, pk_cache) for c in constraints]


def print_human(results: List[FKResult]) -> None:
    """Print a human-readable validation report."""
    source_tables = {r.constraint.source_table for r in results}
    print(f"FK validation: {len(results)} constraints across {len(source_tables)} tables\n")

    failures = 0
    for r in results:
        label = f"{r.constraint.source_table}.{r.constraint.source_column}"
        target = f"{r.constraint.target_table}.{r.constraint.target_column}"
        if r.passed:
            print(f" ok   {label} -> {target}")
        else:
            failures += 1
            print(f"FAIL  {label} -> {target}")
            print(f"      {r.orphaned} / {r.populated} populated rows orphaned "
                  f"({r.orphan_pct:.1f}%), {r.unique_orphans} unique values")
            if r.sample_values:
                samples = ", ".join(r.sample_values[:5])
                print(f"      sample: {samples}")

    passed = len(results) - failures
    print(f"\nSummary: {failures} failures, {passed} passed")


def print_json(results: List[FKResult]) -> None:
    """Print machine-readable JSON report."""
    records = []
    for r in results:
        records.append({
            "source_table": r.constraint.source_table,
            "source_column": r.constraint.source_column,
            "target_table": r.constraint.target_table,
            "target_column": r.constraint.target_column,
            "populated": r.populated,
            "orphaned": r.orphaned,
            "orphan_pct": round(r.orphan_pct, 2),
            "unique_orphans": r.unique_orphans,
            "passed": r.passed,
            "sample_values": r.sample_values,
        })
    json.dump(records, sys.stdout, indent=2)
    print()


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/csv"),
        help="Directory containing processed CSVs (default: data/csv).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output machine-readable JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any FK violations are found.",
    )
    args = parser.parse_args(argv)

    results = validate_all(args.data_dir)

    if args.json_output:
        print_json(results)
    else:
        print_human(results)

    if args.strict and any(not r.passed for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
