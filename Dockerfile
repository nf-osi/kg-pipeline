# Multi-stage build: index RDF data with QLever, then serve.
#
# The build context should contain:
#   data/rdf/*.ttl       — materialized RDF triples
#   schema/ontology.ttl  — OWL ontology
#
# Optional text index (set TEXT_INDEX=1 to enable):
#   pubs/qlever_text/text_entities.ttl
#   pubs/qlever_text/wordsfile.tsv
#   pubs/qlever_text/docsfile.tsv
#
# See .dockerignore for what gets included.

FROM adfreiburg/qlever AS indexer

ARG TEXT_INDEX=0

USER root
RUN mkdir -p /input/rdf /input/schema /input/text /index \
    && chown -R qlever:qlever /input /index
USER qlever

COPY --chown=qlever:qlever schema/ontology.ttl /input/schema/
COPY --chown=qlever:qlever data/rdf/ /input/rdf/

# Copy text index files if TEXT_INDEX is enabled
RUN if [ "$TEXT_INDEX" = "1" ]; then \
      echo "Text index build enabled"; \
    else \
      echo "RDF-only build (no text index)"; \
    fi

COPY --chown=qlever:qlever pubs/qlever_text/ /input/text/

RUN if [ "$TEXT_INDEX" = "1" ]; then \
      cat /input/schema/ontology.ttl \
          /input/text/text_entities.ttl \
          /input/rdf/*.ttl \
        | qlever-index -F ttl -f - -i /index/kg --parse-parallel false \
            -w /input/text/wordsfile.tsv \
            -d /input/text/docsfile.tsv; \
    else \
      cat /input/schema/ontology.ttl /input/rdf/*.ttl \
        | qlever-index -F ttl -f - -i /index/kg --parse-parallel false; \
    fi

# --- final image: just the server + pre-built index ---
FROM adfreiburg/qlever

ARG TEXT_INDEX=0

USER root
RUN mkdir -p /index && chown qlever:qlever /index
USER qlever

COPY --from=indexer --chown=qlever:qlever /index /index

EXPOSE 7001
ENTRYPOINT ["qlever-server"]
# Use -t flag for text search when TEXT_INDEX is enabled
CMD if [ "$TEXT_INDEX" = "1" ]; then \
      exec qlever-server -i /index/kg -p 7001 -t; \
    else \
      exec qlever-server -i /index/kg -p 7001; \
    fi
