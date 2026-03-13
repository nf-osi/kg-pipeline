#!/usr/bin/env python3
"""Transform PubTator3 BioC JSON into QLever text index files.

Reads pubtator3/*.json and produces three outputs in qlever_text/:
- wordsfile.tsv — word/entity entries for QLever text index
- docsfile.tsv  — passage text per record
- text_entities.ttl — companion RDF with entity types and labels

See PUBTATOR_USAGE.md for context on the PubTator3 data.
"""

import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import quote


NF = "http://nf-osi.github.com/terms#"

# PubTator3 type -> (rdf_class, class label)
# rdf_class is a CURIE using prefixes declared in write_ttl().
# Most use the nf: prefix; Species reuses obo:NCBITaxon_species directly.
TYPE_CLASSES = {
    "Gene": ("nf:Gene", "Gene"),
    "Disease": ("nf:DiseaseAnnotation", "Disease Annotation"),
    "Chemical": ("nf:Chemical", "Chemical"),
    "Species": ("obo:NCBITaxon_species", "Species"),
    "CellLine": ("nf:CellLine", "Cell Line"),
    "Variant": ("nf:Variant", "Variant"),
}

WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase text and extract alphanumeric tokens."""
    return WORD_RE.findall(text.lower())


def make_entity_iri(infons: dict) -> str | None:
    """Build a canonical IRI from annotation infons, or None to skip."""
    if not infons.get("valid", True) is True:
        return None

    identifier = infons.get("identifier")
    if not identifier or identifier == "-":
        return None

    entity_type = infons.get("type", "")

    if entity_type == "Gene":
        gene_id = str(identifier).split(";")[0].strip()
        if not gene_id:
            return None
        return f"https://www.ncbi.nlm.nih.gov/gene/{gene_id}"

    if entity_type == "Disease":
        sid = str(identifier)
        if sid.startswith("MESH:"):
            return f"http://id.nlm.nih.gov/mesh/{sid[5:]}"
        if sid.startswith("OMIM:"):
            return f"https://omim.org/entry/{sid[5:]}"
        # Other prefixes — try to parse
        if ":" in sid:
            prefix, bare = sid.split(":", 1)
            if prefix == "MESH":
                return f"http://id.nlm.nih.gov/mesh/{bare}"
            if prefix == "OMIM":
                return f"https://omim.org/entry/{bare}"
        return None

    if entity_type == "Chemical":
        sid = str(identifier)
        if sid.startswith("MESH:"):
            return f"http://id.nlm.nih.gov/mesh/{sid[5:]}"
        if ":" in sid:
            prefix, bare = sid.split(":", 1)
            if prefix == "MESH":
                return f"http://id.nlm.nih.gov/mesh/{bare}"
        return None

    if entity_type == "Species":
        return f"http://purl.obolibrary.org/obo/NCBITaxon_{identifier}"

    if entity_type == "CellLine":
        sid = str(identifier)
        if sid.startswith("CVCL:"):
            bare = sid[5:]
        else:
            bare = sid
        return f"https://www.cellosaurus.org/CVCL_{bare}"

    if entity_type == "Variant":
        hgvs = infons.get("hgvs")
        if not hgvs:
            return None
        encoded = quote(str(hgvs), safe="")
        return f"https://www.ncbi.nlm.nih.gov/research/litvar2-api/variant/autocomplete/?query={encoded}"

    return None


def get_entity_label(infons: dict, annotation_text: str) -> str:
    """Get the best available label for an entity."""
    name = infons.get("name", "")
    if name and name != infons.get("identifier", ""):
        return name
    if annotation_text:
        return annotation_text
    return ""


def escape_ttl(s: str) -> str:
    """Escape a string for Turtle literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def write_ttl(
    entities: dict[str, tuple[str, str]],
    output_path: Path,
) -> None:
    """Write companion RDF as Turtle.

    entities: {iri: (entity_type, label)}
    """
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("@prefix owl:  <http://www.w3.org/2002/07/owl#> .\n")
        f.write("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n")
        f.write("@prefix obo:  <http://purl.obolibrary.org/obo/> .\n")
        f.write(f"@prefix nf:   <{NF}> .\n")
        f.write("\n")

        # Entity instances (classes are declared in schema/ontology.ttl)
        for iri in sorted(entities):
            entity_type, label = entities[iri]
            class_info = TYPE_CLASSES.get(entity_type)
            if not class_info:
                continue
            rdf_class = class_info[0]
            f.write(f"<{iri}> a {rdf_class}")
            if label:
                f.write(f' ;\n    rdfs:label "{escape_ttl(label)}"')
            f.write(" .\n")


def passage_score(section_type: str, title_boost: int, abstract_boost: int) -> int:
    """Return score for a passage based on its section type."""
    if section_type == "TITLE":
        return title_boost
    if section_type == "ABSTRACT":
        return abstract_boost
    return 1


def main():
    parser = argparse.ArgumentParser(
        description="Transform PubTator3 BioC JSON into QLever text index files."
    )
    parser.add_argument(
        "--pubtator-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "pubtator3",
        help="Directory with PubTator3 JSON files (default: pubs/pubtator3)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "qlever_text",
        help="Output directory (default: pubs/qlever_text)",
    )
    parser.add_argument(
        "--title-boost",
        type=int,
        default=2,
        help="Score boost for TITLE passages (default: 2)",
    )
    parser.add_argument(
        "--abstract-boost",
        type=int,
        default=2,
        help="Score boost for ABSTRACT passages (default: 2)",
    )
    args = parser.parse_args()

    pub_dir: Path = args.pubtator_dir
    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    words_path = out_dir / "wordsfile.tsv"
    docs_path = out_dir / "docsfile.tsv"
    ttl_path = out_dir / "text_entities.ttl"

    # Collect unique entities for TTL: {iri: (type, label)}
    all_entities: dict[str, tuple[str, str]] = {}

    record_id = 0
    total_words = 0
    total_entity_refs = 0
    skipped_invalid = 0
    skipped_no_id = 0
    skipped_no_iri = 0
    files_processed = 0

    with (
        open(words_path, "w", encoding="utf-8") as wf,
        open(docs_path, "w", encoding="utf-8") as df,
    ):
        for fname in sorted(os.listdir(pub_dir)):
            if not fname.endswith(".json"):
                continue

            with open(pub_dir / fname) as f:
                data = json.load(f)

            files_processed += 1

            for pub in data.get("PubTator3", []):
                pmid = pub.get("pmid")
                if not pmid:
                    continue
                pub_iri = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}"

                for passage in pub.get("passages", []):
                    infons = passage.get("infons", {})
                    section_type = infons.get("section_type", "")

                    # Skip REF sections
                    if section_type == "REF":
                        continue

                    text = passage.get("text", "").strip()
                    if not text:
                        continue

                    score = passage_score(
                        section_type, args.title_boost, args.abstract_boost
                    )
                    rid = str(record_id)
                    record_id += 1

                    # docsfile: record_id \t passage_text
                    df.write(f"{rid}\t{text}\n")

                    # wordsfile: publication IRI as entity
                    wf.write(f"<{pub_iri}>\t1\t{rid}\t{score}\n")
                    total_entity_refs += 1

                    # wordsfile: tokenized words
                    words = tokenize(text)
                    for w in words:
                        wf.write(f"{w}\t0\t{rid}\t{score}\n")
                    total_words += len(words)

                    # wordsfile: bio-entity IRIs (deduplicated per passage)
                    seen_iris: set[str] = set()
                    for ann in passage.get("annotations", []):
                        ann_infons = ann.get("infons", {})

                        # Skip invalid
                        if ann_infons.get("valid") is False:
                            skipped_invalid += 1
                            continue

                        identifier = ann_infons.get("identifier")
                        if not identifier or identifier == "-":
                            skipped_no_id += 1
                            continue

                        iri = make_entity_iri(ann_infons)
                        if not iri:
                            skipped_no_iri += 1
                            continue

                        # Deduplicate within passage
                        if iri in seen_iris:
                            continue
                        seen_iris.add(iri)

                        wf.write(f"<{iri}>\t1\t{rid}\t{score}\n")
                        total_entity_refs += 1

                        # Collect for TTL (keep first seen label)
                        if iri not in all_entities:
                            entity_type = ann_infons.get("type", "")
                            label = get_entity_label(
                                ann_infons, ann.get("text", "")
                            )
                            all_entities[iri] = (entity_type, label)

    # Write companion RDF
    write_ttl(all_entities, ttl_path)

    # Summary
    print(f"Files processed:    {files_processed}")
    print(f"Records (passages): {record_id:,}")
    print(f"Word entries:       {total_words:,}")
    print(f"Entity IRI entries: {total_entity_refs:,}")
    print(f"Unique entities:    {len(all_entities):,}")
    print(f"Skipped (invalid):  {skipped_invalid:,}")
    print(f"Skipped (no id):    {skipped_no_id:,}")
    print(f"Skipped (no IRI):   {skipped_no_iri:,}")
    print()
    print(f"Output:")
    print(f"  {words_path}")
    print(f"  {docs_path}")
    print(f"  {ttl_path}")


if __name__ == "__main__":
    main()
