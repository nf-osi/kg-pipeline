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
        "help": "Classes and properties defined in the ontology, with labels/comments/domain/range",
        "query": """\
SELECT ?term ?kind ?label ?comment ?domain ?range WHERE {
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
  OPTIONAL { ?term rdfs:comment ?comment }
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
}


def build_canned_query(name: str, class_name: str | None) -> tuple[str, dict[str, str]]:
    spec = CANNED_QUERIES[name]
    if spec.get("needs_class_name"):
        if not class_name:
            raise ValueError(f"--canned {name} requires --class-name")
        if not CLASS_NAME_RE.fullmatch(class_name):
            raise ValueError(f"invalid --class-name: {class_name!r}")
        class_ref = class_name if ":" in class_name else f"nf:{class_name}"
        query = spec["query"].format(class_ref=class_ref)
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
            query, extra_prefixes = build_canned_query(args.canned, args.class_name)
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
