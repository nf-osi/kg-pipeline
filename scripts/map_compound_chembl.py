#!/usr/bin/env python3
"""Build `mappings/compound_chembl.tsv`: portal compound strings -> ChEMBL molecules.

## Why this exists

`nf:compoundName` and `nf:experimentalCondition` are two free-text fields holding the
same kind of value under different conventions, with dose prefixes, plate codes,
combination arms, vehicle controls and treatment durations mixed in. `SELUMETINIB` and
`AZD-6244` are the same drug and never join; `Ribociclib;Trametinib` and
`Trametinib;Ribociclib` are the same experiment and read as two.

No external source fixes that -- it needs a parse and a curation decision. This script
produces the crosswalk so the decision can be made once, reviewed as a diff, and pushed
back upstream as file annotations rather than re-derived by every consumer.

## Portal-wide, with the demo's strings flagged for closer review

Every file carrying a `compoundName` or `experimentalCondition` is in scope, because the
upstream annotation is worth doing once across the portal rather than per demo.

But the strings on demo 2's files are the ones going upstream first and getting read by a
human line by line, so they are marked `in_demo=yes`, carry a `demo_files` count, and sort
to the TOP of the file. Review effort follows the sort order; the long tail sits below it.
`--demo-specimen` redefines that set, and `--specimen` / `--individual` restrict the whole
scope if a narrower pass is wanted.

## Resolution rules, in order

1. **Split a list into arms -- but only if EVERY arm resolves.**
   Two characters separate arms in these fields. A comma is what the portal records
   (`Dasatinib,Simvastatin`), and `|` is what exports built before the ingest stopped
   comma-splitting contain (`CUDC-907|Panobinostat`). Both are handled, so this script
   reads either vintage of `files.csv` without a flag.

   The comma is also a character *inside* chemical names, so the split is attempted and
   kept only if every arm fully resolves. "Any arm resolves" is not enough and the
   difference is not academic: `Acridine, 9-phenoxy-` is one compound, and the lax rule
   happily returns ACRIDINE -- a real molecule, and the wrong one. `SALINOMYCIN, SODIUM`
   fails the same way. Requiring all arms costs a couple of recoverable values
   (`10|20uM Ataluren` loses its dose range) and those stay visible as unresolved,
   which is the trade this file makes everywhere.

   A pre-fix export can also contain **systematic names whose commas became pipes**:
   `11H-Benzo[a]carbazole-1|4-dione|7|11-dimethyl-` was
   `11H-Benzo[a]carbazole-1,4-dione, 7,11-dimethyl-`. Those are classified
   `shredded_name` -- a corrupted value, not an unknown compound. That detection is
   deliberately pipe-only and transitional: the same string spelled with commas is
   correct, and the class should disappear once every export post-dates the ingest fix.
2. **Split combinations** within an arm on `;`, ` + ` and ` plus `. Each component becomes
   its own row, so a two-drug arm is two annotations rather than one unparseable string.
   ` + ` needs the spaces: `(+)-Camptothecin` must not split.
3. **Strip a leading dose**: `100 nM CUDC-907`, `100nM fimepinostat`, `0.0125% DMSO`.
4. **Try both sides of an `=`.** The portal uses that separator in two opposite ways --
   `212= trametinib` puts a plate code before the compound, `doxycycline= 300ng/ml` puts
   the compound before a dose. Rather than guess which side is which, both are looked
   up and whichever resolves wins. Data-driven, so a third convention does not need new code.
5. **Try a trailing parenthetical both ways**: `ARQ 197 (Tivantinib)` resolves on the
   parenthetical, `Bosutinib (SKI-606)` on the stem. 64 components carry one.
6. **Exact match** on the case-folded label index, then a
   **punctuation-insensitive retry**: `CUDC907` finds `CUDC-907`.

## Ambiguity is refused, not guessed

A label can name several molecules, and the wrong pick is not a near miss -- it is a
different drug. Measured on this demo's strings, taking the first candidate resolves
`Olaparib` to PARPI, `Doxorubicin` to DAUNORUBICIN HYDROCHLORIDE, `Erlotinib` to
ICOTINIB and `Sirolimus` to EVEROLIMUS. All four are wrong and all four look plausible
in a table.

So candidates are ranked by match kind -- a molecule's preferred name beats the same
string appearing in another molecule's synonym list -- and if more than one candidate
survives at the best kind, the row is written with `method=ambiguous`, no ChEMBL id, and
the candidates in `notes` for a curator to settle. Refusing is the point.

Unresolved strings are kept with an empty `chembl_id`, the same keep-don't-drop rule the
variant layer uses: a string that does not resolve is a curation finding, and dropping it
would hide the field-hygiene problem this file exists to document.

Usage:
    python scripts/map_compound_chembl.py                  # portal-wide; 1,805 strings
    python scripts/map_compound_chembl.py --individual JH-2-002 --files-out reports/annot.tsv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_FILES = REPO_ROOT / "data" / "csv" / "files.csv"
DEFAULT_OUTPUT = REPO_ROOT / "mappings" / "compound_chembl.tsv"
#: Exported by `python -m opentargets.export_label_index` in sagebrain-tap, which owns
#: Open Targets ingestion. Staged here rather than fetched: the cross-repo handoff is
#: not settled yet, so the path is explicit and the digest is recorded in the header.
DEFAULT_LABEL_INDEX = REPO_ROOT / "data" / "reference" / "chembl_labels.tsv"

COMPOUND_FIELDS = ("compoundName", "experimentalCondition")

#: Demo 2's scope: the cell line derived from individual JH-2-002 and its imaging series.
DEMO_SPECIMENS = ("JH-2-002-CL", "JH-2-002-CL-MIC")

#: A molecule's own preferred name is better evidence than the same string turning up in
#: some other molecule's synonym list. This ordering is what keeps `Olaparib` off PARPI.
KIND_RANK = {"preferred_name": 0, "synonym": 1, "trade_name": 2}

#: Co-administration separators observed in the portal. ` + ` requires its spaces so
#: `(+)-Camptothecin` and `(S)-(+)-...` are not torn apart.
COMBINATION_SPLIT = re.compile(r";|\s\+\s|\bplus\b", re.IGNORECASE)

#: Arm separators. The comma is the portal's own; `|` appears in exports built before
#: the ingest stopped comma-splitting these fields, where it stands for a comma. Both
#: are accepted so this script reads either vintage -- see rule 1.
ARM_SPLIT = re.compile(r"[|,]")

#: Pipe only. A pre-fix export encodes a name's internal commas as pipes, so an
#: unbalanced part is evidence of corruption; the same string spelled with commas is
#: simply the correct value. See `looks_shredded`.
SHREDDED_DELIMITER = "|"

#: A leading concentration, e.g. `100 nM CUDC-907` or `0.0125% DMSO`.
LEADING_DOSE = re.compile(
    r"^[0-9]+(?:\.[0-9]+)?\s*(?:nM|uM|µM|mM|M|nmol|umol|ng/ml|ug/ml|mg/ml|mg/kg|%)\s+",
    re.IGNORECASE)

#: A trailing parenthetical, `ARQ 197 (Tivantinib)`.
TRAILING_PAREN = re.compile(r"^(?P<stem>.+?)\s*\((?P<inner>[^()]+)\)\s*$")

#: Strings that describe how long an exposure lasted rather than what it was. These are
#: not compounds and the actionable upstream fix is to move them out of the field, so
#: they are classified rather than left in the undifferentiated unmatched pile.
DURATION = re.compile(r"\b(treated for|hours?|hrs?|days?|minutes?|mins?)\b", re.IGNORECASE)

#: Values that mark a control arm. `nodrug=` and a zero dose both mean no exposure.
VEHICLES = ("dmso", "vehicle", "untreated", "saline", "no drug", "nodrug")
VEHICLE_WORD = re.compile(
    r"(?<![a-z0-9])(" + "|".join(v.replace(" ", r"\s+") for v in VEHICLES) + r")(?![a-z0-9])",
    re.IGNORECASE)
ZERO_DOSE = re.compile(r"=\s*0\s*(ng/ml|ug/ml|um|nm|mm|mg/ml|%)?\s*$", re.IGNORECASE)

#: Methods this script derives. Anything else in the column is human-authored and
#: preserved on regeneration -- the `cbioportal_sample_specimen.tsv` convention.
DERIVED_METHODS = {"exact", "parsed", "ambiguous", "unmatched"}

COLUMNS = [
    "in_demo",          # yes when a demo-2 file carries this value; these sort first
    "demo_files",       # how many of `files` are demo-2 files
    "raw_value",        # the string exactly as the portal holds it
    "source_field",     # compoundName | experimentalCondition
    "files",            # files portal-wide carrying this value in this field
    "value_class",      # compound | combination | control | not_a_compound | unresolved
    "arm",              # 1-based index of the `|`-separated arm this row belongs to
    "component",        # the single-compound token this row resolves
    "chembl_id",
    "molecule_name",    # Open Targets preferred name, for eyeballing the match
    "match_kind",       # preferred_name | synonym | trade_name
    "method",           # see DERIVED_METHODS, or `manual`
    "combination_key",  # sorted ChEMBL ids for the whole raw_value
    "notes",
]


def flatten(value: str) -> str:
    """Collapse tab, newline and carriage return to spaces.

    Not paranoia: one `experimentalCondition` value in the portal is a four-line mouse
    genotype note with embedded newlines. Written unflattened it splits one TSV record
    across four lines, and the fragments then read back as rows with a blank `method`,
    which `read_manual_rows` treats as human-authored and would append to the file on
    every subsequent run. Flattening on write keeps the file one-record-per-line so
    `cut` and `awk` read it correctly too.
    """
    return re.sub(r"[\t\r\n]+", " ", value or "").strip()


def normalise_punctuation(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


@dataclass
class LabelIndex:
    """Case-folded label -> candidate molecules, from the Open Targets export."""

    by_label: dict[str, list[dict]]
    by_squashed: dict[str, list[dict]]
    digest: str
    release: str

    @classmethod
    def load(cls, path: Path) -> "LabelIndex":
        path = Path(path)
        if not path.exists():
            raise SystemExit(
                f"No ChEMBL label index at {path}.\n"
                "Generate it in the sagebrain-tap repo and stage it here:\n"
                "  python -m opentargets.export_label_index --release 26.06\n"
                f"  cp opentargets/26.06/data/exports/chembl_labels.tsv {path}\n"
                "Or pass --label-index."
            )
        by_label: dict[str, list[dict]] = defaultdict(list)
        by_squashed: dict[str, list[dict]] = defaultdict(list)
        release = "unknown"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with open(path, newline="", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("#"):
                    if "Open Targets Platform" in line:
                        release = line.rstrip().split()[-1]
                    continue
                parts = line.rstrip("\n").split("\t")
                if not parts or parts[0] == "label":
                    continue
                label, folded, kind, _source, chembl, name, drug_type, _amb = parts
                entry = {"label": label, "kind": kind, "chembl": chembl,
                         "name": name, "drug_type": drug_type}
                by_label[folded].append(entry)
                by_squashed[normalise_punctuation(folded)].append(entry)
        if not by_label:
            raise SystemExit(f"{path} contained no label rows.")
        return cls(dict(by_label), dict(by_squashed), digest, release)

    @staticmethod
    def worth_looking_up(token: str) -> bool:
        """Reject fragments before they can match something.

        Splitting `10|20uM Ataluren` leaves a bare `10`, and ChEMBL has molecules whose
        synonym lists contain bare numbers -- so a fragment matches, ambiguously, and
        lands in the file as a decision a curator has to read and dismiss. A compound
        name is not one or two characters and is not pure digits.
        """
        stripped = token.strip()
        return len(stripped) > 2 and not stripped.isdigit()

    def best(self, token: str) -> tuple[dict | None, list[dict], bool]:
        """``(hit, candidates, needed_parse)``; hit is None when unresolved.

        Ranked by match kind, and a tie at the best kind returns no hit -- see the
        module docstring on why guessing is worse than refusing here.
        """
        token = token.strip()
        if not self.worth_looking_up(token):
            return None, [], False
        for needed_parse, bucket, key in (
            (False, self.by_label, token.casefold()),
            (True, self.by_squashed, normalise_punctuation(token)),
        ):
            hits = bucket.get(key, [])
            if not hits:
                continue
            best_rank = min(KIND_RANK[h["kind"]] for h in hits)
            top = [h for h in hits if KIND_RANK[h["kind"]] == best_rank]
            # Several labels can squash to one key; dedupe on the molecule.
            unique = {h["chembl"]: h for h in top}
            return (next(iter(unique.values())) if len(unique) == 1 else None), top, needed_parse
        return None, [], False


def looks_shredded(raw: str) -> bool:
    """Whether `|` appears to have cut through one name rather than separated values.

    Two signals, both taken from the real values:

    * A part whose brackets do not balance. Checked PER PART, not across the whole
      string -- `11H-Indolo[3|2-c]quinolin-9-amine|...` balances globally because the
      `[` and the `]` are both present, just on opposite sides of a delimiter that
      should not be there. That is precisely the tell.
    * A part that is bare digits, as in `1|2|4-Dithiazol-3-amine|...`.

    A genuine list of compound names has neither.
    """
    if SHREDDED_DELIMITER not in raw:
        return False
    for part in raw.split(SHREDDED_DELIMITER):
        stripped = part.strip()
        if stripped.isdigit():
            return True
        if stripped.count("[") != stripped.count("]"):
            return True
        if stripped.count("(") != stripped.count(")"):
            return True
    return False


def split_components(raw: str) -> list[str]:
    return [part.strip() for part in COMBINATION_SPLIT.split(raw) if part.strip()]


def candidate_tokens(component: str) -> list[str]:
    """Every form of a component worth looking up, strongest first.

    Ordered so the least-altered form wins: an exact hit on the component as written
    beats one obtained by stripping a dose, which beats one from a parenthetical.
    """
    tokens = [component]
    without_dose = LEADING_DOSE.sub("", component).strip()
    if without_dose and without_dose != component:
        tokens.append(without_dose)
    for base in list(tokens):
        if "=" in base:
            tokens.extend(side.strip() for side in base.split("=") if side.strip())
    for base in list(tokens):
        match = TRAILING_PAREN.match(base)
        if match:
            # Both ways round: the portal writes `Bosutinib (SKI-606)` with the
            # resolvable name outside the parentheses and `ARQ 197 (Tivantinib)` with
            # it inside, and nothing in the string says which.
            tokens.append(match.group("stem").strip())
            tokens.append(match.group("inner").strip())
    seen, ordered = set(), []
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


@dataclass
class Resolution:
    component: str
    hit: dict | None
    candidates: list[dict]
    method: str
    matched_token: str = ""
    note: str = ""


def resolve_component(component: str, index: LabelIndex) -> Resolution:
    ambiguous: Resolution | None = None
    for token in candidate_tokens(component):
        hit, candidates, needed_parse = index.best(token)
        if hit:
            parsed = needed_parse or token != component
            note = ""
            if token != component:
                note = f"parsed {component!r} -> {token!r}"
            elif needed_parse:
                note = f"punctuation-insensitive match to {hit['label']!r}"
            return Resolution(component, hit, candidates,
                              "parsed" if parsed else "exact", token, note)
        if candidates and ambiguous is None:
            names = ", ".join(f"{c['chembl']}/{c['name']}" for c in candidates[:6])
            ambiguous = Resolution(
                component, None, candidates, "ambiguous", token,
                f"{len(candidates)} molecules share this label at the same match "
                f"strength; a curator must choose: {names}")
    if ambiguous:
        return ambiguous
    return Resolution(component, None, [], "unmatched", "", "")


def classify(raw: str, resolutions: list[Resolution], arms: int) -> tuple[str, str]:
    """``(value_class, note)`` for the raw string as a whole."""
    resolved = [r for r in resolutions if r.hit]
    lowered = raw.casefold()
    if not resolved and looks_shredded(raw):
        return "shredded_name", (
            "the '|' multi-value delimiter appears to have replaced commas inside one "
            "systematic name; the value is corrupted rather than merely unrecognised, "
            "and the upstream fix is to restore the original name")
    if ZERO_DOSE.search(raw):
        return "control", ("zero-dose arm; the compound named is the series agent, "
                           "not an exposure")
    # Word containment, not equality: the portal writes `Vehicle Control`, `DMSO
    # control` and `Untreated` for the same thing, and an exact-match test sends
    # `Vehicle Control` off to be resolved as a compound instead -- where it matches
    # SODIUM CHLORIDE, ambiguously, as a decision nobody should have to make.
    if VEHICLE_WORD.search(raw):
        return "control", "vehicle or untreated control"
    if lowered.startswith("nodrug"):
        return "control", "explicit no-drug arm"
    if not resolved and DURATION.search(raw):
        return "not_a_compound", ("describes exposure duration, not a compound; upstream "
                                  "fix is to move this out of the compound field")
    if not resolved:
        return "unresolved", ""
    if arms > 1:
        return "arm_list", f"{arms} separately-dosed arms in one field value"
    return ("combination" if len(resolved) > 1 else "compound"), ""


def read_manual_rows(path: Path) -> list[dict]:
    """Preserve human-authored rows across regeneration."""
    if not path.exists():
        return []
    manual = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(
                (l for l in handle if not l.startswith("#")), delimiter="\t"):
            method = (row.get("method") or "").strip()
            if method in DERIVED_METHODS:
                continue
            # A row with no method AND no mapping is not a hand edit, it is debris --
            # a malformed line, or a fragment of one. Preserving it would let the file
            # grow garbage on every run, so a manual row has to actually say something.
            if not method and not (row.get("chembl_id") or "").strip():
                continue
            manual.append(row)
    return manual


def collect_strings(files_csv: Path, specimens: set[str] | None,
                    individuals: set[str] | None,
                    demo_specimens: set[str]) -> tuple[dict, dict, dict, dict]:
    """Scan the file table once.

    Returns ``(counts, demo_counts, file_ids, totals)`` keyed by ``(raw, field)``.
    `demo_counts` is the subset of files that are demo-2 files, which is what drives
    the `in_demo` flag and the review ordering.
    """
    csv.field_size_limit(10 ** 7)
    counts: Counter = Counter()
    demo_counts: Counter = Counter()
    file_ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    scanned = with_value = demo_with_value = 0
    with open(files_csv, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if specimens is not None and (row.get("specimenID") or "") not in specimens:
                continue
            if individuals is not None and (row.get("individualID") or "") not in individuals:
                continue
            scanned += 1
            is_demo = (row.get("specimenID") or "") in demo_specimens
            carried = False
            for field_name in COMPOUND_FIELDS:
                value = (row.get(field_name) or "").strip()
                if not value:
                    continue
                carried = True
                counts[(value, field_name)] += 1
                file_ids[(value, field_name)].append(row.get("id") or "")
                if is_demo:
                    demo_counts[(value, field_name)] += 1
            if carried:
                with_value += 1
                if is_demo:
                    demo_with_value += 1
    totals = {"scanned": scanned, "files_with_value": with_value,
              "demo_files_with_value": demo_with_value}
    return dict(counts), dict(demo_counts), dict(file_ids), totals


def build_rows(counts: dict, demo_counts: dict, index: LabelIndex) -> list[dict]:
    rows: list[dict] = []
    # Demo strings first, then by how many files carry the value. Review effort is
    # meant to follow the file's own order, so the ordering is the prioritisation.
    ordering = sorted(
        counts.items(),
        key=lambda kv: (0 if demo_counts.get(kv[0]) else 1, -kv[1], kv[0][0], kv[0][1]))
    for (raw, field_name), file_count in ordering:
        # Attempt the arm split, keep it only if EVERY arm fully resolves -- rule 1.
        split_arms = [a.strip() for a in ARM_SPLIT.split(raw) if a.strip()]
        arms: list[list[Resolution]] = []
        if len(split_arms) > 1:
            attempt = [[resolve_component(c, index) for c in split_components(arm)]
                       for arm in split_arms]
            if all(all(r.hit for r in arm) for arm in attempt):
                arms = attempt
        if not arms:
            arms = [[resolve_component(c, index) for c in split_components(raw)]]

        flat = [r for arm in arms for r in arm]
        value_class, class_note = classify(raw, flat, len(arms))
        for arm_index, arm in enumerate(arms, start=1):
            arm_ids = sorted({r.hit["chembl"] for r in arm if r.hit})
            # Per arm, not per raw value: `mocetinostat + INK128|mocetinostat + rapamycin`
            # is two different two-drug combinations, not one four-drug one.
            combination_key = "+".join(arm_ids) if len(arm_ids) > 1 else ""
            for resolution in arm:
                note = "; ".join(n for n in (class_note, resolution.note) if n)
                rows.append({
                    "arm": str(arm_index),
                    "in_demo": "yes" if demo_counts.get((raw, field_name)) else "no",
                    "demo_files": str(demo_counts.get((raw, field_name), 0)),
                    "raw_value": raw,
                    "source_field": field_name,
                    "files": str(file_count),
                    "value_class": value_class,
                    "component": resolution.component,
                    "chembl_id": resolution.hit["chembl"] if resolution.hit else "",
                    "molecule_name": resolution.hit["name"] if resolution.hit else "",
                    "match_kind": resolution.hit["kind"] if resolution.hit else "",
                    "method": resolution.method,
                    "combination_key": combination_key,
                    "notes": note,
                })
    return rows


def write_mapping(path: Path, rows: list[dict], manual: list[dict],
                  index: LabelIndex, scope: str, stats: dict) -> None:
    header = [
        "# Portal compound strings -> ChEMBL molecules.",
        "# Regenerate with scripts/map_compound_chembl.py; rows whose `method` is not one",
        f"# of ({', '.join(sorted(DERIVED_METHODS))}) are treated as human-authored and",
        "# preserved on rerun -- use method=manual for hand fixes.",
        "#",
        f"# scope: {scope}",
        f"# label index: Open Targets Platform {index.release}, "
        f"sha256 {index.digest[:16]}...",
        "#",
        "# One row per (raw_value, source_field, component): a combination arm becomes one",
        "# row per drug. method=ambiguous means the label names several molecules at equal",
        "# match strength and this file deliberately does NOT choose -- see `notes`.",
        "# Unresolved strings are kept with an empty chembl_id rather than dropped.",
        "#",
        "# ROWS WITH in_demo=yes SORT FIRST and are the review priority: they are the",
        "# strings on demo 2's files, which are the ones being annotated upstream first.",
        "# Everything below them is the portal-wide tail, resolved by the same rules but",
        "# not yet read line by line.",
        "#",
        f"# {stats['strings']} distinct strings over {stats['files_with_value']} files "
        f"carrying a value: {stats['resolved_strings']} fully resolved, "
        f"{stats['partial']} partly, {stats['unresolved_strings']} not at all.",
        f"# demo subset: {stats['demo_strings']} strings over "
        f"{stats['demo_files_with_value']} files, {stats['demo_resolved']} fully resolved.",
    ]
    ordered = rows + [
        {c: (m.get(c) or "") for c in COLUMNS} for m in manual
    ]
    # Atomic replace, and a lock, for the same reason the cBioPortal crosswalk has
    # them: two concurrent regenerations must not interleave into one file.
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.close(fd)
        with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent),
                                         newline="", encoding="utf-8") as tmp:
            for line in header:
                tmp.write(line + "\n")
            writer = csv.DictWriter(tmp, fieldnames=COLUMNS, delimiter="\t",
                                    lineterminator="\n", extrasaction="ignore")
            writer.writeheader()
            writer.writerows({c: flatten(str(row.get(c, ""))) for c in COLUMNS}
                             for row in ordered)
            temp_name = tmp.name
        os.replace(temp_name, str(path))
    finally:
        os.unlink(str(lock))


def write_file_sheet(path: Path, rows: list[dict], file_ids: dict) -> int:
    """Per-file expansion, for pushing annotations upstream.

    Not checked in: it is derived from the mapping plus the current file table, and it
    is the file table that changes. The mapping is the reviewable artifact.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["file_id", "source_field", "raw_value", "chembl_id",
                         "molecule_name", "value_class", "method"])
        for row in rows:
            for file_id in file_ids.get((row["raw_value"], row["source_field"]), []):
                writer.writerow([file_id, row["source_field"], flatten(row["raw_value"]),
                                 row["chembl_id"], row["molecule_name"],
                                 row["value_class"], row["method"]])
                written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--files-csv", type=Path, default=DEFAULT_FILES)
    parser.add_argument("--label-index", type=Path, default=DEFAULT_LABEL_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--demo-specimen", action="append", default=None,
                        help="Specimens whose strings are flagged in_demo=yes and sorted "
                             f"first (default: {', '.join(DEMO_SPECIMENS)})")
    parser.add_argument("--specimen", action="append", default=None,
                        help="Restrict the whole scope to these specimenIDs")
    parser.add_argument("--individual", action="append", default=None,
                        help="Restrict the whole scope to these individualIDs")
    parser.add_argument("--files-out", type=Path, default=None,
                        help="Also write a per-file annotation sheet for upstream use")
    args = parser.parse_args()

    demo_specimens = set(args.demo_specimen or DEMO_SPECIMENS)
    if args.individual:
        specimens, individuals = None, set(args.individual)
        scope = f"individualID in ({', '.join(sorted(individuals))})"
    elif args.specimen:
        specimens, individuals = set(args.specimen), None
        scope = f"specimenID in ({', '.join(sorted(specimens))})"
    else:
        specimens = individuals = None
        scope = "all portal files carrying compoundName or experimentalCondition"

    index = LabelIndex.load(args.label_index)
    print(f"label index: Open Targets {index.release}, "
          f"{len(index.by_label):,} folded labels", file=sys.stderr)

    counts, demo_counts, file_ids, totals = collect_strings(
        args.files_csv, specimens, individuals, demo_specimens)
    if not counts:
        raise SystemExit(f"No files matched {scope}. Check --specimen/--individual.")
    rows = build_rows(counts, demo_counts, index)

    by_value: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        by_value[(row["raw_value"], row["source_field"])].append(row)
    fully = sum(1 for rs in by_value.values() if all(r["chembl_id"] for r in rs))
    none_ = sum(1 for rs in by_value.values() if not any(r["chembl_id"] for r in rs))
    demo_values = [rs for rs in by_value.values() if rs[0]["in_demo"] == "yes"]
    stats = {"strings": len(by_value), "resolved_strings": fully,
             "unresolved_strings": none_, "partial": len(by_value) - fully - none_,
             "demo_strings": len(demo_values),
             "demo_resolved": sum(1 for rs in demo_values
                                  if all(r["chembl_id"] for r in rs)),
             **totals}

    manual = read_manual_rows(args.output)
    write_mapping(args.output, rows, manual, index, scope, stats)

    methods = Counter(r["method"] for r in rows)
    classes = Counter(rs[0]["value_class"] for rs in by_value.values())
    annotated = sum(int(rs[0]["files"]) for rs in by_value.values()
                    if any(r["chembl_id"] for r in rs))
    print(f"scope: {scope}", file=sys.stderr)
    print(f"  {totals['scanned']:,} files scanned, "
          f"{totals['files_with_value']:,} carry a compound string", file=sys.stderr)
    print(f"  {len(by_value):,} distinct strings -> {len(rows):,} rows "
          f"({fully:,} fully resolved, {stats['partial']} partly, {none_:,} not at all)",
          file=sys.stderr)
    print(f"  demo subset (in_demo=yes, sorted first): {stats['demo_strings']} strings "
          f"over {totals['demo_files_with_value']} files, "
          f"{stats['demo_resolved']} fully resolved", file=sys.stderr)
    print(f"  methods: {dict(methods)}", file=sys.stderr)
    print(f"  value classes: {dict(classes)}", file=sys.stderr)
    print(f"  distinct molecules: "
          f"{len({r['chembl_id'] for r in rows if r['chembl_id']})}", file=sys.stderr)
    print(f"  field values carrying a ChEMBL id reach {annotated:,} file-field values",
          file=sys.stderr)
    if manual:
        print(f"  preserved {len(manual)} human-authored row(s)", file=sys.stderr)
    print(f"  -> {args.output}", file=sys.stderr)

    if args.files_out:
        written = write_file_sheet(args.files_out, rows, file_ids)
        print(f"  per-file annotation sheet: {written:,} rows -> {args.files_out}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
