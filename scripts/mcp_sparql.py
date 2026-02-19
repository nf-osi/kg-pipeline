"""MCP server exposing the NF knowledge graph via SPARQL."""

import os

import httpx
from fastmcp import FastMCP

ENDPOINT = os.environ.get("SPARQL_ENDPOINT", "http://localhost:7001")

mcp = FastMCP(
    "nf-kg",
    instructions=(
        "SPARQL interface for the NF-OSI knowledge graph. "
        "Use get_schema first to discover classes and properties, "
        "then use sparql_query to run queries. "
        "The default namespace is nf: <http://nf-osi.github.com/terms#>."
    ),
)


@mcp.tool()
def sparql_query(query: str) -> str:
    """Execute a SPARQL query against the NF knowledge graph.

    Returns results as tab-separated values (TSV).
    The graph uses prefix nf: <http://nf-osi.github.com/terms#>.
    """
    r = httpx.get(
        ENDPOINT,
        params={"query": query, "action": "tsv_export"},
        timeout=30,
    )
    r.raise_for_status()
    return r.text


@mcp.tool()
def get_schema() -> str:
    """Return all classes and properties defined in the NF ontology.

    Use this to discover the graph structure before writing queries.
    """
    q = """\
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

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
} ORDER BY ?kind ?term"""
    r = httpx.get(
        ENDPOINT,
        params={"query": q, "action": "tsv_export"},
        timeout=30,
    )
    r.raise_for_status()
    return r.text


@mcp.tool()
def count_by_type() -> str:
    """Return instance counts grouped by rdf:type.

    Quick overview of what data is in the graph.
    """
    q = """\
SELECT ?type (COUNT(?s) AS ?count) WHERE {
  ?s a ?type
} GROUP BY ?type ORDER BY DESC(?count)"""
    r = httpx.get(
        ENDPOINT,
        params={"query": q, "action": "tsv_export"},
        timeout=30,
    )
    r.raise_for_status()
    return r.text


if __name__ == "__main__":
    mcp.run()
