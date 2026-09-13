"""Materialize nf:Specimen and nf:Individual nodes from the harmonized files table.

The portal records `specimenID` and `individualID` as *string literals on nf:File*, so
before this script there were no specimen or individual nodes in the graph: 8,000-odd
specimen identifiers existed only as text hanging off files. Anything that wanted to
reason per-specimen -- "which files came from this specimen", "which specimens belong to
this individual", and in particular the variant layer's "which specimens carry this
variant" (nf-osi/kg-pipeline#95) -- had to string-join at query time.

Both classes are subclassed under BioLink and instances are typed with *both* the
`nf:` class and the BioLink parent -- `nf:Specimen` / `biolink:MaterialSample` and
`nf:Individual` / `biolink:IndividualOrganism`. The second type is emitted rather than
left to `rdfs:subClassOf` because the QLever index does no OWL reasoning, so a
declaration alone would leave `?s a biolink:MaterialSample` matching nothing. Costs
12,623 triples of 149,944. See `docs/biolink-alignment.md` for why these are subclassed
rather than replaced (BioLink has no `biolink:Sample`; its `MaterialSample` maps to a
sibling OBI term, and `biolink:Case` is human-patient-only while many NF individuals are
animals).

This promotes both to first-class nodes and adds the edges:

    nf:File     --nf:fromSpecimen-->   nf:Specimen   (+ inverse nf:hasFile)
    nf:Specimen --nf:fromIndividual--> nf:Individual (+ inverse nf:hasSpecimen)
    nf:File     --nf:fromIndividual--> nf:Individual

The file->individual edge is asserted directly rather than left to be inferred through
the specimen, because 28% of files carry an individualID with no specimenID at all;
routing only through specimens would silently lose them.

## Three things about the source data that shape the implementation

1. **Multi-valued cells.** `specimenID` and `individualID` may hold several ids
   separated by `|` (600 and 1,358 rows respectively). `mappings/rml/files.rml.ttl`
   splits on `|` for the literal properties, so this must too, or those files would be
   attributed to a single specimen named `"N10|N5"`.

2. **NA spellings are not identifiers.** `na`, `nan`, `n/a`, `none`, `unknown`
   (case-insensitive, trimmed) are placeholders. The files RML routes them to
   `nf:hasSpecimenIdStatus nf:UnknownOrNA` instead of `nf:specimenID`; the same
   exclusion list lives in [`NA_VALUES`] here so the two cannot drift.

3. **The same string can be both a specimen and an individual id** -- 2,188 of them
   are. So the two node types get separate IRI stems (`specimen/` vs `individual/`);
   a single `id/` stem would silently merge a specimen with an unrelated individual.

Identifiers are percent-encoded into the IRI: 1,276 specimenIDs and 364 individualIDs
contain characters that are not IRI-safe (spaces, `#`, `[`, `]`, `?`, `"`, en-dash).
`#` matters especially, since the `nf:` namespace is itself a fragment
(`...terms#`) and an unescaped `#` would truncate the IRI.

Note this is deliberately *faithful to the source* rather than curated: some portal
specimenIDs are DICOM instance UIDs (`1.3.6.1.4.1.14519...`) and some individualIDs are
experimental group labels (`cre- veh 52`). They become nodes because the portal calls
them specimen/individual ids. Cleaning that up is a curation job, not a mapping job.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

NF = Namespace("http://nf-osi.github.com/terms#")
BIOLINK = Namespace("https://w3id.org/biolink/vocab/")
SYNAPSE = "https://www.synapse.org/Synapse:"

# Placeholder spellings that are not real identifiers. Mirrors the GREL list in
# mappings/rml/files.rml.ttl ("|na|nan|n/a|none|unknown|"), which routes these to
# nf:hasSpecimenIdStatus / nf:hasIndividualIdStatus nf:UnknownOrNA rather than to an id.
NA_VALUES = frozenset({"na", "nan", "n/a", "none", "unknown"})

# Portal multi-value separator, as split by the files RML.
MULTI_SEP = "|"

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def split_ids(cell: str | None) -> list[str]:
    """Split a portal id cell into real identifiers, dropping NA spellings.

    Returns them in first-seen order with duplicates removed, so a cell like
    ``"N5|N5|na"`` yields ``["N5"]``.
    """
    if not cell:
        return []
    out: list[str] = []
    for part in cell.split(MULTI_SEP):
        part = part.strip()
        if not part or part.lower() in NA_VALUES:
            continue
        if part not in out:
            out.append(part)
    return out


def specimen_iri(specimen_id: str) -> URIRef:
    return URIRef(f"{NF}specimen/{quote(specimen_id, safe='')}")


def individual_iri(individual_id: str) -> URIRef:
    return URIRef(f"{NF}individual/{quote(individual_id, safe='')}")


class SpecimenIndex:
    """Specimen/individual identifiers and their links, accumulated over file rows."""

    def __init__(self) -> None:
        self.specimens: set[str] = set()
        self.individuals: set[str] = set()
        # specimen -> individuals seen on the same file row
        self.specimen_individuals: dict[str, set[str]] = defaultdict(set)
        # specimen/individual -> synapse file ids
        self.specimen_files: dict[str, set[str]] = defaultdict(set)
        self.individual_files: dict[str, set[str]] = defaultdict(set)
        self.rows = 0
        self.rows_with_specimen = 0
        self.rows_with_individual = 0
        self.rows_with_neither = 0

    def add_row(self, file_id: str, specimen_cell: str | None, individual_cell: str | None) -> None:
        self.rows += 1
        specimens = split_ids(specimen_cell)
        individuals = split_ids(individual_cell)
        if specimens:
            self.rows_with_specimen += 1
        if individuals:
            self.rows_with_individual += 1
        if not specimens and not individuals:
            self.rows_with_neither += 1

        self.specimens.update(specimens)
        self.individuals.update(individuals)
        for s in specimens:
            if file_id:
                self.specimen_files[s].add(file_id)
            # A row listing several individuals alongside several specimens (rare) does
            # not say which goes with which, so every pair on the row is asserted.
            self.specimen_individuals[s].update(individuals)
        for i in individuals:
            if file_id:
                self.individual_files[i].add(file_id)

    @property
    def orphan_specimens(self) -> set[str]:
        """Specimens whose rows never named an individual."""
        return {s for s in self.specimens if not self.specimen_individuals[s]}


def index_files(files_csv: Path, id_column: str = "id") -> SpecimenIndex:
    """Read the harmonized files CSV and index its specimen/individual identifiers."""
    index = SpecimenIndex()
    with open(files_csv, newline="") as handle:
        reader = csv.DictReader(handle)
        for column in (id_column, "specimenID", "individualID"):
            if column not in (reader.fieldnames or []):
                raise SystemExit(
                    f"{files_csv} is missing required column {column!r}; "
                    f"found {reader.fieldnames}"
                )
        for row in reader:
            index.add_row(
                (row.get(id_column) or "").strip(),
                row.get("specimenID"),
                row.get("individualID"),
            )
    return index


def build_graph(index: SpecimenIndex) -> Graph:
    """Turn an index into the specimen/individual RDF."""
    graph = Graph()
    graph.bind("nf", NF)
    graph.bind("biolink", BIOLINK)

    for specimen_id in sorted(index.specimens):
        node = specimen_iri(specimen_id)
        graph.add((node, RDF.type, NF.Specimen))
        graph.add((node, RDF.type, BIOLINK.MaterialSample))
        graph.add((node, NF.specimenID, Literal(specimen_id, datatype=XSD.string)))
        for individual_id in sorted(index.specimen_individuals[specimen_id]):
            graph.add((node, NF.fromIndividual, individual_iri(individual_id)))
            graph.add((individual_iri(individual_id), NF.hasSpecimen, node))
        for file_id in sorted(index.specimen_files[specimen_id]):
            file_node = URIRef(f"{SYNAPSE}{file_id}")
            graph.add((file_node, NF.fromSpecimen, node))
            graph.add((node, NF.hasFile, file_node))

    for individual_id in sorted(index.individuals):
        node = individual_iri(individual_id)
        graph.add((node, RDF.type, NF.Individual))
        graph.add((node, RDF.type, BIOLINK.IndividualOrganism))
        graph.add((node, NF.individualID, Literal(individual_id, datatype=XSD.string)))
        for file_id in sorted(index.individual_files[individual_id]):
            graph.add((URIRef(f"{SYNAPSE}{file_id}"), NF.fromIndividual, node))

    return graph


def materialize_specimens(
    files_csv: Path,
    output_ttl: Path,
    id_column: str = "id",
) -> SpecimenIndex:
    """Build specimen/individual nodes from ``files_csv`` and write ``output_ttl``."""
    index = index_files(files_csv, id_column=id_column)
    graph = build_graph(index)
    output_ttl.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=output_ttl, format="turtle")
    return index


def report(index: SpecimenIndex, output_ttl: Path) -> str:
    """Human-readable run summary, shared by the CLI and the Dagster asset log."""
    orphans = index.orphan_specimens
    lines = [
        f"files rows read              {index.rows}",
        f"  with a specimenID          {index.rows_with_specimen}",
        f"  with an individualID       {index.rows_with_individual}",
        f"  with neither               {index.rows_with_neither}",
        f"distinct specimens           {len(index.specimens)}",
        f"distinct individuals         {len(index.individuals)}",
        f"specimens with no individual {len(orphans)}",
        f"output                       {output_ttl}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--files",
        default=Path("data/csv/files_harmonized.csv"),
        type=Path,
        help="Harmonized portal files CSV (the same input the files RML consumes)",
    )
    parser.add_argument(
        "--output",
        default=Path("data/rdf/specimens.ttl"),
        type=Path,
        help="Output path for the specimen/individual Turtle",
    )
    parser.add_argument(
        "--id-column",
        default="id",
        help="Column holding the Synapse file id",
    )
    args = parser.parse_args(argv)

    index = materialize_specimens(args.files, args.output, id_column=args.id_column)
    print(report(index, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
