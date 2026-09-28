#!/usr/bin/env python3
"""Run the demo queries against sagebrain (Neptune), where the NF graph and the
shared resources (Open Targets, Reactome) live side by side.

Unlike scripts/query_sparql.py, which talks to a synchronous public/local QLever
endpoint, this script talks to sagebrain's asynchronous query API: submit a job,
get a job_id, poll until complete. Authorization is a Synapse personal access
token in SYNAPSE_AUTH_TOKEN (the caller must be on the Sage Brain team).

sagebrain is append-only and holds every snapshot ever published, so every query
MUST be scoped to explicit named graphs -- an unscoped query answers from the
merge of all snapshots and silently returns duplicated and outdated rows. The
canned queries here are pre-scoped to the pinned graph versions below; re-pin
with --nf-graph / --ot-graph / --reactome-graph when newer snapshots land
(--canned graphs lists what is loaded).

Usage:
    python scripts/query_demo.py --canned graphs
    python scripts/query_demo.py --canned demo2-progression
    python scripts/query_demo.py --canned demo2-screening
    python scripts/query_demo.py --canned demo2-mechanism
    python scripts/query_demo.py --canned demo2-indication
    python scripts/query_demo.py --canned demo2-mechanism --bind gene=SUZ12
    python scripts/query_demo.py "SELECT ... WHERE { GRAPH <urn:...> { ... } }"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

# The prod SPARQL API (API Gateway in front of Neptune). Reads only. The
# authoritative source for this URL is the app-prod-neptune-api stack output;
# override with SAGEBRAIN_QUERY_ENDPOINT or --endpoint if it moves.
DEFAULT_ENDPOINT = "https://vyar2xyj0k.execute-api.us-east-1.amazonaws.com/prod/query"

# Pinned named graphs. sagebrain names program snapshots by ingest date, not by
# the release inside them (opentargets:2026-09-24 *is* Open Targets 26.06 -- the
# release lives on pav:version in the graph's own void:Dataset).
NF_GRAPH = "urn:sagebrain:nf:2026-09-28"
OT_GRAPH = "urn:sagebrain:opentargets:2026-09-24"
REACTOME_GRAPH = "urn:sagebrain:reactome:2026-09-22"

POLL_INTERVAL = 2.5

DEFAULT_PREFIXES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "nf": "http://nf-osi.github.com/terms#",
    "biolink": "https://w3id.org/biolink/vocab/",
    "obo": "http://purl.obolibrary.org/obo/",
    "efo": "http://www.ebi.ac.uk/efo/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    # sagebrain's own namespace. The Reactome direct gene->pathway edge and all
    # of Open Targets' mechanism/stage properties live here, NOT under biolink:
    # -- biolink:participates_in returns 0 rows, silently.
    "sb": "https://w3id.org/synapse/sagebrain#",
    # Each snapshot's provenance manifest (void:triples, pav:version).
    "void": "http://rdfs.org/ns/void#",
    "pav": "http://purl.org/pav/",
}

# Demo 2 (docs/demos/demo-2.md): one patient, genotype to measured drug
# response. The chain runs across three graphs joined purely by IRI:
# identifiers.org/chembl:* for molecules (NF <-> Open Targets),
# identifiers.org/hgnc:* for genes (Open Targets <-> Reactome), and
# EFO/MONDO purls for diseases (nf:tumorClass <-> Open Targets indications).
CANNED_QUERIES = {
    "pinned": {
        "help": "Fast connection check: the three pinned graphs' declared triple counts and release versions, read from each graph's own void:Dataset provenance rather than counted (~2s vs ~1min for `graphs`)",
        "query": """\
SELECT ?g ?triples ?version WHERE {{
  VALUES ?g {{ <{nf_graph}> <{ot_graph}> <{reactome_graph}> }}
  GRAPH ?g {{ ?d void:triples ?triples . OPTIONAL {{ ?d pav:version ?version }} }}
}}""",
    },
    "graphs": {
        "help": "Named graphs currently loaded, with triple counts. The only deliberately unscoped query here: it is how you find out what to scope to",
        "query": """\
SELECT ?g (COUNT(*) AS ?triples)
WHERE {{ GRAPH ?g {{ ?s ?p ?o }} }}
GROUP BY ?g ORDER BY DESC(?g)""",
    },
    "demo2-progression": {
        "help": "Hop 1: driver-panel alleles for one individual across their lesions, with tumour types. The story: the same NF1 allele in four lesions, SUZ12 only in the two MPNSTs. Params: individual",
        "binds": {"individual": "JH-2-002"},
        "query": """\
SELECT ?vrs ?symbol ?change (COUNT(DISTINCT ?specimen) AS ?specimens)
       (GROUP_CONCAT(DISTINCT ?tumorType; separator=" | ") AS ?tumorTypes)
WHERE {{
  GRAPH <{nf_graph}> {{
    VALUES ?symbol {{ "NF1" "NF2" "SUZ12" "EED" "TP53" "CDKN2A" }}
    ?gene a biolink:Gene ; nf:geneSymbol ?symbol .
    ?obs nf:affectedGene ?gene ; nf:observesVariant ?variant ; nf:fromSpecimen ?specimen ;
         nf:fromIndividual ?individual ; nf:hasConsequence ?so .
    VALUES ?so {{
      obo:SO_0001583 obo:SO_0001587 obo:SO_0001578 obo:SO_0001589
      obo:SO_0001822 obo:SO_0001821 obo:SO_0002012
    }}
    FILTER(STRENDS(STR(?individual), "/{individual}"))
    ?variant nf:vrsId ?vrs .
    OPTIONAL {{ ?obs nf:aminoacidChange ?change }}
    OPTIONAL {{ ?specimen nf:hasFile ?f . ?f nf:tumorType ?tumorType }}
  }}
}}
GROUP BY ?vrs ?symbol ?change
ORDER BY DESC(?specimens) ?symbol""",
    },
    "demo2-progression-detail": {
        "help": "Hop 1, per-specimen: one row per allele x specimen for one individual, for the lesion-by-lesion matrix (the aggregate view is demo2-progression). Params: individual",
        "binds": {"individual": "JH-2-002"},
        "query": """\
SELECT DISTINCT ?specimenID ?symbol ?change ?vrs ?tumorType
WHERE {{
  GRAPH <{nf_graph}> {{
    VALUES ?symbol {{ "NF1" "NF2" "SUZ12" "EED" "TP53" "CDKN2A" }}
    ?gene a biolink:Gene ; nf:geneSymbol ?symbol .
    ?obs nf:affectedGene ?gene ; nf:observesVariant ?variant ; nf:fromSpecimen ?specimen ;
         nf:fromIndividual ?individual ; nf:hasConsequence ?so .
    VALUES ?so {{
      obo:SO_0001583 obo:SO_0001587 obo:SO_0001578 obo:SO_0001589
      obo:SO_0001822 obo:SO_0001821 obo:SO_0002012
    }}
    FILTER(STRENDS(STR(?individual), "/{individual}"))
    ?variant nf:vrsId ?vrs .
    ?specimen nf:specimenID ?specimenID .
    OPTIONAL {{ ?obs nf:aminoacidChange ?change }}
    OPTIONAL {{ ?specimen nf:hasFile ?f . ?f nf:tumorType ?tumorType }}
  }}
}} ORDER BY ?symbol ?specimenID""",
    },
    "demo2-screening": {
        "help": "Hop 2: the same individual -> derived specimens -> screening files -> ChEMBL compound IRIs. Params: individual",
        "binds": {"individual": "JH-2-002"},
        "query": """\
SELECT ?compound (SAMPLE(?name) AS ?compoundName)
       (COUNT(DISTINCT ?file) AS ?files)
       (GROUP_CONCAT(DISTINCT ?sid; separator=" | ") AS ?specimens)
WHERE {{
  GRAPH <{nf_graph}> {{
    ?specimen nf:fromIndividual ?individual ; nf:hasFile ?file .
    FILTER(STRENDS(STR(?individual), "/{individual}"))
    ?file nf:compound ?compound .
    OPTIONAL {{ ?file nf:compoundName ?name }}
    OPTIONAL {{ ?file nf:specimenID ?sid }}
  }}
}}
GROUP BY ?compound
ORDER BY DESC(?files)""",
    },
    "demo2-mechanism": {
        "help": "Hop 3, three graphs: screened compound -> mechanism target (Open Targets) -> Reactome pathway shared with the patient's mutated gene. NF1 has no mechanism edge of its own, so the pathway IS the route. Params: individual, gene",
        "binds": {"individual": "JH-2-002", "gene": "NF1"},
        "query": """\
SELECT ?drug ?action ?targetSymbol ?targetType
       (GROUP_CONCAT(DISTINCT ?pathwayLabel; separator=" | ") AS ?sharedPathways)
WHERE {{
  {{
    SELECT DISTINCT ?c WHERE {{
      GRAPH <{nf_graph}> {{
        ?specimen nf:fromIndividual ?individual ; nf:hasFile ?file .
        FILTER(STRENDS(STR(?individual), "/{individual}"))
        ?file nf:compound ?c .
      }}
    }}
  }}
  GRAPH <{ot_graph}> {{
    ?a a biolink:ChemicalAffectsGeneAssociation ;
       biolink:subject ?c ; biolink:object ?target ;
       sb:action_type ?action ; sb:target_type ?targetType .
    ?c rdfs:label ?drug .
    ?target rdfs:label ?targetSymbol .
  }}
  # OPTIONAL: a compound whose target shares no specific pathway with the
  # patient's gene keeps its mechanism row with an empty ?sharedPathways --
  # that emptiness is the honest answer (e.g. ribociclib: CDK4/6 is not in
  # NF1's Reactome pathways; its rationale is the combination, not the map).
  OPTIONAL {{
    GRAPH <{reactome_graph}> {{
      # sb:participates_in, not biolink: (which is valid SPARQL and returns
      # nothing). Associations are transitively closed up the pathway tree,
      # so every signalling gene "shares" the roots -- exclude them, or
      # digoxin reads as pathway-linked to {gene} via "Disease".
      ?patientGene rdfs:label "{gene}" ; sb:participates_in ?pw .
      ?target sb:participates_in ?pw .
      ?pw rdfs:label ?pathwayLabel .
      FILTER(?pathwayLabel NOT IN ("Disease", "Signal Transduction",
        "Diseases of signal transduction by growth factor receptors and second messengers"))
    }}
  }}
}}
GROUP BY ?drug ?action ?targetSymbol ?targetType
ORDER BY ?drug ?targetSymbol""",
    },
    "demo2-indication": {
        "help": "Hop 4: screened compound -> indication (Open Targets) -> the patient's own tumour classes, joined on the EFO/MONDO IRI nf:tumorClass carries. Stage is per drug-disease pair, never per drug. Params: individual",
        "binds": {"individual": "JH-2-002"},
        "query": """\
SELECT DISTINCT ?drug ?disease ?stage
WHERE {{
  # Both sides collapsed to DISTINCT sets first: the raw file x file join is
  # a cross product large enough to blow the worker's 60s budget.
  {{
    SELECT DISTINCT ?c WHERE {{
      GRAPH <{nf_graph}> {{
        ?specimen nf:fromIndividual ?individual ; nf:hasFile ?file .
        FILTER(STRENDS(STR(?individual), "/{individual}"))
        ?file nf:compound ?c .
      }}
    }}
  }}
  {{
    SELECT DISTINCT ?tumorClass WHERE {{
      GRAPH <{nf_graph}> {{
        ?patientFile nf:individualID ?iid ; nf:tumorClass ?tumorClass .
        FILTER(STR(?iid) = "{individual}")
      }}
    }}
  }}
  GRAPH <{ot_graph}> {{
    # treats_or_applied_or_studied_to_treat, deliberately: most rows are
    # trials, not approvals. max_clinical_stage belongs to this edge.
    ?a a biolink:ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation ;
       biolink:subject ?c ; biolink:object ?tumorClass ;
       sb:max_clinical_stage ?stage .
    ?c rdfs:label ?drug .
    ?tumorClass rdfs:label ?disease .
  }}
}}
ORDER BY ?drug ?disease""",
    },
}


def build_canned_query(name: str, binds: dict[str, str], graphs: dict[str, str]) -> str:
    spec = CANNED_QUERIES[name]
    supplied = dict(spec.get("binds", {}))
    for key, value in binds.items():
        if key not in supplied:
            accepted = sorted(supplied) or ["(none)"]
            raise ValueError(f"--canned {name} takes {', '.join(accepted)}, not {key!r}")
        supplied[key] = value
    # Values land inside SPARQL string literals; escape so a quote cannot
    # close the literal and continue the query.
    escaped = {
        k: v.replace("\\", "\\\\").replace('"', '\\"') for k, v in supplied.items()
    }
    return spec["query"].format(**escaped, **graphs)


def build_query(query: str, prefixes: dict[str, str]) -> str:
    prefix_lines = "\n".join(f"PREFIX {name}: <{uri}>" for name, uri in prefixes.items())
    return f"{prefix_lines}\n{query}" if prefix_lines else query


def parse_prefix_arg(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(f"expected NAME=URI, got {value!r}")
    name, uri = value.split("=", 1)
    return name.strip(), uri.strip()


def submit_and_poll(endpoint: str, query: str, token: str, deadline: float) -> dict:
    """Submit to the async API and poll until complete/error. Returns the SPARQL
    JSON results object. A failed query still comes back HTTP 200 -- failure is
    in the status field."""
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Source": "kg-pipeline/query_demo.py",
    }
    r = httpx.post(
        endpoint,
        json={"query": query},
        headers={**headers, "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    job_id = r.json()["job_id"]

    stop = time.monotonic() + deadline
    while True:
        time.sleep(POLL_INTERVAL)
        poll = httpx.get(f"{endpoint}/{job_id}", headers=headers, timeout=30)
        poll.raise_for_status()
        body = poll.json()
        status = body.get("status")
        if status == "complete":
            # "results" is a STRING holding SPARQL JSON; parse it a second time.
            return json.loads(body["results"])
        if status == "error":
            raise RuntimeError(f"query failed: {body.get('error', '(no detail)')}")
        if time.monotonic() > stop:
            raise TimeoutError(f"job {job_id} still {status} after {deadline:.0f}s")


def render_tsv(results: dict) -> str:
    cols = results["head"]["vars"]
    lines = ["\t".join(cols)]
    for row in results["results"]["bindings"]:
        lines.append("\t".join(row.get(c, {}).get("value", "") for c in cols))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    load_dotenv(REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("query", nargs="?", help="SPARQL query string; reads stdin if omitted. Ignored if --canned is given. Scope it with GRAPH yourself.")
    parser.add_argument(
        "--canned", choices=sorted(CANNED_QUERIES), metavar="NAME",
        help="Run a canned demo query. Choices: " + "; ".join(f"{n} ({s['help']})" for n, s in sorted(CANNED_QUERIES.items())),
    )
    parser.add_argument(
        "--bind", action="append", default=[], type=parse_prefix_arg, metavar="KEY=VALUE",
        help="Set a parameter on a canned query (repeatable), e.g. --bind individual=JH-2-002",
    )
    parser.add_argument("--endpoint", default=os.environ.get("SAGEBRAIN_QUERY_ENDPOINT", DEFAULT_ENDPOINT), help="Async query API URL (default: SAGEBRAIN_QUERY_ENDPOINT or the known prod URL)")
    parser.add_argument("--nf-graph", default=NF_GRAPH, help=f"NF named graph (default: {NF_GRAPH})")
    parser.add_argument("--ot-graph", default=OT_GRAPH, help=f"Open Targets named graph (default: {OT_GRAPH})")
    parser.add_argument("--reactome-graph", default=REACTOME_GRAPH, help=f"Reactome named graph (default: {REACTOME_GRAPH})")
    parser.add_argument(
        "--prefix", action="append", default=[], type=parse_prefix_arg, metavar="NAME=URI",
        help="Add a custom PREFIX declaration (repeatable), on top of the defaults",
    )
    parser.add_argument("--format", choices=["tsv", "json"], default="tsv", help="Output format (default: tsv)")
    parser.add_argument("--timeout", type=float, default=90, help="Give up polling after this many seconds (default: 90; the worker itself times out at 60)")
    args = parser.parse_args(argv)

    token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if not token:
        parser.error("SYNAPSE_AUTH_TOKEN is not set (a Synapse PAT; the account must be on the Sage Brain team)")

    graphs = {
        "nf_graph": args.nf_graph,
        "ot_graph": args.ot_graph,
        "reactome_graph": args.reactome_graph,
    }
    if args.canned:
        try:
            query = build_canned_query(args.canned, dict(args.bind), graphs)
        except ValueError as e:
            parser.error(str(e))
    else:
        query = args.query if args.query is not None else sys.stdin.read()
        if not query.strip():
            parser.error("no SPARQL query provided")
        if not re.search(r"\bGRAPH\b", query, re.IGNORECASE):
            print(
                "warning: query has no GRAPH clause -- sagebrain merges every "
                "snapshot ever loaded, so unscoped results are duplicated and stale",
                file=sys.stderr,
            )

    prefixes = dict(DEFAULT_PREFIXES)
    prefixes.update(args.prefix)
    full_query = build_query(query, prefixes)

    try:
        results = submit_and_poll(args.endpoint, full_query, token, args.timeout)
    except (httpx.HTTPError, RuntimeError, TimeoutError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.format == "json":
        json.dump(results, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_tsv(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
