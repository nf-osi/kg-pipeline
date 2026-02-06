# Triple generation pipeline for NF graph POC.

JAVA ?= java
PYTHON ?= python
CSV_DIR := data/csv
RDF_DIR := data/rdf
LOG_DIR := logs

# =============================================================================
# RML Pipeline
# =============================================================================
# Prerequisites:
#   Maintain mappings/rml/*.rml.ttl mappings manually
#   RMLMapper JAR in tools/
#
# Usage:
#   make                     # Generate all RDF
#   make portal_studies      # Generate studies RDF (RML + SPARQL transform)
#   make portal_mutations    # Generate mutations RDF

RML_DIR := mappings/rml
RMLMAPPER_JAR := tools/rmlmapper-8.1.0.jar
RML_FUNCTION_FILES := tools/functions_grel.ttl tools/grel_java_mapping.ttl
RMLMAPPER_FLAGS := $(foreach file,$(RML_FUNCTION_FILES),-f $(file))

# Lookup and transform dependencies
LOOKUP_FILE := mappings/data_lookup.ttl
TRANSFORM_SCRIPT := scripts/transform_iris.py

all: portal_studies portal_files

# =============================================================================
# Portal Studies
# =============================================================================

# Step 1: RML mapping (CSV -> raw RDF with literal dataTypes)
$(RDF_DIR)/portal_studies_raw.ttl: $(RML_DIR)/portal_studies.rml.ttl $(CSV_DIR)/portal_studies.csv $(RMLMAPPER_JAR) $(RML_FUNCTION_FILES)
	@mkdir -p $(dir $@) $(LOG_DIR)
	@echo "Running RMLMapper for portal_studies..."
	@/usr/bin/time -f "  Time: %E elapsed, %U user, %S system" sh -c '$(JAVA) -jar $(RMLMAPPER_JAR) $(RMLMAPPER_FLAGS) -m $< -s turtle -o $@ 2> $(LOG_DIR)/portal_studies_rml.log' 2>&1
	@echo "  Output: $@"

rml_portal_studies: $(RDF_DIR)/portal_studies_raw.ttl

# Step 2: IRI transform (literal dataTypes -> IRIs)
$(RDF_DIR)/portal_studies.ttl: $(RDF_DIR)/portal_studies_raw.ttl $(LOOKUP_FILE) $(TRANSFORM_SCRIPT)
	@echo "Running IRI transform for portal_studies..."
	@/usr/bin/time -f "  Time: %E elapsed, %U user, %S system" $(PYTHON) $(TRANSFORM_SCRIPT) --input $< --output $@ --lookup $(LOOKUP_FILE) 2>&1
	@echo "  Output: $@"

portal_studies: $(RDF_DIR)/portal_studies.ttl

# =============================================================================
# Portal Files
# =============================================================================

$(RDF_DIR)/portal_files_raw.ttl: $(RML_DIR)/portal_files.rml.ttl $(CSV_DIR)/portal_files.csv $(RMLMAPPER_JAR) $(RML_FUNCTION_FILES)
	@mkdir -p $(dir $@) $(LOG_DIR)
	@echo "Running RMLMapper for portal_files..."
	@/usr/bin/time -f "  Time: %E elapsed, %U user, %S system" sh -c '$(JAVA) -jar $(RMLMAPPER_JAR) $(RMLMAPPER_FLAGS) -m $< -s turtle -o $@ 2> $(LOG_DIR)/portal_files_rml.log' 2>&1
	@echo "  Output: $@"

rml_portal_files: $(RDF_DIR)/portal_files_raw.ttl

# Step 2: IRI transform (literal dataTypes -> IRIs)
$(RDF_DIR)/portal_files.ttl: $(RDF_DIR)/portal_files_raw.ttl $(LOOKUP_FILE) $(TRANSFORM_SCRIPT)
	@echo "Running IRI transform for portal_files..."
	@/usr/bin/time -f "  Time: %E elapsed, %U user, %S system" $(PYTHON) $(TRANSFORM_SCRIPT) --input $< --output $@ --lookup $(LOOKUP_FILE) 2>&1
	@echo "  Output: $@"

portal_files: $(RDF_DIR)/portal_files.ttl

# =============================================================================
# Clean
# =============================================================================

clean:
	rm -f $(RDF_DIR)/portal_studies_raw.ttl $(RDF_DIR)/portal_studies.ttl
	rm -f $(RDF_DIR)/portal_files_raw.ttl $(RDF_DIR)/portal_files.ttl
	rm -f $(LOG_DIR)/*.log
