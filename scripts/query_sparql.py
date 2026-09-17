#!/usr/bin/env python3
"""Query the NF-OSI knowledge graph SPARQL endpoint.

Defaults to SPARQL_ENDPOINT_PROD (from .env). Use --dev to query the
local qlever-rdf service at http://localhost:7001 instead, or --endpoint
for any other URL.

Common prefixes (nf, rdfs, owl, biolink, etc. -- see DEFAULT_PREFIXES) are
declared automatically, so most queries don't need any PREFIX lines. Use
--prefix to add one-off namespaces, or --no-default-prefixes to opt out
entirely.

Canned summary queries are available via --canned (see CANNED_QUERIES), for
common questions like "what classes/properties exist" or "how many
instances of each type are there" without writing SPARQL by hand.

Usage:
    python scripts/query_sparql.py "SELECT * WHERE { ?s a nf:Study } LIMIT 10"
    python scripts/query_sparql.py --dev "ASK { ?s ?p ?o }" --format json
    python scripts/query_sparql.py --prefix sh=http://www.w3.org/ns/shacl# "..."
    python scripts/query_sparql.py --canned schema
    python scripts/query_sparql.py --canned shape --class-name Study
    cat query.sparql | python scripts/query_sparql.py
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
DEV_ENDPOINT = "http://localhost:7001"

DEFAULT_PREFIXES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "nf": "http://nf-osi.github.com/terms#",
    "biolink": "https://w3id.org/biolink/vocab/",
    "efo": "http://www.ebi.ac.uk/efo/",
    "obo": "http://purl.obolibrary.org/obo/",
    "prov": "http://www.w3.org/ns/prov#",
    # Imported terms carry NF-OSI usage guidance on skos:scopeNote.
    "skos": "http://www.w3.org/2004/02/skos/core#",
    # Person names live on foaf:name (biolink:Person and nf:Investigator alike),
    # so almost any people question needs this declared.
    "foaf": "http://xmlns.com/foaf/0.1/",
}

FORMAT_ACTIONS = {
    "tsv": "tsv_export",
    "csv": "csv_export",
    "json": None,
}

CLASS_NAME_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*:)?[A-Za-z_][A-Za-z0-9_]*")

# Canned summary queries, selectable with --canned NAME. `extra_prefixes` are
# merged in on top of DEFAULT_PREFIXES (unless --no-default-prefixes is set).
CANNED_QUERIES = {
    "schema": {
        "help": "Classes and properties in the ontology, with label, rdfs:comment (definition), skos:scopeNote (NF-OSI usage guidance on imported terms), domain and range",
        "query": """\
SELECT ?term ?kind ?label ?comment ?scopeNote ?domain ?range WHERE {
  {
    ?term a owl:Class .
    BIND("Class" AS ?kind)
  } UNION {
    ?term a owl:ObjectProperty .
    BIND("ObjectProperty" AS ?kind)
  } UNION {
    ?term a owl:DatatypeProperty .
    BIND("DatatypeProperty" AS ?kind)
  }
  OPTIONAL { ?term rdfs:label ?label }
  # Two documentation slots, kept as separate columns because they mean
  # different things. rdfs:comment is the DEFINITION, present on terms this
  # ontology mints. scopeNote is NF-OSI USAGE GUIDANCE on a term imported from
  # another vocabulary (biolink:, foaf:, prov:, void:) -- we never write to a
  # borrowed term's rdfs:comment, since that slot belongs to whoever defined it.
  # A term normally has one or the other, so an empty column is expected.
  OPTIONAL { ?term rdfs:comment ?comment }
  OPTIONAL { ?term skos:scopeNote ?scopeNote }
  OPTIONAL { ?term rdfs:domain ?domain }
  OPTIONAL { ?term rdfs:range ?range }
} ORDER BY ?kind ?term""",
    },
    "count-by-type": {
        "help": "Instance counts grouped by rdf:type, descending",
        "query": """\
SELECT ?type (COUNT(?s) AS ?count) WHERE {
  ?s a ?type
} GROUP BY ?type ORDER BY DESC(?count)""",
    },
    "predicate-usage": {
        "help": "Predicate usage counts across the whole graph, descending",
        "query": """\
SELECT ?p (COUNT(*) AS ?count) WHERE {
  ?s ?p ?o
} GROUP BY ?p ORDER BY DESC(?count)""",
    },
    "shape": {
        "help": "SHACL shape (properties, cardinalities, datatypes) for a class; requires --class-name",
        "needs_class_name": True,
        "extra_prefixes": {"sh": "http://www.w3.org/ns/shacl#"},
        "query": """\
SELECT ?shape ?label ?comment ?path ?datatype ?nodeKind ?class ?minCount ?maxCount
WHERE {{
  ?shape a sh:NodeShape ;
         sh:targetClass {class_ref} .
  OPTIONAL {{ ?shape rdfs:label ?label }}
  OPTIONAL {{ ?shape rdfs:comment ?comment }}
  OPTIONAL {{
    ?shape sh:property ?prop .
    OPTIONAL {{ ?prop sh:path ?path }}
    OPTIONAL {{ ?prop sh:datatype ?datatype }}
    OPTIONAL {{ ?prop sh:nodeKind ?nodeKind }}
    OPTIONAL {{ ?prop sh:class ?class }}
    OPTIONAL {{ ?prop sh:minCount ?minCount }}
    OPTIONAL {{ ?prop sh:maxCount ?maxCount }}
  }}
}}
ORDER BY ?path""",
    },
    "instances-of-class": {
        "help": "Sample instances of a class with their properties; requires --class-name",
        "needs_class_name": True,
        "query": """\
SELECT ?s ?p ?o WHERE {{
  ?s a {class_ref} ; ?p ?o .
}} LIMIT 50""",
    },
    # --- Somatic variant layer (nf-osi/kg-pipeline#95) ----------------------------
    # These only return rows when the variant layer is included in the index; it is
    # excluded by default (see docs/variant-layer.md). Each corresponds to one of the
    # use cases the issue is meant to unlock, so they are the layer's acceptance test.
    "variant-in-cases": {
        "help": "Has this somatic variant been seen in a case? Specimens, individuals and portal files for a gene + protein change. Params: gene, change",
        "binds": {"gene": "NF1", "change": "p.R1276*"},
        "query": """\
SELECT ?specimen ?individual ?vrsId ?consequence ?file ?assay WHERE {{
  ?obs a nf:VariantObservation ;
       nf:affectedGeneSymbol "{gene}" ;
       nf:aminoacidChange "{change}" ;
       nf:observesVariant ?variant .
  ?variant nf:vrsId ?vrsId .
  OPTIONAL {{ ?obs nf:hasConsequence ?consequence }}
  # The specimen link is OPTIONAL on purpose: an observation whose barcode did not
  # resolve to a portal specimen is still in the graph, and hiding it here would
  # make a coverage gap look like an absence of data.
  OPTIONAL {{
    ?obs nf:fromSpecimen ?specimen .
    OPTIONAL {{ ?obs nf:fromIndividual ?individual }}
    OPTIONAL {{ ?specimen nf:hasFile ?file . OPTIONAL {{ ?file nf:assay ?assay }} }}
  }}
}} ORDER BY ?specimen ?file""",
    },
    "variant-gene-summary": {
        "help": "Gene-level cohort summary: distinct specimens with a protein-altering variant per gene, descending. Answers 'GENE is altered in N of M samples' without leaving the graph",
        "query": """\
SELECT ?symbol ?gene (COUNT(DISTINCT ?specimen) AS ?specimens) (COUNT(DISTINCT ?variant) AS ?alleles)
WHERE {
  # Grouped on the gene NODE, not the symbol string: the source's per-row symbol can be
  # borrowed from a neighbouring locus, so grouping by string splits a gene's count in
  # two. nf:geneSymbol is the HGNC-verified label (see docs/variant-layer.md).
  #
  # `a biolink:Gene` is load-bearing, not decoration: nf:affectedGene carries both the
  # Ensembl gene node and the gene's HGNC IRI, and only the former is typed, so without
  # this line every observation would be counted twice.
  ?gene a biolink:Gene ; nf:geneSymbol ?symbol .
  ?obs nf:affectedGene ?gene ;
       nf:fromSpecimen ?specimen ;
       nf:observesVariant ?variant ;
       nf:hasConsequence ?so .
  # Protein-altering only: missense, stop_gained, stop_lost, frameshift,
  # inframe indel, start_lost. Without this the ranking is dominated by the
  # longest genes, since intronic and synonymous calls scale with gene length.
  VALUES ?so {
    obo:SO_0001583 obo:SO_0001587 obo:SO_0001578 obo:SO_0001589
    obo:SO_0001822 obo:SO_0001821 obo:SO_0002012
  }
} GROUP BY ?symbol ?gene ORDER BY DESC(?specimens) LIMIT 50""",
    },
    "variant-recurrent": {
        "help": "Alleles observed in more than one specimen, i.e. where VRS identity actually collapsed rows across samples",
        "query": """\
SELECT ?vrsId ?gene ?change (COUNT(DISTINCT ?specimen) AS ?specimens) WHERE {
  ?obs nf:observesVariant ?variant ;
       nf:fromSpecimen ?specimen .
  ?variant nf:vrsId ?vrsId .
  OPTIONAL { ?obs nf:affectedGeneSymbol ?gene }
  OPTIONAL { ?obs nf:aminoacidChange ?change }
} GROUP BY ?vrsId ?gene ?change
HAVING (COUNT(DISTINCT ?specimen) > 1)
ORDER BY DESC(?specimens) LIMIT 50""",
    },
    "variant-genotype-cohort": {
        "help": "Cohort builder with a genotype predicate: specimens altered in a gene that also have a given assay in the portal. Params: gene, assay",
        # Values are matched case-insensitively as substrings of the portal's own
        # assay labels, which are hyphenated free text ("RNA-seq", "whole exome
        # sequencing") -- so "rnaseq" would match nothing.
        "binds": {"gene": "NF1", "assay": "RNA-seq"},
        "query": """\
SELECT ?specimen ?individual (GROUP_CONCAT(DISTINCT ?change; separator=", ") AS ?changes)
WHERE {{
  ?obs nf:affectedGeneSymbol "{gene}" ;
       nf:fromSpecimen ?specimen .
  OPTIONAL {{ ?obs nf:fromIndividual ?individual }}
  OPTIONAL {{ ?obs nf:aminoacidChange ?change }}
  ?specimen nf:hasFile ?file .
  ?file nf:assay ?assay .
  FILTER(CONTAINS(LCASE(STR(?assay)), LCASE("{assay}")))
}} GROUP BY ?specimen ?individual ORDER BY ?specimen""",
    },
    "variant-layer-summary": {
        "help": "Size and health of the variant layer: node counts, how many observations reached a specimen, and how many variants are unnormalized or not fully justified. A metric with no matches is absent rather than zero",
        "query": """\
SELECT ?metric (COUNT(DISTINCT ?s) AS ?count) WHERE {
  {
    ?s a biolink:SequenceVariant . BIND("1_variants" AS ?metric)
  } UNION {
    ?s nf:unnormalizedVariant true . BIND("2_variants_unnormalized" AS ?metric)
  } UNION {
    # Present only when false, so its mere presence is the count of bad ones.
    ?s nf:fullyJustified ?j . BIND("3_variants_not_fully_justified" AS ?metric)
  } UNION {
    ?s a nf:VariantObservation . BIND("4_observations" AS ?metric)
  } UNION {
    ?s a nf:VariantObservation ; nf:fromSpecimen ?spec .
    BIND("5_observations_with_specimen" AS ?metric)
  } UNION {
    ?s a nf:VariantObservation ; nf:hasConsequence ?so .
    BIND("6_observations_with_a_consequence" AS ?metric)
  } UNION {
    ?s a nf:Specimen ; nf:hasVariantObservation ?o .
    BIND("7_specimens_with_a_variant" AS ?metric)
  } UNION {
    ?s a nf:Individual . ?o nf:fromIndividual ?s ; a nf:VariantObservation .
    BIND("8_individuals_with_a_variant" AS ?metric)
  } UNION {
    ?s a biolink:Gene . BIND("9_genes" AS ?metric)
  } UNION {
    # `a biolink:Gene` also de-duplicates nf:affectedGene's HGNC object -- see
    # variant-gene-summary above.
    ?s a biolink:Gene . ?o nf:affectedGene ?s .
    BIND("A_genes_with_a_variant" AS ?metric)
  }
} GROUP BY ?metric ORDER BY ?metric""",
    },
}


def build_canned_query(
    name: str, class_name: str | None, binds: dict[str, str] | None = None
) -> tuple[str, dict[str, str]]:
    spec = CANNED_QUERIES[name]
    if spec.get("needs_class_name"):
        if not class_name:
            raise ValueError(f"--canned {name} requires --class-name")
        if not CLASS_NAME_RE.fullmatch(class_name):
            raise ValueError(f"invalid --class-name: {class_name!r}")
        class_ref = class_name if ":" in class_name else f"nf:{class_name}"
        query = spec["query"].format(class_ref=class_ref)
    elif spec.get("binds"):
        # Queries with free-text parameters (a gene symbol, a protein change). Values
        # are interpolated into SPARQL string literals, so quotes and backslashes are
        # escaped rather than passed through -- a value like `p."x` must not be able to
        # close the literal and continue the query.
        supplied = dict(spec["binds"])
        for key, value in (binds or {}).items():
            if key not in supplied:
                raise ValueError(
                    f"--canned {name} takes {', '.join(sorted(supplied))}, not {key!r}"
                )
            supplied[key] = value
        escaped = {
            k: v.replace("\\", "\\\\").replace('"', '\\"')
            for k, v in supplied.items()
        }
        query = spec["query"].format(**escaped)
    else:
        query = spec["query"]
    return query, spec.get("extra_prefixes", {})


def build_query(query: str, prefixes: dict[str, str]) -> str:
    prefix_lines = "\n".join(f"PREFIX {name}: <{uri}>" for name, uri in prefixes.items())
    return f"{prefix_lines}\n{query}" if prefix_lines else query


def parse_prefix_arg(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(f"expected NAME=URI, got {value!r}")
    name, uri = value.split("=", 1)
    return name.strip(), uri.strip()


def main(argv: list[str] | None = None) -> int:
    load_dotenv(REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", nargs="?", help="SPARQL query string; reads stdin if omitted. Ignored if --canned is given.")
    parser.add_argument(
        "--canned", choices=sorted(CANNED_QUERIES), metavar="NAME",
        help="Run a canned summary query instead of a custom one. Choices: " + ", ".join(f"{n} ({s['help']})" for n, s in CANNED_QUERIES.items()),
    )
    parser.add_argument("--class-name", help="Class name for --canned shape/instances-of-class. Bare name defaults to the nf: prefix (e.g. Study -> nf:Study); use a prefixed name (e.g. biolink:Study) for other namespaces.")
    parser.add_argument(
        "--bind", action="append", default=[], type=parse_prefix_arg, metavar="KEY=VALUE",
        help="Set a parameter on a canned query that takes one (repeatable), e.g. "
             "--canned variant-in-cases --bind gene=NF1 --bind change=p.R1276*. Each "
             "canned query's defaults are shown in its --canned help text.",
    )
    parser.add_argument("--dev", action="store_true", help=f"Query the local dev endpoint ({DEV_ENDPOINT}) instead of SPARQL_ENDPOINT_PROD")
    parser.add_argument("--endpoint", help="Query an arbitrary SPARQL endpoint URL instead of --dev/SPARQL_ENDPOINT_PROD")
    parser.add_argument(
        "--prefix", action="append", default=[], type=parse_prefix_arg, metavar="NAME=URI",
        help="Add a custom PREFIX declaration (repeatable), on top of the defaults",
    )
    parser.add_argument("--no-default-prefixes", action="store_true", help="Don't auto-declare the default prefixes (nf, rdfs, owl, ...)")
    parser.add_argument("--format", choices=sorted(FORMAT_ACTIONS), default="tsv", help="Output format (default: tsv). Use json for ASK queries.")
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("SPARQL_TIMEOUT", "30")), help="Request timeout in seconds")
    args = parser.parse_args(argv)

    if args.endpoint:
        endpoint = args.endpoint
    elif args.dev:
        endpoint = DEV_ENDPOINT
    else:
        endpoint = os.environ.get("SPARQL_ENDPOINT_PROD")
        if not endpoint:
            parser.error("SPARQL_ENDPOINT_PROD is not set in .env")

    extra_prefixes = {}
    if args.canned:
        try:
            query, extra_prefixes = build_canned_query(
                args.canned, args.class_name, dict(args.bind)
            )
        except ValueError as e:
            parser.error(str(e))
    else:
        query = args.query if args.query is not None else sys.stdin.read()
        if not query.strip():
            parser.error("no SPARQL query provided")

    prefixes = {} if args.no_default_prefixes else dict(DEFAULT_PREFIXES)
    prefixes.update(extra_prefixes)
    prefixes.update(args.prefix)
    full_query = build_query(query, prefixes)

    params = {"query": full_query}
    action = FORMAT_ACTIONS[args.format]
    if action:
        params["action"] = action

    headers = {}
    auth_token = os.environ.get("SPARQL_AUTH_TOKEN")
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    try:
        r = httpx.post(endpoint, data=params, headers=headers, timeout=args.timeout)
        r.raise_for_status()
    except httpx.TimeoutException:
        print(f"error: query timed out after {args.timeout}s", file=sys.stderr)
        return 1
    except httpx.HTTPStatusError as e:
        print(f"error: SPARQL endpoint returned {e.response.status_code}:\n{e.response.text}", file=sys.stderr)
        return 1
    except httpx.HTTPError as e:
        print(f"error: request failed: {e}", file=sys.stderr)
        return 1

    sys.stdout.write(r.text)
    if not r.text.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
