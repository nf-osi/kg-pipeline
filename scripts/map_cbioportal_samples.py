"""Build the cBioPortal sample -> portal specimen/individual crosswalk.

Part of the variant layer PoC (nf-osi/kg-pipeline#95). See `docs/variant-layer.md`.

cBioPortal `Tumor_Sample_Barcode` values may or may not match portal `specimenID`s, and
which is true is a per-study fact, not a rule to hardcode. `BARCODE_RULES` is tried in
order and the row records which one hit:

| Study | Rule that matches | Coverage |
|---|---|---|
| `schw_ctf_synodos_2025` | `verbatim` | 40 / 40 |
| `nst_nfosi_ntap` | `strip_last_segment` | 71 / 80 |

For `nst_nfosi_ntap` the barcode carries one extra trailing segment:

    Tumor_Sample_Barcode  JH-2-001-8A1B1-A
    portal specimenID     JH-2-001-8A1B1
    portal individualID   JH-2-001

Verbatim, 0 of 80 barcodes match a specimenID. Dropping the last `-`-delimited segment
matches 71 of 80. Dropping a literal trailing `-A` matches only 68, because three
barcodes end in something else (`...-GAF53-A1011`, `...-GAF53-FB9H7`, `...-1419H-9GG15`)
-- which is why the rule is "last segment", not "the letter A".

Rather than bury that regex inside the RDF step, this script writes the resolved
crosswalk to a reviewable TSV that the RDF step then reads verbatim. Consequences:

* the mapping is diffable, and a reviewer can see every barcode that did not resolve;
* the 9 unresolved barcodes can be fixed by hand (set `method` to `manual`) without
  touching code, and reruns preserve those edits;
* one file holds every study: a run rebuilds only the study it is given and carries the
  other studies' rows across unchanged, so adding a study cannot delete another's;
* a study whose ids cannot be derived at all -- `nfib_ctf_biobank_2025`, whose
  `Patient10_Tumor1` ids were renamed at submission and have no deterministic route back
  to portal specimens like `HM5230` -- can be added as a wholly manual file.

The individual is taken from the *specimen's* own `nf:fromIndividual` link rather than
re-derived from the barcode, so the crosswalk cannot disagree with the specimen layer.
Only when a barcode resolves to no specimen does it fall back to a barcode-prefix guess,
and that fallback is recorded in `method` so it is never mistaken for portal truth.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from materialize_specimens import index_files  # noqa: E402

CROSSWALK_COLUMNS = [
    "study_id",
    "tumor_sample_barcode",
    "specimen_id",
    "individual_id",
    "method",
    "notes",
]

#: Methods this script derives. Anything else in an existing file (notably `manual`) is
#: treated as human-authored and preserved verbatim on rerun.
DERIVED_METHODS = frozenset(
    {"verbatim", "strip_last_segment", "prefix_guess", "unmatched"}
)


def strip_last_segment(barcode: str) -> str:
    """`JH-2-001-8A1B1-A` -> `JH-2-001-8A1B1`."""
    return barcode.rsplit("-", 1)[0] if "-" in barcode else barcode


#: Barcode -> specimenID rules, tried in order; the first candidate that is a portal
#: specimenID wins and names itself in the row's `method`.
#:
#: `verbatim` is first because it is the only rule that cannot be wrong -- if the
#: barcode already IS a specimenID there is nothing to derive. It matches 0 of 80 in
#: `nst_nfosi_ntap` and 40 of 40 in `schw_ctf_synodos_2025`, so the two studies need no
#: per-study branching: each simply falls to the rule that fits it.
BARCODE_RULES: tuple[tuple[str, "Callable[[str], str]"], ...] = (
    ("verbatim", lambda barcode: barcode),
    ("strip_last_segment", strip_last_segment),
)


def individual_prefix_guess(barcode: str, segments: int = 3) -> str:
    """`JH-2-001-8A1B1-A` -> `JH-2-001`. Only used when no specimen resolved."""
    parts = barcode.split("-")
    return "-".join(parts[:segments]) if len(parts) > segments else barcode


def read_maf_barcodes(maf: Path) -> list[str]:
    """Distinct `Tumor_Sample_Barcode` values, in first-seen order."""
    with open(maf, newline="") as handle:
        rows = (line for line in handle if not line.startswith("#"))
        reader = csv.DictReader(rows, delimiter="\t")
        if "Tumor_Sample_Barcode" not in (reader.fieldnames or []):
            raise SystemExit(f"{maf}: no Tumor_Sample_Barcode column")
        seen: dict[str, None] = {}
        for row in reader:
            barcode = (row.get("Tumor_Sample_Barcode") or "").strip()
            if barcode:
                seen.setdefault(barcode, None)
    return list(seen)


def load_existing(path: Path) -> dict[tuple[str, str], dict]:
    """Load a crosswalk, keyed by (study_id, barcode)."""
    if not path.exists():
        return {}
    with open(path, newline="") as handle:
        rows = [line for line in handle if not line.startswith("#")]
    reader = csv.DictReader(rows, delimiter="\t")
    return {(r["study_id"], r["tumor_sample_barcode"]): r for r in reader}


def build_rows(
    study_id: str,
    barcodes: list[str],
    specimens: set[str],
    specimen_individuals: dict[str, set[str]],
    existing: dict[tuple[str, str], dict],
) -> list[dict]:
    rows = []
    for barcode in barcodes:
        kept = existing.get((study_id, barcode))
        if kept and kept.get("method") not in DERIVED_METHODS:
            # Human-authored row: never overwrite.
            rows.append({c: kept.get(c, "") for c in CROSSWALK_COLUMNS})
            continue

        tried = []
        for method, rule in BARCODE_RULES:
            candidate = rule(barcode)
            tried.append(candidate)
            if candidate not in specimens:
                continue
            individuals = sorted(specimen_individuals.get(candidate, set()))
            rows.append(
                {
                    "study_id": study_id,
                    "tumor_sample_barcode": barcode,
                    "specimen_id": candidate,
                    # A specimen linked to several individuals is a source-data problem;
                    # leave it blank rather than pick one arbitrarily.
                    "individual_id": individuals[0] if len(individuals) == 1 else "",
                    "method": method,
                    "notes": ""
                    if len(individuals) <= 1
                    else f"specimen links to {len(individuals)} individuals: {','.join(individuals)}",
                }
            )
            break
        else:
            attempted = ", ".join(f"'{c}'" for c in dict.fromkeys(tried))
            rows.append(
                {
                    "study_id": study_id,
                    "tumor_sample_barcode": barcode,
                    "specimen_id": "",
                    "individual_id": "",
                    "method": "unmatched",
                    "notes": f"no portal specimenID among {attempted}; "
                             "set method=manual to fix by hand",
                }
            )
    return rows


def write_crosswalk(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as handle:
        handle.write(
            "# cBioPortal Tumor_Sample_Barcode -> portal specimenID / individualID.\n"
            "# Regenerate with scripts/map_cbioportal_samples.py. Rows whose `method` is\n"
            "# not one of (" + ", ".join(sorted(DERIVED_METHODS)) + ") are treated as\n"
            "# human-authored and preserved on rerun -- use method=manual for hand fixes.\n"
        )
        writer = csv.DictWriter(handle, fieldnames=CROSSWALK_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def load_crosswalk(path: Path, study_id: str | None = None) -> dict[str, dict]:
    """Read a crosswalk for use by the RDF step: barcode -> row (resolved rows only)."""
    rows = load_existing(path)
    return {
        barcode: row
        for (study, barcode), row in rows.items()
        if (study_id is None or study == study_id) and row.get("specimen_id")
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--maf", type=Path, required=True, help="Study MAF")
    parser.add_argument("--study-id", required=True, help="cBioPortal study id")
    parser.add_argument(
        "--files",
        type=Path,
        default=Path("data/csv/files_harmonized.csv"),
        help="Harmonized files CSV, source of portal specimen/individual ids",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("mappings/cbioportal_sample_specimen.tsv"),
        help="Crosswalk TSV to write (existing manual rows are preserved)",
    )
    args = parser.parse_args(argv)

    barcodes = read_maf_barcodes(args.maf)
    index = index_files(args.files)
    existing = load_existing(args.output)
    rows = build_rows(
        args.study_id,
        barcodes,
        index.specimens,
        index.specimen_individuals,
        existing,
    )
    # One file holds every study, but a run only rebuilds the study it was given, so
    # the other studies' rows have to be carried across or running study B would delete
    # study A -- including the hand-authored rows this file promises to preserve.
    carried = [
        {c: row.get(c, "") for c in CROSSWALK_COLUMNS}
        for (study, _), row in existing.items()
        if study != args.study_id
    ]
    write_crosswalk(args.output, sorted(
        carried + rows, key=lambda r: (r["study_id"], r["tumor_sample_barcode"])
    ))

    resolved = [r for r in rows if r["specimen_id"]]
    with_individual = [r for r in resolved if r["individual_id"]]
    unmatched = [r for r in rows if not r["specimen_id"]]
    manual = [r for r in rows if r["method"] not in DERIVED_METHODS]

    print(f"study                    {args.study_id}")
    print(f"barcodes in MAF          {len(barcodes)}")
    print(f"  resolved to specimen   {len(resolved)}")
    print(f"  with an individual     {len(with_individual)}")
    print(f"  hand-authored rows     {len(manual)}")
    print(f"  UNMATCHED              {len(unmatched)}")
    if carried:
        studies = sorted({r["study_id"] for r in carried})
        print(f"  carried over           {len(carried)} rows ({', '.join(studies)})")
    for row in unmatched:
        print(f"    {row['tumor_sample_barcode']}")
    print(f"output                   {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
