# Node embedding pipeline for NF KG.
# Prerequisites: pip install pecanpy

PYTHON ?= python
RDF_DIR := data/rdf
LOG_DIR := logs
EMBEDDINGS_DIR := data/embeddings
EDGELIST := $(EMBEDDINGS_DIR)/kg.edgelist
EMBEDDINGS := $(EMBEDDINGS_DIR)/kg.emd
EDGELIST_SCRIPT := scripts/rdf_to_edgelist.py

PECANPY_MODE ?= PreCompFirstOrder
PECANPY_WORKERS ?= 16
PECANPY_DIM ?= 128
PECANPY_WALKLEN ?= 80
PECANPY_NUMWALKS ?= 10
PECANPY_P ?= 1
PECANPY_Q ?= 1

$(EDGELIST): $(EDGELIST_SCRIPT) $(wildcard $(RDF_DIR)/*.ttl)
	@mkdir -p $(EMBEDDINGS_DIR) $(LOG_DIR)
	@echo "Converting RDF to edgelist..."
	@/usr/bin/time -f "  Time: %E elapsed, %U user, %S system" \
		$(PYTHON) $(EDGELIST_SCRIPT) --rdf-dir $(RDF_DIR) --output $@ 2>&1
	@echo "  Output: $@"

edgelist: $(EDGELIST)

$(EMBEDDINGS): $(EDGELIST)
	@echo "Running PecanPy (mode=$(PECANPY_MODE), dim=$(PECANPY_DIM))..."
	@/usr/bin/time -f "  Time: %E elapsed, %U user, %S system" \
		pecanpy --input $< --output $@ \
		--mode $(PECANPY_MODE) \
		--workers $(PECANPY_WORKERS) \
		--dimensions $(PECANPY_DIM) \
		--walk-length $(PECANPY_WALKLEN) \
		--num-walks $(PECANPY_NUMWALKS) \
		--p $(PECANPY_P) \
		--q $(PECANPY_Q) \
		--weighted 2>&1
	@echo "  Output: $@"

embeddings: $(EMBEDDINGS)

clean_embeddings:
	rm -f $(EDGELIST) $(EMBEDDINGS)
