#!/usr/bin/env python3
"""Mint GA4GH VRS identifiers for the curated model-system mutations that carry a
ClinVar expression, and write `mappings/model_mutation_vrs.tsv`.

## Why

`nf:Mutation` nodes describe what a cell line or animal model carries, as HGVS strings.
The somatic variant layer describes what patients carry, as `ga4gh:VA.*` digests. Today
the two are joined on the HGVS **protein** string plus a gene constraint, which is
documented as fragile in docs/demos/variant-layer-demo.md (pitfalls 2 and 3): a protein
change is not gene-scoped, and the same allele spelled against two transcripts produces
two different protein strings. Both failure modes are real in this data -- `p.Arg1947Ter`
(NM_000267.3) and `p.Arg1968Ter` (NM_001042492.3) are the same allele.

Giving the curated mutations a VRS identity replaces that with a digest-to-digest join.
It only works for the mutations that carry `humanClinVarMutation`, because that column
is the only one with a transcript accession; `nf:sequenceVariation` holds bare cDNA
(`c.910C>T`) which cannot be projected to coordinates without knowing the transcript.
Those stay on the protein-string tier. That two-tier split is the point, not a shortfall.

## Route

    humanClinVarMutation                       NM_000267.3(NF1):c.910C>T (p.Arg304Ter)
      -> transcript HGVS                       NM_000267.3:c.910C>T
      -> NCBI Variation Services               NM_000267.3:1292:C:T        (transcript SPDI)
      -> .../canonical_representative          NC_000017.11:31200442:C:T   (genomic SPDI)
      -> ClinVar esearch/esummary              VCV000210652, canonical_spdi
      -> agreement check                       the two SPDIs must be identical
      -> VCF (anchor bases read from hg38)     chr17  31200443  C  T
      -> vrsify --strict --reference           ga4gh:VA.tYkXXkZwcWWOMYuwRTMlAFaI2KP-EAKr

The two resolvers are kept as a **cross-check**, not a fallback chain: Variation
Services projects the exact transcript the curator wrote, ClinVar's `canonical_spdi`
comes from the submitted record, and requiring them to agree is what makes a minted
digest trustworthy enough to assert as identity. Where they cannot be compared the row
says so in its `evidence` column rather than looking like a verified one.

Intronic positions (`c.96+1G>A`) are the known asymmetry: Variation Services rejects
them because a transcript SPDI has no coordinate for an intron, while ClinVar carries
the genomic record. Those rows are `evidence=clinvar_only` and are verified instead by
requiring ClinVar's own preferred name or an alias to reproduce the curated expression.

## Provenance

Per-row provenance (ClinVar VCV id, assembly coordinates, both SPDIs, how the row was
verified) is in the columns. Run-level provenance (mint date, vrsify version, source
endpoints) is in the file header, because a column repeating one value on every row
makes the TSV noisier without making it more auditable, and a per-row mint date would
make the checked-in file differ on every regeneration.

Usage:
    python scripts/mint_model_mutation_vrs.py
    python scripts/mint_model_mutation_vrs.py --limit 5 --output /tmp/probe.tsv
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

VARIATION_SERVICES = "https://api.ncbi.nlm.nih.gov/variation/v0"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
USER_AGENT = "nf-osi-kg-pipeline/mint_model_mutation_vrs"
#: NCBI allows 3 requests/second without an API key; this script makes two or three
#: per mutation and there are only ~40, so it just stays under the limit rather than
#: asking anyone to provision a key.
REQUEST_INTERVAL = 0.4

DEFAULT_MUTATIONS = REPO_ROOT / "data" / "csv" / "mutations.csv"
DEFAULT_OUTPUT = REPO_ROOT / "mappings" / "model_mutation_vrs.tsv"
DEFAULT_REFERENCE = REPO_ROOT / "data" / "reference" / "GRCh38" / "hg38.fa"
DEFAULT_SEQMAP = REPO_ROOT / "data" / "reference" / "GRCh38" / "seqmap.tsv"
DEFAULT_VRSIFY = REPO_ROOT / "data" / "tools" / "vrsify" / "bin" / "vrsify"

#: `NM_000267.3(NF1):c.910C>T (p.Arg304Ter)`, and the gene and protein halves are both
#: optional -- splice variants are curated as `NM_000546.6(TP53):c.96+1G>A`.
CLINVAR_EXPRESSION = re.compile(
    r"^(?P<accession>[A-Z]{2}_[\d.]+)"
    r"(?:\((?P<gene>[^)]+)\))?"
    r":(?P<hgvs_c>[^ ]+?)"
    r"(?:\s+\((?P<hgvs_p>p\.[^)]+)\))?$"
)

COLUMNS = [
    "mutation_id",
    "gene_symbol",
    "clinvar_expression",
    "hgvs_c",
    "hgvs_p",
    "clinvar_vcv",
    "assembly",
    "chromosome",
    "position",
    "reference_bases",
    "alternate_bases",
    "genomic_spdi",
    "variation_services_spdi",
    "evidence",
    "vrs_id",
    "notes",
]


class Throttle:
    """One shared clock for every NCBI call, so the rate limit is a property of the
    run rather than of whichever function happened to sleep last."""

    def __init__(self, interval: float = REQUEST_INTERVAL) -> None:
        self.interval = interval
        self._last = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self._last = time.monotonic()


def get_json(url: str, throttle: Throttle, attempts: int = 4) -> dict:
    """GET with backoff on 429/5xx. A 400 is a real answer here (Variation Services
    rejects intronic HGVS that way), so it is raised immediately rather than retried."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(attempts):
        throttle.wait()
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as err:
            if err.code < 500 and err.code != 429:
                raise
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


# --------------------------------------------------------------------------- FASTA

def build_fai(fasta: Path, fai: Path) -> None:
    """Write a samtools-compatible .fai. Vendored (~20 lines) rather than taking a
    pysam/samtools dependency for the handful of anchor bases this script reads."""
    entries = []
    with fasta.open("rb") as handle:
        name, offset, length, line_bases, line_width, pos = None, 0, 0, 0, 0, 0
        for line in handle:
            if line.startswith(b">"):
                if name is not None:
                    entries.append((name, length, offset, line_bases, line_width))
                name = line[1:].split()[0].decode()
                offset, length, line_bases, line_width = pos + len(line), 0, 0, 0
            else:
                sequence = line.rstrip(b"\r\n")
                if line_bases == 0:
                    line_bases, line_width = len(sequence), len(line)
                length += len(sequence)
            pos += len(line)
        if name is not None:
            entries.append((name, length, offset, line_bases, line_width))
    fai.write_text("".join("\t".join(str(f) for f in e) + "\n" for e in entries))


class Reference:
    def __init__(self, fasta: Path) -> None:
        self.path = fasta
        fai = fasta.with_name(fasta.name + ".fai")
        if not fai.exists():
            build_fai(fasta, fai)
        self.index = {}
        for line in fai.read_text().splitlines():
            name, length, offset, line_bases, line_width = line.split("\t")
            self.index[name] = (int(length), int(offset), int(line_bases), int(line_width))
        self._handle = fasta.open("rb")

    def fetch(self, contig: str, start: int, end: int) -> str:
        """0-based, half-open."""
        length, offset, line_bases, line_width = self.index[contig]
        if start < 0 or end > length:
            raise ValueError(f"{contig}:{start}-{end} outside {contig} (length {length})")
        out, pos = [], start
        while pos < end:
            line_no, column = divmod(pos, line_bases)
            take = min(line_bases - column, end - pos)
            self._handle.seek(offset + line_no * line_width + column)
            out.append(self._handle.read(take).decode())
            pos += take
        return "".join(out).upper()


# ------------------------------------------------------------------------ resolving

def parse_expression(value: str) -> re.Match[str] | None:
    """Parse the first expression of a `humanClinVarMutation` cell.

    The column is pipe-separated where a curator recorded the same allele against a
    second transcript (`...c.5488C>T (p.Arg1830Cys)|NM_000267.3:c.5425C>T:...`). The
    first is the ClinVar-formatted one; the rest are notes, and both spellings resolve
    to the same digest anyway, which is exactly what this file is for.
    """
    return CLINVAR_EXPRESSION.match(value.split("|")[0].strip())


def refseq_contig(accession: str) -> str:
    """`NC_000017.11` -> `chr17`. Numbering is the RefSeq chromosome convention:
    01-22 are the autosomes, 23 is X, 24 is Y."""
    match = re.fullmatch(r"NC_0000(\d\d)\.\d+", accession)
    if not match:
        raise ValueError(f"not a RefSeq GRCh38 chromosome accession: {accession}")
    number = int(match.group(1))
    name = {23: "X", 24: "Y"}.get(number, str(number))
    return f"chr{name}"


def variation_services_spdi(hgvs: str, throttle: Throttle) -> str | None:
    """Project a transcript HGVS to a genomic SPDI, or None if NCBI declines it.

    Declining is informative rather than an error: an intronic `c.96+1G>A` has no
    transcript coordinate, so the 400 means "ask ClinVar", not "this is broken".
    """
    quoted = urllib.parse.quote(hgvs, safe="")
    try:
        data = get_json(f"{VARIATION_SERVICES}/hgvs/{quoted}/contextuals", throttle)
    except urllib.error.HTTPError as err:
        if err.code == 400:
            return None
        raise
    spdis = data["data"]["spdis"]
    if len(spdis) != 1:
        return None
    s = spdis[0]
    key = f"{s['seq_id']}:{s['position']}:{s['deleted_sequence']}:{s['inserted_sequence']}"
    genomic = get_json(
        f"{VARIATION_SERVICES}/spdi/{urllib.parse.quote(key, safe='')}"
        "/canonical_representative",
        throttle,
    )["data"]
    return (f"{genomic['seq_id']}:{genomic['position']}:"
            f"{genomic['deleted_sequence']}:{genomic['inserted_sequence']}")


#: ClinVar's preferred name carries the gene in parentheses
#: (`NM_001042492.3(NF1):c.6704+1G>T`); a curated expression may or may not. Strip it
#: on both sides before comparing, or an intronic variant that ClinVar names exactly
#: reads as unconfirmed.
GENE_PARENTHETICAL = re.compile(r"\([^)]*\)")


def normalize_hgvs(value: str) -> str:
    return GENE_PARENTHETICAL.sub("", value).replace(" ", "")


#: How many RefSeq transcript versions above the curated one to try. ClinVar indexes
#: HGVS against the CURRENT version of a transcript only, so a mutation curated as
#: `NM_000546.5:c.405C>G` finds nothing once NCBI moves TP53 to `.6`. Walking forward
#: cannot manufacture a false match: whatever it finds still has to produce the same
#: genomic SPDI as the version the curator actually wrote.
VERSION_LOOKAHEAD = 3


def clinvar_search(hgvs: str, throttle: Throttle) -> list[str]:
    """ClinVar UIDs for a quoted HGVS expression.

    Quoting matters: an unquoted `NM_000267.3:c.910C>T` is tokenized and ANDed, which
    happily returns `c.909_910delinsTT` -- a different allele at an overlapping
    position.
    """
    term = urllib.parse.quote(f'"{hgvs}"')
    return get_json(f"{EUTILS}/esearch.fcgi?db=clinvar&retmode=json&term={term}",
                    throttle)["esearchresult"]["idlist"]


def clinvar_record(hgvs: str, throttle: Throttle) -> dict | None:
    """Look a transcript HGVS up in ClinVar and return the single matching record.

    More than one hit is treated as no hit: this file asserts allele identity, and
    picking one of several by rank would be guessing.
    """
    ids = clinvar_search(hgvs, throttle)
    searched = hgvs
    if not ids:
        accession, _, remainder = hgvs.partition(":")
        base, _, version = accession.rpartition(".")
        if base and version.isdigit():
            for bump in range(1, VERSION_LOOKAHEAD + 1):
                candidate = f"{base}.{int(version) + bump}:{remainder}"
                ids = clinvar_search(candidate, throttle)
                if ids:
                    searched = candidate
                    break
    if len(ids) != 1:
        return None
    result = get_json(
        f"{EUTILS}/esummary.fcgi?db=clinvar&retmode=json&id={ids[0]}", throttle
    )["result"]
    record = result[ids[0]]
    variation = record["variation_set"][0]
    grch38 = next((loc for loc in variation.get("variation_loc", [])
                   if loc.get("assembly_name") == "GRCh38"), None)
    return {
        "searched": searched,
        "vcv": record.get("accession", ""),
        "spdi": variation.get("canonical_spdi", ""),
        "name": variation.get("variation_name", ""),
        "aliases": variation.get("aliases", []),
        "chromosome": (grch38 or {}).get("chr", ""),
        "start": (grch38 or {}).get("start", ""),
    }


def spdi_to_vcf(spdi: str, reference: Reference) -> tuple[str, int, str, str]:
    """Genomic SPDI -> a VCF (CHROM, POS, REF, ALT) record.

    Pure insertions and deletions get the VCF anchor base, read from the reference
    rather than carried over from the SPDI, and the SPDI's deleted sequence is asserted
    against the reference on the way past. `vrsify --strict` checks this again; doing
    it here means a mismatch names the mutation that caused it.
    """
    seq_id, position, deleted, inserted = spdi.split(":")
    contig = refseq_contig(seq_id)
    start = int(position)

    observed = reference.fetch(contig, start, start + len(deleted)) if deleted else ""
    if observed != deleted:
        raise ValueError(
            f"{spdi}: reference has {observed!r} at {contig}:{start}, SPDI says {deleted!r}"
        )

    if deleted and inserted:
        return contig, start + 1, deleted, inserted
    anchor = reference.fetch(contig, start - 1, start)
    return contig, start, anchor + deleted, anchor + inserted


# ----------------------------------------------------------------------------- main

def collect(mutations_csv: Path) -> list[dict[str, str]]:
    rows = []
    for row in csv.DictReader(mutations_csv.open()):
        expression = row["humanClinVarMutation"].strip()
        if expression:
            rows.append(row)
    return rows


def resolve_all(rows: list[dict[str, str]], reference: Reference,
                throttle: Throttle) -> list[dict[str, str]]:
    resolved: list[dict[str, str]] = []
    cache: dict[str, dict[str, str]] = {}

    for row in rows:
        expression = row["humanClinVarMutation"].strip()
        base = {c: "" for c in COLUMNS}
        base.update(mutation_id=row["mutationId"],
                    gene_symbol=row["affectedGeneSymbol"],
                    clinvar_expression=expression)

        if expression in cache:
            resolved.append({**base, **cache[expression]})
            continue

        match = parse_expression(expression)
        if not match:
            resolved.append({**base, "evidence": "unparsed",
                             "notes": "does not match the ClinVar expression grammar"})
            continue
        hgvs_c = f"{match['accession']}:{match['hgvs_c']}"
        found = {"hgvs_c": hgvs_c, "hgvs_p": match["hgvs_p"] or ""}

        vs_spdi = variation_services_spdi(hgvs_c, throttle)
        record = clinvar_record(hgvs_c, throttle)
        found["variation_services_spdi"] = vs_spdi or ""
        if record:
            found.update(clinvar_vcv=record["vcv"], chromosome=record["chromosome"],
                         position=record["start"], assembly="GRCh38")
            if record["searched"] != hgvs_c:
                found["notes"] = (f"ClinVar indexes this as {record['searched']}; the "
                                  f"curated transcript version is superseded")

        cv_spdi = (record or {}).get("spdi", "")
        if vs_spdi and cv_spdi and vs_spdi == cv_spdi:
            found.update(genomic_spdi=vs_spdi, evidence="both_agree")
            # keep any transcript-version note already recorded
        elif vs_spdi and cv_spdi:
            found.update(evidence="disagree",
                         notes=f"Variation Services {vs_spdi} != ClinVar {cv_spdi}")
        elif vs_spdi:
            found.update(genomic_spdi=vs_spdi, evidence="variation_services_only",
                         notes="no single ClinVar record for this expression")
        elif cv_spdi:
            wanted = normalize_hgvs(record["searched"])
            named = (wanted in normalize_hgvs(record["name"])
                     or any(wanted in normalize_hgvs(a) for a in record["aliases"]))
            if named:
                found.update(genomic_spdi=cv_spdi, evidence="clinvar_only",
                             notes="Variation Services cannot project this position "
                                   "(intronic); ClinVar reproduces the curated expression")
            else:
                found.update(evidence="clinvar_unconfirmed",
                             notes=f"ClinVar {record['vcv']} does not name {hgvs_c}")
        else:
            found.update(evidence="unresolved",
                         notes="neither NCBI service returned coordinates")

        if found.get("genomic_spdi"):
            contig, pos, ref, alt = spdi_to_vcf(found["genomic_spdi"], reference)
            found.update(chromosome=contig, position=str(pos),
                         reference_bases=ref, alternate_bases=alt, assembly="GRCh38")

        cache[expression] = found
        resolved.append({**base, **found})
    return resolved


def mint(resolved: list[dict[str, str]], vrsify: Path, seqmap: Path,
         reference_fasta: Path, workdir: Path) -> dict[tuple[str, str, str, str], str]:
    """Run vrsify over the resolved coordinates and return (contig,pos,ref,alt) -> VRS id.

    A sample column is present because vrsify emits observations per sample, and the
    observation is the only output that carries the input coordinates back out --
    the allele NDJSON is context-free by design, so there is nothing in it to join on.
    """
    records = {}
    for row in resolved:
        if row.get("reference_bases"):
            key = (row["chromosome"], row["position"],
                   row["reference_bases"], row["alternate_bases"])
            records[key] = None
    if not records:
        return {}

    workdir.mkdir(parents=True, exist_ok=True)
    vcf = workdir / "model_mutations.vcf"
    with vcf.open("w") as out:
        out.write("##fileformat=VCFv4.2\n")
        out.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tMODEL\n")
        for contig, pos, ref, alt in sorted(
            records, key=lambda k: (k[0], int(k[1]))
        ):
            out.write(f"{contig}\t{pos}\t.\t{ref}\t{alt}\t.\t.\t.\tGT\t0/1\n")

    alleles = workdir / "alleles.ndjson"
    observations = workdir / "observations.ndjson"
    subprocess.run(
        [str(vrsify), "convert", "--vcf", str(vcf), "--seqmap", str(seqmap),
         "--reference", str(reference_fasta), "--out-alleles", str(alleles),
         "--out-observations", str(observations), "--strict",
         "--source", "nf-osi:mutations.csv#humanClinVarMutation"],
        check=True,
    )

    minted = {}
    for line in observations.read_text().splitlines():
        obs = json.loads(line)
        key = (obs["sourceContig"], str(obs["sourcePos"]),
               obs["referenceBases"], obs["alternateBases"])
        minted[key] = obs["variant"]
    return minted


def render(rows: list[dict[str, str]], vrsify_version: str, minted_on: str) -> str:
    header = f"""\
# GA4GH VRS identifiers for curated model-system mutations that carry a ClinVar
# expression. Regenerate with scripts/mint_model_mutation_vrs.py.
#
# minted: {minted_on}   vrsify: {vrsify_version}
# assembly: GRCh38 (data/reference/GRCh38/hg38.fa, seqmap.tsv)
# coordinate sources: NCBI Variation Services ({VARIATION_SERVICES})
#                     NCBI ClinVar via E-utilities ({EUTILS})
#
# evidence=both_agree              Variation Services and ClinVar returned the same
#                                  genomic SPDI; the digest is asserted as identity
# evidence=clinvar_only            intronic position; Variation Services cannot project
#                                  it, ClinVar's record reproduces the curated expression
# evidence=variation_services_only no single ClinVar record matched the expression
# evidence=disagree / unresolved / clinvar_unconfirmed / unparsed
#                                  no digest minted; see `notes`
#
# vrs_id is the SAME identifier space as the somatic variant layer's nf:vrsId, which is
# the whole point: a model mutation and a patient allele are the same allele when the
# two digests are equal, with no string comparison in between.
"""
    out = io.StringIO()
    out.write(header)
    writer = csv.DictWriter(out, fieldnames=COLUMNS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--mutations", type=Path, default=DEFAULT_MUTATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--seqmap", type=Path, default=DEFAULT_SEQMAP)
    parser.add_argument("--vrsify", type=Path, default=DEFAULT_VRSIFY)
    parser.add_argument("--workdir", type=Path, default=Path("/tmp/model_mutation_vrs"))
    parser.add_argument("--limit", type=int, help="Resolve only the first N mutations (probing)")
    args = parser.parse_args(argv)

    rows = collect(args.mutations)
    if args.limit:
        rows = rows[: args.limit]
    print(f"{len(rows)} mutation rows carry a ClinVar expression "
          f"({len({r['humanClinVarMutation'].strip() for r in rows})} distinct)",
          file=sys.stderr)

    reference = Reference(args.reference)
    resolved = resolve_all(rows, reference, Throttle())
    minted = mint(resolved, args.vrsify, args.seqmap, args.reference, args.workdir)

    for row in resolved:
        if row.get("reference_bases"):
            key = (row["chromosome"], row["position"],
                   row["reference_bases"], row["alternate_bases"])
            row["vrs_id"] = minted.get(key, "")

    resolved.sort(key=lambda r: (r["gene_symbol"], r["clinvar_expression"], r["mutation_id"]))
    version = subprocess.run([str(args.vrsify), "--version"], capture_output=True,
                             text=True, check=True).stdout.strip()
    args.output.write_text(
        render(resolved, version, date.today().isoformat()), encoding="utf-8"
    )

    from collections import Counter
    tally = Counter(r["evidence"] for r in resolved)
    with_id = sum(1 for r in resolved if r["vrs_id"])
    distinct = len({r["vrs_id"] for r in resolved if r["vrs_id"]})
    print(f"wrote {args.output}: {len(resolved)} rows, {with_id} with a VRS id "
          f"({distinct} distinct alleles)")
    print("  evidence: " + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    for row in resolved:
        if not row["vrs_id"]:
            print(f"  no digest: {row['clinvar_expression']} -- {row['notes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
