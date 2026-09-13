"""Materialize biolink:Gene nodes from a cBioPortal MAF's gene annotation columns.

Core graph, not part of the reversible variant layer -- gene nodes stay whether or not
the variant layer is published. See `docs/entity-layers.md`.

`biolink:Gene` is used directly, NOT `nf:Gene`: that class already means "a gene entity
annotated in publication text" (PubTator3) and carries no identifiers.

## Ensembl is the key, because the symbol is not

MAF gene columns disagree with each other, and only one pairing is clean. Measured on
`nst_nfosi_ntap` (23,741 rows):

| Mapping | Ambiguous keys |
|---|---|
| `Gene` (ENSG) -> `HGNC_ID` | **0** of 11,211 |
| `HGNC_ID` -> `Gene` | 1 of 11,210 |
| `Hugo_Symbol` -> `Gene` | 82 of 11,304 |
| `Gene` -> `Hugo_Symbol` | 148 of 11,233 |
| `HGNC_ID` -> `Hugo_Symbol` | 146 of 11,210 |

`Hugo_Symbol` is the *picked transcript's* symbol, not the gene's: an antisense or
readthrough transcript (`ACBD3-AS1`, `FBXO38-DT`) carries the overlapping gene's ENSG
and HGNC id. So keying on HGNC would merge genuinely unrelated genes -- `HGNC:11033`
appears as both `SLC4A7` and `UBA52P4`, `HGNC:15464` as both `SPINK5` and `FBXO38-DT`.
Keying on ENSG avoids that, and makes `nf:hgncId` safe to assert because that direction
has no conflicts.

## HGNC is the symbol authority, not the MAF

Picking the *dominant* MAF symbol per gene is not enough: 53 symbols would still end up
labelling two different gene nodes, because a symbol gets borrowed onto a neighbouring
locus. `NF1` landed on both `ENSG00000196712` (really NF1) and `ENSG00000126860` (really
EVI2A, which sits inside the NF1 locus) -- so "how many samples are altered in NF1"
would have silently split across two nodes.

So symbols and names come from HGNC's `hgnc_complete_set.txt`, keyed by the MAF's
`HGNC_ID`, and are accepted only when **HGNC's own `ensembl_gene_id` agrees with the
MAF's `Gene`**. That independent cross-check holds for 11,208 of 11,233 genes (99.8%)
and corrects 271 symbols. The 25 that do not verify keep the dominant MAF symbol and are
counted as unverified rather than quietly trusted.

Nothing is lost by overriding: the observation keeps `nf:affectedGeneSymbol` verbatim,
so every row is still traceable to exactly what the MAF said. Entrez ids are restricted
to those seen alongside the dominant symbol for the same reason.

## Not folded in: portal mutation gene symbols

`data/csv/mutations.csv` has 22 gene symbols, and only 11 overlap the MAF. The rest are
model-organism orthologs (`Nf1`, `Trp53`, `Cdkn2a` mouse; `nf1a`, `nf1b` zebrafish) or
transgene constructs (`Cre`, `CAG-cre/Esr1*`, `SynI`). Case-insensitive symbol matching
would merge mouse `Nf1` into human `NF1` -- a false assertion, and mouse genes belong to
MGI, not HGNC. Those mutations keep their `nf:affectedGeneSymbol` literal instead.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

import urllib.request

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, SKOS, XSD

NF = Namespace("http://nf-osi.github.com/terms#")
BIOLINK = Namespace("https://w3id.org/biolink/vocab/")

# identifiers.org resolves both of these (verified: 302 to ensembl.org / genenames.org).
ENSEMBL_IRI = "https://identifiers.org/ensembl:{}"
HGNC_IRI = "https://identifiers.org/hgnc:{}"

#: MAF placeholders that are not gene identities.
NOT_A_GENE = frozenset({"", ".", "NA", "Unknown", "0"})

HGNC_COMPLETE_SET_URL = (
    "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/"
    "hgnc_complete_set.txt"
)
DEFAULT_HGNC_PATH = Path("data/raw/hgnc_complete_set.txt")

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def gene_iri(ensembl_gene_id: str) -> URIRef:
    return URIRef(ENSEMBL_IRI.format(ensembl_gene_id))


def hgnc_iri(hgnc_id: str) -> URIRef:
    """`HGNC:7765` -> the identifiers.org IRI. The numeric part is the identifier."""
    return URIRef(HGNC_IRI.format(hgnc_id.split(":", 1)[-1]))


def fetch_hgnc(destination: Path = DEFAULT_HGNC_PATH) -> Path:
    """Download the HGNC complete set unless it is already cached."""
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(HGNC_COMPLETE_SET_URL, timeout=180) as resp, \
            open(tmp, "wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    tmp.replace(destination)
    return destination


def load_hgnc(path: Path) -> dict[str, tuple[str, str, str]]:
    """`hgnc_id -> (symbol, name, ensembl_gene_id)` for Approved genes only.

    Withdrawn and merged entries are skipped: adopting a withdrawn symbol would
    reintroduce exactly the ambiguity this lookup exists to remove.
    """
    out: dict[str, tuple[str, str, str]] = {}
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if (row.get("status") or "").strip() != "Approved":
                continue
            out[(row.get("hgnc_id") or "").strip()] = (
                (row.get("symbol") or "").strip(),
                (row.get("name") or "").strip(),
                (row.get("ensembl_gene_id") or "").strip(),
            )
    return out


class GeneIndex:
    """Gene identities keyed on Ensembl gene id, accumulated over MAF rows."""

    def __init__(self) -> None:
        self.symbols: dict[str, Counter] = defaultdict(Counter)
        self.hgnc: dict[str, set[str]] = defaultdict(set)
        #: Entrez ids keyed by the symbol they appeared with, so a minority symbol's id
        #: does not get attached to the gene the dominant symbol names.
        self.entrez_by_symbol: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self.rows = 0
        self.rows_without_ensembl = 0
        #: Symbols seen on rows that had no Ensembl gene id, so got no node.
        self.orphan_symbols: Counter = Counter()

    def add_row(self, ensembl: str, symbol: str, hgnc: str, entrez: str) -> None:
        self.rows += 1
        if ensembl in NOT_A_GENE:
            self.rows_without_ensembl += 1
            if symbol not in NOT_A_GENE:
                self.orphan_symbols[symbol] += 1
            return
        # Touch the counter so a gene with no symbol at all still gets a node.
        counts = self.symbols[ensembl]
        if symbol not in NOT_A_GENE:
            counts[symbol] += 1
            if entrez not in NOT_A_GENE:
                self.entrez_by_symbol[ensembl][symbol].add(entrez)
        if hgnc not in NOT_A_GENE:
            self.hgnc[ensembl].add(hgnc)

    @property
    def genes(self) -> set[str]:
        return set(self.symbols)

    def label_for(self, ensembl: str) -> str | None:
        """Most frequently seen symbol, lexicographic tie-break for determinism."""
        counts = self.symbols.get(ensembl)
        if not counts:
            return None
        return min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]

    def entrez_for(self, ensembl: str) -> set[str]:
        """Entrez ids seen alongside this gene's dominant symbol only."""
        symbol = self.label_for(ensembl)
        if symbol is None:
            return set()
        return self.entrez_by_symbol[ensembl].get(symbol, set())

    @property
    def ambiguous_symbol_genes(self) -> set[str]:
        return {e for e, c in self.symbols.items() if len(c) > 1}

    @property
    def discarded_symbols(self) -> int:
        """Minority symbols not asserted on any gene node."""
        return sum(len(c) - 1 for c in self.symbols.values() if len(c) > 1)

    def resolve_symbol(
        self, ensembl: str, hgnc: dict[str, tuple[str, str, str]]
    ) -> tuple[str | None, str | None]:
        """Authoritative (symbol, name) for a gene, or the MAF fallback.

        HGNC wins only when its own ``ensembl_gene_id`` agrees with the MAF's -- an
        independent check that the MAF's HGNC_ID was assigned to the right locus. When
        it does not agree, or HGNC has no Ensembl id for the gene, the MAF's dominant
        symbol stands and no name is asserted.
        """
        ids = sorted(self.hgnc.get(ensembl, ()))
        if ids:
            entry = hgnc.get(ids[0])
            if entry and entry[2] == ensembl:
                return entry[0] or None, entry[1] or None
        return self.label_for(ensembl), None

    def tally_resolution(
        self, hgnc: dict[str, tuple[str, str, str]], lookup_supplied: bool
    ) -> None:
        """Count how each gene's symbol was decided, for the run report.

        ``lookup_supplied`` is passed rather than inferred from ``hgnc`` being empty:
        "no lookup was given" (offline run, expected) and "the lookup was given but had
        nothing for this gene" (a data problem) are different findings, and only the
        first should raise a warning.
        """
        self.resolution = Counter()
        for ensembl in self.genes:
            if not lookup_supplied:
                self.resolution["no_hgnc_lookup"] += 1
                continue
            ids = sorted(self.hgnc.get(ensembl, ()))
            entry = hgnc.get(ids[0]) if ids else None
            if entry and entry[2] == ensembl:
                self.resolution["verified_by_hgnc"] += 1
                if entry[0] != self.label_for(ensembl):
                    self.resolution["symbol_corrected"] += 1
            else:
                self.resolution["unverified_maf_symbol"] += 1


def index_maf(maf: Path) -> GeneIndex:
    index = GeneIndex()
    with open(maf, newline="") as handle:
        rows = (line for line in handle if not line.startswith("#"))
        reader = csv.DictReader(rows, delimiter="\t")
        required = {"Gene", "Hugo_Symbol"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{maf} is missing required column(s): {sorted(missing)}")
        for row in reader:
            index.add_row(
                (row.get("Gene") or "").strip(),
                (row.get("Hugo_Symbol") or "").strip(),
                (row.get("HGNC_ID") or "").strip(),
                (row.get("Entrez_Gene_Id") or "").strip(),
            )
    return index


def build_graph(
    index: GeneIndex, hgnc: dict[str, tuple[str, str, str]] | None = None
) -> Graph:
    graph = Graph()
    graph.bind("nf", NF)
    graph.bind("biolink", BIOLINK)
    graph.bind("skos", SKOS)
    hgnc = hgnc or {}

    for ensembl in sorted(index.genes):
        node = gene_iri(ensembl)
        graph.add((node, RDF.type, BIOLINK.Gene))
        graph.add((node, NF.ensemblGeneId, Literal(ensembl, datatype=XSD.string)))

        symbol, name = index.resolve_symbol(ensembl, hgnc)
        if symbol:
            graph.add((node, RDFS.label, Literal(symbol)))
            graph.add((node, NF.geneSymbol, Literal(symbol, datatype=XSD.string)))
        if name:
            graph.add((node, NF.geneName, Literal(name, datatype=XSD.string)))

        for hgnc_id in sorted(index.hgnc[ensembl]):
            graph.add((node, NF.hgncId, Literal(hgnc_id, datatype=XSD.string)))
            # An equivalence, not a label: lets HGNC-keyed data join without a lookup.
            graph.add((node, SKOS.exactMatch, hgnc_iri(hgnc_id)))
        for entrez in sorted(index.entrez_for(ensembl)):
            graph.add((node, NF.entrezGeneId, Literal(entrez, datatype=XSD.string)))

    return graph


def materialize_genes(
    maf: Path, output_ttl: Path, hgnc_path: Path | None = None
) -> GeneIndex:
    """Build gene nodes from ``maf``, using ``hgnc_path`` as the symbol authority.

    ``hgnc_path=None`` falls back to the dominant MAF symbol, which leaves ~53 symbols
    labelling the wrong gene -- runnable offline, but not what should be published.
    """
    index = index_maf(maf)
    hgnc = load_hgnc(hgnc_path) if hgnc_path else {}
    index.tally_resolution(hgnc, lookup_supplied=hgnc_path is not None)
    graph = build_graph(index, hgnc)
    output_ttl.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=output_ttl, format="turtle")
    return index


def report(index: GeneIndex, output_ttl: Path) -> str:
    """Run summary, shared by the CLI and the Dagster asset log."""
    resolution = getattr(index, "resolution", Counter())
    lines = [
        f"MAF rows read                {index.rows}",
        f"  no Ensembl gene id         {index.rows_without_ensembl}",
        f"distinct genes               {len(index.genes)}",
        f"  with an HGNC id            {sum(1 for g in index.genes if index.hgnc[g])}",
        f"  with >1 MAF symbol         {len(index.ambiguous_symbol_genes)}",
        f"symbol source:",
        f"  verified against HGNC      {resolution['verified_by_hgnc']}",
        f"    of which corrected       {resolution['symbol_corrected']}",
        f"  unverified MAF symbol      {resolution['unverified_maf_symbol']}",
    ]
    if resolution["no_hgnc_lookup"]:
        lines.append(
            f"  WARNING no HGNC lookup     {resolution['no_hgnc_lookup']} "
            "(symbols may label the wrong gene)"
        )
    lines += [
        f"minority MAF symbols dropped {index.discarded_symbols}",
        f"symbols with no gene node    {len(index.orphan_symbols)}",
        f"output                       {output_ttl}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--maf", type=Path, required=True, help="cBioPortal MAF")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/rdf/genes.ttl"),
        help="Output Turtle. In data/rdf/ (not the variants subdirectory) because gene "
             "nodes are core graph and are not dropped with the variant layer.",
    )
    parser.add_argument(
        "--hgnc",
        type=Path,
        default=None,
        help=f"HGNC complete set TSV (downloaded to {DEFAULT_HGNC_PATH} if absent)",
    )
    parser.add_argument(
        "--no-hgnc",
        action="store_true",
        help="Skip the HGNC lookup and use the dominant MAF symbol. Offline-friendly, "
             "but leaves ~53 symbols labelling the wrong gene",
    )
    args = parser.parse_args(argv)

    hgnc_path = None
    if not args.no_hgnc:
        hgnc_path = args.hgnc or fetch_hgnc()
    index = materialize_genes(args.maf, args.output, hgnc_path)
    print(report(index, args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
