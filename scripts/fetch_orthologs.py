#!/usr/bin/env python3
"""Build `mappings/orthologs.tsv`: model-organism gene -> human gene, for the genes
NF-OSI curates mutations on.

## Why this exists

Curated model-system mutations (`data/csv/mutations.csv`) name their gene with a
*model-organism* symbol -- `Nf1`, `Trp53`, `nf1a` -- while the somatic variant layer
names genes with human HGNC identifiers. The two can never meet: every animal model in
the registry matches zero patient alleles, structurally, and that zero reads as "no
coverage" when it actually means "no crosswalk". This file is the crosswalk, and it is
deliberately the size of the problem -- tens of rows for the ~20 genes in
`mutations.csv`, not a genome-wide ortholog table.

## Source

Alliance of Genome Resources combined orthology, `Stringent` filter. Chosen over HGNC
HCOP because HCOP's bulk TSVs moved off `ftp.ebi.ac.uk` and are not served from the
HGNC download bucket that `materialize_genes.py` already uses; the Alliance file is a
single stable URL, carries HGNC ids on the human side directly (so no second lookup),
and ships per-pair support counts (`AlgorithmsMatch` / `OutOfAlgorithms`) that let a
weak call like CDKN2A->Cdkn2a be seen rather than assumed.

The release is pinned by SHA-256, the same discipline as `fetch_cbioportal_maf.py`: the
Alliance serves `/download/ORTHOLOGY-ALLIANCE_COMBINED.tsv.gz` as a moving "current
release" pointer, so the URL alone is not a pin.

## Species disambiguation is data-driven, not guessed

`Nf1` is a valid symbol in both mouse (MGI:97306) and rat (RGD:3168). Picking one by
convention would be a coin flip. Instead each symbol's species is read off the animal
models that actually carry the mutation (`mutation_model.csv` -> `animal_models.csv`
-> `species`), and the script fails rather than guessing if that does not resolve to
exactly one species.

## Constructs get no row, visibly

Cre drivers and transgenes are not orthologs of anything -- a `Dhh-Cre` line is a tool
for tissue-specific recombination, not a model of DHH loss, and letting it through
would report DHH as "covered" in the gap analysis. They are listed in EXCLUDED with a
reason and written to the TSV as `status=excluded`, so their absence from the graph is
a decision on the record rather than a hole.

Usage:
    python scripts/fetch_orthologs.py
    python scripts/fetch_orthologs.py --check      # verify the checked-in TSV is current
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Alliance combined orthology, `Stringent` filter. Moving pointer at the URL; the
#: digest is the actual pin. Bump both together, and record the release in HEADER.
ORTHOLOGY_URL = (
    "https://fms.alliancegenome.org/download/ORTHOLOGY-ALLIANCE_COMBINED.tsv.gz"
)
ORTHOLOGY_SHA256 = "977ad252878d25a6cf486a9054448feff0e308e83e2fe5d6e8b6ec31c45491d4"
#: From the downloaded file's own header block -- asserted below, not just recorded.
ORTHOLOGY_RELEASE = "9.0.0"
ORTHOLOGY_GENERATED = "2026-04-05"
ORTHOLOGY_CACHE = REPO_ROOT / "data" / "raw" / "ORTHOLOGY-ALLIANCE_COMBINED.tsv.gz"

DEFAULT_MUTATIONS = REPO_ROOT / "data" / "csv" / "mutations.csv"
DEFAULT_MUTATION_MODEL = REPO_ROOT / "data" / "csv" / "mutation_model.csv"
DEFAULT_ANIMAL_MODELS = REPO_ROOT / "data" / "csv" / "animal_models.csv"
DEFAULT_OUTPUT = REPO_ROOT / "mappings" / "orthologs.tsv"

HUMAN_TAXON = "NCBITaxon:9606"
HGNC_IRI = "https://identifiers.org/hgnc:{}"

#: Symbols in `mutations.csv` that name a construct or a promoter, not a gene whose
#: loss the model is meant to represent. Each is a recombinase driver line: the symbol
#: says where Cre is expressed, not what is broken. Giving these ortholog rows would
#: make the gap analysis report DHH, GFAP and SYN1 as modelled NF genes.
EXCLUDED: dict[str, str] = {
    "Cre": "Cre recombinase; a transgene, not a locus",
    "CAG-cre/Esr1*": "CAG-CreER transgene (CAG promoter + Cre-ERT2 fusion)",
    "GFAP": "human GFAP promoter driving Cre; the allele is the driver, not GFAP loss",
    "SynI": "rat synapsin I promoter driving Cre; driver, not SYN1 loss",
    "Dhh": "Dhh-Cre knock-in; the Dhh locus carries the driver, it is not the modelled gene",
    "": "zebrafish dlx5a/dlx6a:cre transgene, curated with no gene symbol",
}

HEADER = f"""\
# Model-organism gene -> human gene, for the genes NF-OSI curates mutations on.
# Regenerate with scripts/fetch_orthologs.py; verify with --check.
#
# source: Alliance of Genome Resources combined orthology ({ORTHOLOGY_URL})
# release: {ORTHOLOGY_RELEASE}   file generated (UTC): {ORTHOLOGY_GENERATED}
# orthology filter: Stringent
# sha256: {ORTHOLOGY_SHA256}
#
# status=ortholog   a model-organism gene mapped to its human gene; the only rows that
#                   become nf:hasOrtholog triples (scripts/materialize_orthologs.py)
# status=human      the curated symbol is already human; no crosswalk needed, listed so
#                   the audit of mutations.csv's symbol vocabulary is complete
# status=excluded   a construct or promoter, not a modelled locus; see `notes`
# status=unresolved a non-human symbol the Alliance release does not cover; a real gap,
#                   left visible rather than dropped
#
# support = AlgorithmsMatch / OutOfAlgorithms from the Alliance file. CDKN2A->Cdkn2a is
# 1/10: the mouse Cdkn2a/Cdkn2b locus does not correspond cleanly to the human one, and
# that is a fact about the biology, not a defect in the row. Kept visible on purpose.
"""

COLUMNS = [
    "status",
    "curated_symbol",
    "model_gene_id",
    "model_gene_symbol",
    "model_species",
    "human_gene_id",
    "human_symbol",
    "human_iri",
    "support",
    "is_best_score",
    "is_best_rev_score",
    "notes",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_orthology(cache: Path = ORTHOLOGY_CACHE) -> Path:
    """Download the pinned Alliance release unless a cached copy matches the digest."""
    if cache.exists() and sha256_file(cache) == ORTHOLOGY_SHA256:
        return cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(cache.suffix + ".part")
    with urllib.request.urlopen(ORTHOLOGY_URL, timeout=300) as resp, tmp.open("wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    got = sha256_file(tmp)
    if got != ORTHOLOGY_SHA256:
        tmp.unlink()
        raise SystemExit(
            f"{ORTHOLOGY_URL} digest {got} != pinned {ORTHOLOGY_SHA256}.\n"
            "The Alliance published a new release behind the same URL. Re-pin "
            "ORTHOLOGY_SHA256/_RELEASE/_GENERATED after reviewing the diff."
        )
    tmp.replace(cache)
    return cache


def read_orthology(path: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Return (human-anchored pair rows, header metadata declared by the file)."""
    meta: dict[str, str] = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        text = handle.read()
    lines = text.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("#"):
            if ":" in line:
                key, _, value = line.lstrip("# ").partition(":")
                meta[key.strip()] = value.strip()
            continue
        body_start = i
        break
    reader = csv.DictReader(io.StringIO("\n".join(lines[body_start:])), delimiter="\t")
    rows = [r for r in reader if r["Gene1SpeciesTaxonID"] == HUMAN_TAXON]
    return rows, meta


def curated_symbols(
    mutations_csv: Path, mutation_model_csv: Path, animal_models_csv: Path
) -> tuple[dict[str, int], dict[str, set[str]]]:
    """Symbols used in `mutations.csv`, and the animal-model species carrying each.

    Species comes from the models rather than from the symbol's casing: casing is a
    curation convention, and `mutations.csv` already breaks it in both directions (4
    human cell lines carry mouse-cased `Nf1`, one pig model carries human `NF1`).
    """
    mutations = {r["mutationId"]: r for r in csv.DictReader(mutations_csv.open())}
    animals = {r["resourceId"]: r for r in csv.DictReader(animal_models_csv.open())}

    counts: dict[str, int] = defaultdict(int)
    for row in mutations.values():
        counts[row["affectedGeneSymbol"]] += 1

    species: dict[str, set[str]] = defaultdict(set)
    for link in csv.DictReader(mutation_model_csv.open()):
        mutation = mutations.get(link["mutationId"])
        model = animals.get(link["resourceId"])
        if mutation and model and model.get("species"):
            species[mutation["affectedGeneSymbol"]].add(model["species"])
    return dict(counts), dict(species)


def build_rows(
    pairs: list[dict[str, str]],
    counts: dict[str, int],
    species: dict[str, set[str]],
) -> list[dict[str, str]]:
    human_by_symbol = {p["Gene1Symbol"]: p for p in pairs}
    # (model symbol, model species) -> pair rows. Keyed on both because `Nf1` alone is
    # mouse and rat at once.
    by_model: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for p in pairs:
        by_model[(p["Gene2Symbol"], p["Gene2SpeciesName"])].append(p)

    rows: list[dict[str, str]] = []
    for symbol in sorted(counts, key=lambda s: (s == "", s.lower(), s)):
        base = {c: "" for c in COLUMNS}
        base["curated_symbol"] = symbol
        base["notes"] = f"{counts[symbol]} mutation row(s) in mutations.csv"

        if symbol in EXCLUDED:
            rows.append({**base, "status": "excluded",
                         "notes": f"{EXCLUDED[symbol]}; {base['notes']}"})
            continue

        if symbol in human_by_symbol:
            p = human_by_symbol[symbol]
            rows.append({**base, "status": "human",
                         "human_gene_id": p["Gene1ID"], "human_symbol": p["Gene1Symbol"],
                         "human_iri": HGNC_IRI.format(p["Gene1ID"].split(":")[-1])})
            continue

        model_species = species.get(symbol, set())
        if len(model_species) != 1:
            rows.append({**base, "status": "unresolved",
                         "notes": f"species did not resolve to exactly one "
                                  f"({sorted(model_species) or 'no animal model link'}); "
                                  f"{base['notes']}"})
            continue
        organism = next(iter(model_species))
        matches = by_model.get((symbol, organism), [])
        if not matches:
            rows.append({**base, "status": "unresolved", "model_species": organism,
                         "notes": f"no {organism} ortholog in Alliance "
                                  f"{ORTHOLOGY_RELEASE}; {base['notes']}"})
            continue
        for p in sorted(matches, key=lambda m: m["Gene1ID"]):
            rows.append({
                **base,
                "status": "ortholog",
                "model_gene_id": p["Gene2ID"],
                "model_gene_symbol": p["Gene2Symbol"],
                "model_species": p["Gene2SpeciesName"],
                "human_gene_id": p["Gene1ID"],
                "human_symbol": p["Gene1Symbol"],
                "human_iri": HGNC_IRI.format(p["Gene1ID"].split(":")[-1]),
                "support": f"{p['AlgorithmsMatch']}/{p['OutOfAlgorithms']}",
                "is_best_score": p["IsBestScore"],
                "is_best_rev_score": p["IsBestRevScore"],
            })
    return rows


def render(rows: list[dict[str, str]]) -> str:
    out = io.StringIO()
    out.write(HEADER)
    writer = csv.DictWriter(out, fieldnames=COLUMNS, delimiter="\t",
                            lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mutations", type=Path, default=DEFAULT_MUTATIONS)
    parser.add_argument("--mutation-model", type=Path, default=DEFAULT_MUTATION_MODEL)
    parser.add_argument("--animal-models", type=Path, default=DEFAULT_ANIMAL_MODELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true",
                        help="Exit non-zero if the checked-in TSV differs from a fresh build")
    args = parser.parse_args(argv)

    path = fetch_orthology()
    pairs, meta = read_orthology(path)
    declared = meta.get("Alliance Database Version")
    if declared and declared != ORTHOLOGY_RELEASE:
        raise SystemExit(
            f"file declares release {declared}, pinned as {ORTHOLOGY_RELEASE}"
        )

    counts, species = curated_symbols(args.mutations, args.mutation_model,
                                      args.animal_models)
    rows = build_rows(pairs, counts, species)
    text = render(rows)

    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != text:
            print(f"{args.output} is out of date; rerun without --check", file=sys.stderr)
            return 1
        print(f"{args.output} is current")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")

    tally = defaultdict(int)
    for row in rows:
        tally[row["status"]] += 1
    print(f"wrote {args.output} ({len(rows)} rows): " +
          ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    for row in rows:
        if row["status"] == "unresolved":
            print(f"  unresolved: {row['curated_symbol']!r} -- {row['notes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
