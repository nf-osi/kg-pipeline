# Multi-stage build: index RDF data with QLever, then serve.
#
# The build context should contain:
#   data/rdf/*.ttl       — materialized RDF triples
#   schema/ontology.ttl  — OWL ontology
#   schema/shapes.ttl    — SHACL shapes
#
# Optional text index files for the plus-text build:
#   pubs/qlever_text/text_entities.ttl
#   pubs/qlever_text/wordsfile.tsv
#   pubs/qlever_text/docsfile.tsv
#
# See .dockerignore for what gets included.

FROM adfreiburg/qlever AS indexer-base

USER root
RUN mkdir -p /input/rdf /input/schema /input/text /index \
    && chown -R qlever:qlever /input /index
USER qlever

COPY --chown=qlever:qlever schema/ontology.ttl schema/shapes.ttl /input/schema/
COPY --chown=qlever:qlever data/rdf/ /input/rdf/

FROM indexer-base AS indexer-text
COPY --chown=qlever:qlever pubs/qlever_text/ /input/text/
RUN cat /input/schema/ontology.ttl \
        /input/schema/shapes.ttl \
        /input/text/text_entities.ttl \
        /input/rdf/*.ttl \
      | qlever-index -F ttl -f - -i /index/kg -p false \
          -w /input/text/wordsfile.tsv \
          -d /input/text/docsfile.tsv

FROM indexer-base AS indexer-rdf
RUN cat /input/schema/ontology.ttl /input/schema/shapes.ttl /input/rdf/*.ttl \
      | qlever-index -F ttl -f - -i /index/kg -p false

# --- final image: just the server + pre-built index ---
FROM adfreiburg/qlever AS runtime-base

USER root
RUN mkdir -p /index && chown qlever:qlever /index
USER qlever

EXPOSE 7001

FROM runtime-base AS runtime-text
COPY --from=indexer-text --chown=qlever:qlever /index /index
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:7001/ \
      -H "Accept: application/sparql-results+json" \
      --data-urlencode "query=ASK { ?s ?p ?o }" || exit 1
ENTRYPOINT ["qlever-server"]
CMD ["-i", "/index/kg", "-p", "7001", "-t"]

FROM runtime-base AS runtime-rdf
COPY --from=indexer-rdf --chown=qlever:qlever /index /index
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:7001/ \
      -H "Accept: application/sparql-results+json" \
      --data-urlencode "query=ASK { ?s ?p ?o }" || exit 1
ENTRYPOINT ["qlever-server"]
CMD ["-i", "/index/kg", "-p", "7001"]
