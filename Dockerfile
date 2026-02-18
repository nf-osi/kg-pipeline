# Multi-stage build: index RDF data with QLever, then serve.
#
# The build context should contain:
#   data/rdf/*.ttl       — materialized RDF triples
#   schema/ontology.ttl  — OWL ontology
#
# See .dockerignore for what gets included.

FROM adfreiburg/qlever AS indexer

USER root
RUN mkdir -p /input/rdf /input/schema /index \
    && chown -R qlever:qlever /input /index
USER qlever

COPY --chown=qlever:qlever schema/ontology.ttl /input/schema/
COPY --chown=qlever:qlever data/rdf/ /input/rdf/

RUN cat /input/schema/ontology.ttl /input/rdf/*.ttl \
    | qlever-index -F ttl -f - -i /index/kg --parse-parallel false

# --- final image: just the server + pre-built index ---
FROM adfreiburg/qlever

USER root
RUN mkdir -p /index && chown qlever:qlever /index
USER qlever

COPY --from=indexer --chown=qlever:qlever /index /index

EXPOSE 7001
ENTRYPOINT ["qlever-server"]
CMD ["-i", "/index/kg", "-p", "7001"]
