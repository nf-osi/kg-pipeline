# Multi-stage build: index RDF data with QLever, then serve.
#
# The build context should contain:
#   data/rdf/*.ttl       — materialized RDF triples
#   schema/ontology.ttl  — OWL ontology
#   schema/shapes.ttl    — SHACL shapes
#
# Optional somatic variant layer (nf-osi/kg-pipeline#95), in a SUBdirectory so the
# data/rdf/*.ttl globs below miss it — publishing it is a separate, explicit choice:
#   data/rdf/variants/*.ttl
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

# --- variant-layer build: core graph PLUS the somatic variant layer ---
# The variant layer is a proof of concept and is meant to be droppable in a later
# release, so it gets its own image target rather than being folded into the default
# one. Build it explicitly:
#     docker build --target runtime-variants -t kg:variants .
# If data/rdf/variants/ is empty (the layer is opt-in at ingest too, via
# KG_INCLUDE_VARIANTS) this target produces the same index as indexer-rdf.
FROM indexer-base AS indexer-variants
RUN cat /input/schema/ontology.ttl /input/schema/shapes.ttl /input/rdf/*.ttl \
        $(ls /input/rdf/variants/*.ttl 2>/dev/null) \
      | qlever-index -F ttl -f - -i /index/kg -p false

# --- final image: just the server + pre-built index ---
FROM adfreiburg/qlever AS runtime-base

USER root
RUN mkdir -p /index && chown qlever:qlever /index

# Install nginx for health-aware proxying on the public service port.
RUN apt-get update && apt-get install -y nginx && rm -rf /var/lib/apt/lists/*

# Add nginx config and entrypoint wrapper
COPY --chown=root:root nginx.conf /nginx.conf
COPY --chown=root:root entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER qlever

EXPOSE 7001

FROM runtime-base AS runtime-text
COPY --from=indexer-text --chown=qlever:qlever /index /index
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:7001/healthz || exit 1
ENTRYPOINT ["/entrypoint.sh"]
CMD ["qlever-server", "-i", "/index/kg", "-p", "7002", "-t"]

FROM runtime-base AS runtime-rdf
COPY --from=indexer-rdf --chown=qlever:qlever /index /index
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:7001/healthz || exit 1
ENTRYPOINT ["/entrypoint.sh"]
CMD ["qlever-server", "-i", "/index/kg", "-p", "7002"]

FROM runtime-base AS runtime-variants
COPY --from=indexer-variants --chown=qlever:qlever /index /index
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:7001/healthz || exit 1
ENTRYPOINT ["/entrypoint.sh"]
CMD ["qlever-server", "-i", "/index/kg", "-p", "7002"]
