#!/usr/bin/env python3
"""Download portal tables from Synapse and emit raw + processed CSV exports.

The raw files are untouched Synapse exports for archival/debugging, while the
processed CSVs flatten to pipe-delimited lists, coerce numeric
columns so downstream mapping jobs see consistent values, etc. The SELECT clauses are
defined as constants so column order and naming stay stable even if the upstream
Synapse schemas evolve."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import synapseclient
import yaml

STUDIES_SELECT = """
studyId as studyId,
studyName as studyName,
summary as summary,
initiative as initiative,
studyLeads as studyLeads,
institutions as institutions,
manifestation as manifestation,
diseaseFocus as diseaseFocus,
studyStatus as studyStatus,
dataStatus as dataStatus,
fundingAgency as fundingAgency,
accessRequirements as accessRequirements,
acknowledgementStatements as acknowledgementStatements,
dataType as dataType,
relatedStudies as relatedStudies,
studyFileviewId as studyFileviewId,
grantDOI as grantDOI
"""

FILES_SELECT = """
id as id,
name as name,
studyId as studyId,
assay as assay,
platform as platform,
resourceType as resourceType,
dataType as dataType,
dataSubtype as dataSubtype,
fileFormat as fileFormat,
individualID as individualID,
diagnosis as diagnosis,
nf1Genotype as nf1Genotype,
nf2Genotype as nf2Genotype,
sex as sex,
species as species,
specimenID as specimenID,
cellType as cellType,
tissue as tissue,
tumorType as tumorType,
fundingAgency as fundingAgency,
progressReportNumber as reportMilestone,
compoundName as compoundName,
experimentalCondition as experimentalCondition,
modelSystemName as modelSystemName,
createdBy as createdBy,
modifiedBy as modifiedBy
"""

# MUST USE mutationDetailsId as mutationId
MUTATIONS_SELECT = """
mutationDetailsId as mutationId,
humanClinVarMutation as humanClinVarMutation,
alleleType as alleleType,
affectedGeneSymbol as affectedGeneSymbol,
mutationMethod as mutationMethod,
externalMutationID as externalMutationID,
affectedGeneName as affectedGeneName,
sequenceVariation as sequenceVariation,
chromosome as chromosome,
proteinVariation as proteinVariation,
animalModelMutation as animalModelMutation,
mutationType as mutationType
"""

GENETIC_REAGENTS_SELECT = """
geneticReagentId as geneticReagentId,
vectorType as vectorType,
insertEntrezId as insertEntrezId,
insertName as insertName,
insertSpecies as insertSpecies,
insertSize as insertSize,
cloningMethod as cloningMethod,
copyNumber as copyNumber,
nTerminalTag as nTerminalTag,
cTerminalTag as cTerminalTag,
totalSize as totalSize,
vectorBackbone as vectorBackbone,
backboneSize as backboneSize,
promoter as promoter,
bacterialResistance as bacterialResistance,
growthTemp as growthTemp,
growthStrain as growthStrain,
selectableMarker as selectableMarker,
"5primer" as fivePrimer,
"3primer" as threePrimer,
"5primeCloningSite" as fivePrimeCloningSite,
"3primeCloningSite" as threePrimeCloningSite,
"5primeSiteDestroyed" as fivePrimeSiteDestroyed,
"3primeSiteDestroyed" as threePrimeSiteDestroyed,
gRNAshRNASequence as gRNAshRNASequence,
hazardous as hazardous
"""

ANIMAL_MODELS_SELECT = """
animalModelId as animalModelId,
donorId as donorId,
transplantationDonorId as transplantationDonorId,
backgroundStrain as backgroundStrain,
backgroundSubstrain as backgroundSubstrain,
strainNomenclature as strainNomenclature,
animalModelOfManifestation as animalModelOfManifestation,
animalModelGeneticDisorder as animalModelGeneticDisorder,
transplantationType as transplantationType,
animalState as animalState,
generation as generation
"""

CELL_LINES_SELECT = """
cellLineId as cellLineId,
donorId as donorId,
originYear as originYear,
organ as organ,
strProfile as strProfile,
tissue as tissue,
cellLineManifestation as cellLineManifestation,
resistance as resistance,
cellLineCategory as cellLineCategory,
contaminatedMisidentified as contaminatedMisidentified,
cellLineGeneticDisorder as cellLineGeneticDisorder,
populationDoublingTime as populationDoublingTime
"""

DONORS_SELECT = """
donorId as donorId,
parentDonorId as parentDonorId,
species as species,
race as race,
sex as sex,
age as age,
transplantationDonorId as transplantationDonorId
"""

ANTIBODIES_SELECT = """
antibodyId as antibodyId,
uniprotId as uniprotId,
cloneId as cloneId,
reactiveSpecies as reactiveSpecies,
hostOrganism as hostOrganism,
conjugate as conjugate,
clonality as clonality,
targetAntigen as targetAntigen
"""

DEVELOPMENT_SELECT = """
developmentId as developmentId,
resourceId as resourceId,
investigatorId as investigatorId,
publicationId as publicationId,
funderId as funderId
"""

FUNDERS_SELECT = """
funderId as funderId,
funderName as funderName
"""

INVESTIGATORS_SELECT = """
investigatorId as investigatorId,
investigatorSynapseId as investigatorSynapseId,
orcid as orcid,
institution as institution,
investigatorName as investigatorName
"""

PUBLICATIONS_SELECT = """
publicationId as publicationId,
doi as doi,
pmid as pmid,
abstract as abstract,
journal as journal,
publicationDate as publicationDate,
citation as citation,
publicationDateUnix as publicationDateUnix,
authors as authors,
publicationTitle as publicationTitle
"""

DONOR_TOOL_SELECT = """
donorId as donorId,
resourceId as resourceId
"""

MUTATION_MODEL_SELECT = """
mutationDetailsId as mutationId,
animalModelId as animalModelId,
cellLineId as cellLineId
"""

BIOBANKS_SELECT = """
biobankId as biobankId,
resourceId as resourceId,
diseaseType as diseaseType,
biobankURL as biobankURL,
biobankName as biobankName,
specimenPreparationMethod as specimenPreparationMethod,
specimenType as specimenType,
tumorType as tumorType,
specimenFormat as specimenFormat,
specimenTissueType as specimenTissueType,
contact as contact
"""

OBSERVATIONS_SELECT = """
observationId as observationId,
resourceId as resourceId,
publicationId as publicationId,
observationSubmitterName as observationSubmitterName,
synapseId as synapseId,
observationText as observationText,
observationType as observationType,
observationPhase as observationPhase,
observationTime as observationTime,
observationTimeUnits as observationTimeUnits,
reliabilityRating as reliabilityRating,
easeOfUseRating as easeOfUseRating,
observationLink as observationLink
"""

RESOURCES_SELECT = """
resourceId as resourceId,
geneticReagentId as geneticReagentId,
antibodyId as antibodyId,
cellLineId as cellLineId,
animalModelId as animalModelId,
biobankId as biobankId,
usageRequirements as usageRequirements,
resourceName as resourceName,
resourceType as resourceType,
synonyms as synonyms,
dateModified as dateModified,
rrid as rrid,
description as description,
dateAdded as dateAdded,
howToAcquire as howToAcquire
"""

# Short name aliases for convenience
TABLE_ALIASES = {
    "study": "studies",
    "file": "files",
    "mutation": "mutations",
    "reagent": "genetic_reagents",
    "animal": "animal_models",
    "cell": "cell_lines",
    "donor": "donors",
    "antibody": "antibodies",
    "resource": "resources",
    "observation": "observations",
    "dev": "development",
    "funder": "funders",
    "investigator": "investigators",
    "publication": "publications",
    "donor_tool": "donor_tool",
    "mutation_model": "mutation_model",
    "biobank": "biobanks",
}

TABLES: Dict[str, Dict[str, Any]] = {
    "studies": {
        "synapse_id": "syn52694652",
        "csv_path": Path("data/csv/studies.csv"),
        "raw_filename": "studies_raw.csv",
        "select_clause": STUDIES_SELECT,
        "columns": [
            {"target": "studyId", "source": "studyId", "type": "iri", "transform": "synapse_id"},
            {"target": "studyName", "source": "studyName", "type": "text"},
            {"target": "summary", "source": "summary", "type": "text"},
            {"target": "initiative", "source": "initiative", "type": "text"},
            {"target": "studyLeads", "source": "studyLeads", "type": "text+", "transform": "string_list"},
            {"target": "institutions", "source": "institutions", "type": "text+", "transform": "string_list"},
            {"target": "manifestation", "source": "manifestation", "type": "text+", "transform": "string_list"},
            {"target": "diseaseFocus", "source": "diseaseFocus", "type": "text+", "transform": "string_list"},
            {"target": "studyStatus", "source": "studyStatus", "type": "text"},
            {"target": "dataStatus", "source": "dataStatus", "type": "text"},
            {"target": "fundingAgency", "source": "fundingAgency", "type": "text+", "transform": "string_list"},
            {"target": "accessRequirements", "source": "accessRequirements", "type": "text"},
            {
                "target": "acknowledgementStatements",
                "source": "acknowledgementStatements",
                "type": "text",
            },
            {"target": "dataType", "source": "dataType", "type": "text+", "transform": "string_list"},
            {"target": "relatedStudies", "source": "relatedStudies", "type": "iri+", "transform": "synapse_id_list"},
            {"target": "studyFileviewId", "source": "studyFileviewId", "type": "iri", "transform": "synapse_id"},
            {"target": "grantDOI", "source": "grantDOI", "type": "iri+", "transform": "iri_list"},
        ],
    },
    "files": {
        "synapse_id": "syn16858331",
        "csv_path": Path("data/csv/files.csv"),
        "raw_filename": "files_raw.csv",
        "select_clause": FILES_SELECT,
        "columns": [
            {"target": "id", "source": "id", "type": "iri", "transform": "synapse_id"},
            {"target": "name", "source": "name", "type": "text"},
            {"target": "studyId", "source": "studyId", "type": "iri", "transform": "synapse_id"},
            {"target": "assay", "source": "assay", "type": "text"},
            {"target": "platform", "source": "platform", "type": "text"},
            {"target": "resourceType", "source": "resourceType", "type": "text"},
            {"target": "dataType", "source": "dataType", "type": "text"},
            {"target": "dataSubtype", "source": "dataSubtype", "type": "text"},
            {"target": "fileFormat", "source": "fileFormat", "type": "text"},
            {"target": "individualID", "source": "individualID", "type": "text+", "transform": "string_list"},
            {"target": "diagnosis", "source": "diagnosis", "type": "text+", "transform": "string_list"},
            {"target": "nf1Genotype", "source": "nf1Genotype", "type": "text+", "transform": "string_list"},
            {"target": "nf2Genotype", "source": "nf2Genotype", "type": "text+", "transform": "string_list"},
            {"target": "sex", "source": "sex", "type": "text"},
            {"target": "species", "source": "species", "type": "text"},
            {"target": "specimenID", "source": "specimenID", "type": "text+", "transform": "string_list"},
            {"target": "cellType", "source": "cellType", "type": "text+", "transform": "string_list"},
            {"target": "tissue", "source": "tissue", "type": "text+", "transform": "string_list"},
            {"target": "tumorType", "source": "tumorType", "type": "text+", "transform": "string_list"},
            {"target": "fundingAgency", "source": "fundingAgency", "type": "text+", "transform": "string_list"},
            {
                "target": "reportMilestone",
                "source": "progressReportNumber",
                "type": "text",
                "transform": "number",
            },
            {"target": "compoundName", "source": "compoundName", "type": "text+", "transform": "string_list"},
            {
                "target": "experimentalCondition",
                "source": "experimentalCondition",
                "type": "text+",
                "transform": "string_list",
            },
            {"target": "modelSystemName", "source": "modelSystemName", "type": "text+", "transform": "string_list"},
        ],
    },
    "mutations": {
        "synapse_id": "syn26486835",
        "csv_path": Path("data/csv/mutations.csv"),
        "raw_filename": "mutations_raw.csv",
        "select_clause": MUTATIONS_SELECT,
        "columns": [
            {"target": "mutationId", "source": "mutationId", "type": "iri"},
            {"target": "humanClinVarMutation", "source": "humanClinVarMutation", "type": "text+", "transform": "string_list"},
            {"target": "alleleType", "source": "alleleType", "type": "text+", "transform": "string_list"},
            {"target": "affectedGeneSymbol", "source": "affectedGeneSymbol", "type": "text"},
            {"target": "mutationMethod", "source": "mutationMethod", "type": "text+", "transform": "string_list"},
            {"target": "externalMutationID", "source": "externalMutationID", "type": "iri"},
            {"target": "affectedGeneName", "source": "affectedGeneName", "type": "text"},
            {"target": "sequenceVariation", "source": "sequenceVariation", "type": "text"},
            {"target": "chromosome", "source": "chromosome", "type": "text"},
            {"target": "proteinVariation", "source": "proteinVariation", "type": "text"},
            {"target": "animalModelMutation", "source": "animalModelMutation", "type": "text"},
            {"target": "mutationType", "source": "mutationType", "type": "text+", "transform": "string_list"},
        ],
    },
    "genetic_reagents": {
        "synapse_id": "syn26486832",
        "csv_path": Path("data/csv/genetic_reagents.csv"),
        "raw_filename": "genetic_reagents_raw.csv",
        "select_clause": GENETIC_REAGENTS_SELECT,
        "columns": [
            {"target": "geneticReagentId", "source": "geneticReagentId", "type": "iri"},
            {"target": "vectorType", "source": "vectorType", "type": "text+", "transform": "string_list"},
            {"target": "insertEntrezId", "source": "insertEntrezId", "type": "text"},
            {"target": "insertName", "source": "insertName", "type": "text"},
            {"target": "insertSpecies", "source": "insertSpecies", "type": "text+", "transform": "string_list"},
            {"target": "insertSize", "source": "insertSize", "type": "text"},
            {"target": "cloningMethod", "source": "cloningMethod", "type": "text"},
            {"target": "copyNumber", "source": "copyNumber", "type": "text"},
            {"target": "nTerminalTag", "source": "nTerminalTag", "type": "text"},
            {"target": "cTerminalTag", "source": "cTerminalTag", "type": "text"},
            {"target": "totalSize", "source": "totalSize", "type": "text"},
            {"target": "vectorBackbone", "source": "vectorBackbone", "type": "text"},
            {"target": "backboneSize", "source": "backboneSize", "type": "text"},
            {"target": "promoter", "source": "promoter", "type": "text"},
            {"target": "bacterialResistance", "source": "bacterialResistance", "type": "text"},
            {"target": "growthTemp", "source": "growthTemp", "type": "text"},
            {"target": "growthStrain", "source": "growthStrain", "type": "text"},
            {"target": "selectableMarker", "source": "selectableMarker", "type": "text"},
            {"target": "fivePrimer", "source": "fivePrimer", "type": "text"},
            {"target": "threePrimer", "source": "threePrimer", "type": "text"},
            {"target": "fivePrimeCloningSite", "source": "fivePrimeCloningSite", "type": "text"},
            {"target": "threePrimeCloningSite", "source": "threePrimeCloningSite", "type": "text"},
            {"target": "fivePrimeSiteDestroyed", "source": "fivePrimeSiteDestroyed", "type": "text"},
            {"target": "threePrimeSiteDestroyed", "source": "threePrimeSiteDestroyed", "type": "text"},
            {"target": "gRNAshRNASequence", "source": "gRNAshRNASequence", "type": "text"},
            {"target": "hazardous", "source": "hazardous", "type": "text"},
        ],
    },
    "animal_models": {
        "synapse_id": "syn26486808",
        "csv_path": Path("data/csv/animal_models.csv"),
        "raw_filename": "animal_models_raw.csv",
        "select_clause": ANIMAL_MODELS_SELECT,
        "columns": [
            {"target": "animalModelId", "source": "animalModelId", "type": "iri"},
            {"target": "donorId", "source": "donorId", "type": "iri", "references": {"table": "donors", "column": "donorId"}},
            {"target": "species", "source": "species", "type": "text+", "transform": "string_list"},
            {"target": "transplantationDonorId", "source": "transplantationDonorId", "type": "iri", "references": {"table": "donors", "column": "donorId"}},
            {"target": "backgroundStrain", "source": "backgroundStrain", "type": "text"},
            {"target": "backgroundSubstrain", "source": "backgroundSubstrain", "type": "text"},
            {"target": "strainNomenclature", "source": "strainNomenclature", "type": "text"},
            {"target": "animalModelOfManifestation", "source": "animalModelOfManifestation", "type": "text+", "transform": "string_list"},
            {"target": "animalModelGeneticDisorder", "source": "animalModelGeneticDisorder", "type": "text+", "transform": "string_list"},
            {"target": "transplantationType", "source": "transplantationType", "type": "text"},
            {"target": "animalState", "source": "animalState", "type": "text"},
            {"target": "generation", "source": "generation", "type": "text"},
        ],
    },
    "cell_lines": {
        "synapse_id": "syn26486823",
        "csv_path": Path("data/csv/cell_lines.csv"),
        "raw_filename": "cell_lines_raw.csv",
        "select_clause": CELL_LINES_SELECT,
        "columns": [
            {"target": "cellLineId", "source": "cellLineId", "type": "iri"},
            {"target": "donorId", "source": "donorId", "type": "iri", "references": {"table": "donors", "column": "donorId"}},
            {"target": "originYear", "source": "originYear", "type": "text"},
            {"target": "organ", "source": "organ", "type": "text"},
            {"target": "race", "source": "race", "type": "text"},
            {"target": "strProfile", "source": "strProfile", "type": "text"},
            {"target": "tissue", "source": "tissue", "type": "text"},
            {"target": "cellLineManifestation", "source": "cellLineManifestation", "type": "text+", "transform": "string_list"},
            {"target": "resistance", "source": "resistance", "type": "text"},
            {"target": "cellLineCategory", "source": "cellLineCategory", "type": "text"},
            {"target": "contaminatedMisidentified", "source": "contaminatedMisidentified", "type": "text"},
            {"target": "cellLineGeneticDisorder", "source": "cellLineGeneticDisorder", "type": "text+", "transform": "string_list"},
            {"target": "populationDoublingTime", "source": "populationDoublingTime", "type": "text"},
        ],
    },
    "donors": {
        "synapse_id": "syn26486829",
        "csv_path": Path("data/csv/donors.csv"),
        "raw_filename": "donors_raw.csv",
        "select_clause": DONORS_SELECT,
        "columns": [
            {"target": "donorId", "source": "donorId", "type": "iri"},
            {"target": "parentDonorId", "source": "parentDonorId", "type": "iri", "references": {"table": "donors", "column": "donorId"}},
            {"target": "species", "source": "species", "type": "text+", "transform": "string_list"},
            {"target": "race", "source": "race", "type": "text"},
            {"target": "sex", "source": "sex", "type": "text"},
            {"target": "age", "source": "age", "type": "text"},
            {"target": "transplantationDonorId", "source": "transplantationDonorId", "type": "iri", "references": {"table": "donors", "column": "donorId"}},
        ],
    },
    "antibodies": {
        "synapse_id": "syn26486811",
        "csv_path": Path("data/csv/antibodies.csv"),
        "raw_filename": "antibodies_raw.csv",
        "select_clause": ANTIBODIES_SELECT,
        "columns": [
            {"target": "antibodyId", "source": "antibodyId", "type": "iri"},
            {"target": "uniprotId", "source": "uniprotId", "type": "iri"},
            {"target": "cloneId", "source": "cloneId", "type": "text"},
            {"target": "reactiveSpecies", "source": "reactiveSpecies", "type": "text+", "transform": "string_list"},
            {"target": "hostOrganism", "source": "hostOrganism", "type": "text"},
            {"target": "conjugate", "source": "conjugate", "type": "text"},
            {"target": "clonality", "source": "clonality", "type": "text"},
            {"target": "targetAntigen", "source": "targetAntigen", "type": "text"},
        ],
    },
    "resources": {
        "synapse_id": "syn26450069",
        "csv_path": Path("data/csv/resources.csv"),
        "raw_filename": "resources_raw.csv",
        "select_clause": RESOURCES_SELECT,
        "columns": [
            {"target": "resourceId", "source": "resourceId", "type": "iri"},
            {"target": "geneticReagentId", "source": "geneticReagentId", "type": "iri", "references": {"table": "genetic_reagents", "column": "geneticReagentId"}},
            {"target": "antibodyId", "source": "antibodyId", "type": "iri", "references": {"table": "antibodies", "column": "antibodyId"}},
            {"target": "cellLineId", "source": "cellLineId", "type": "iri", "references": {"table": "cell_lines", "column": "cellLineId"}},
            {"target": "animalModelId", "source": "animalModelId", "type": "iri", "references": {"table": "animal_models", "column": "animalModelId"}},
            {"target": "biobankId", "source": "biobankId", "type": "iri", "references": {"table": "biobanks", "column": "biobankId"}},
            {"target": "usageRequirements", "source": "usageRequirements", "type": "text"},
            {"target": "resourceName", "source": "resourceName", "type": "text"},
            {"target": "resourceType", "source": "resourceType", "type": "text"},
            {"target": "synonyms", "source": "synonyms", "type": "text+", "transform": "string_list"},
            {"target": "dateModified", "source": "dateModified", "type": "text"},
            {"target": "rrid", "source": "rrid", "type": "iri"},
            {"target": "description", "source": "description", "type": "text"},
            {"target": "dateAdded", "source": "dateAdded", "type": "text"},
            {"target": "howToAcquire", "source": "howToAcquire", "type": "text"},
        ],
    },
    "observations": {
        "synapse_id": "syn26486836",
        "csv_path": Path("data/csv/observations.csv"),
        "raw_filename": "observations_raw.csv",
        "select_clause": OBSERVATIONS_SELECT,
        "columns": [
            {"target": "observationId", "source": "observationId", "type": "iri"},
            {"target": "resourceId", "source": "resourceId", "type": "iri", "references": {"table": "resources", "column": "resourceId"}},
            {"target": "publicationId", "source": "publicationId", "type": "iri", "references": {"table": "publications", "column": "publicationId"}},
            {"target": "observationSubmitterName", "source": "observationSubmitterName", "type": "text"},
            {"target": "synapseId", "source": "synapseId", "type": "iri", "transform": "synapse_id"},
            {"target": "observationText", "source": "observationText", "type": "text"},
            {"target": "observationType", "source": "observationType", "type": "text"},
            {"target": "observationPhase", "source": "observationPhase", "type": "text"},
            {"target": "observationTime", "source": "observationTime", "type": "text"},
            {"target": "observationTimeUnits", "source": "observationTimeUnits", "type": "text"},
            {"target": "reliabilityRating", "source": "reliabilityRating", "type": "text"},
            {"target": "easeOfUseRating", "source": "easeOfUseRating", "type": "text"},
            {"target": "observationLink", "source": "observationLink", "type": "iri"},
        ],
    },
    "development": {
        "synapse_id": "syn26486807",
        "csv_path": Path("data/csv/development.csv"),
        "raw_filename": "development_raw.csv",
        "select_clause": DEVELOPMENT_SELECT,
        "columns": [
            {"target": "developmentId", "source": "developmentId", "type": "iri"},
            {"target": "resourceId", "source": "resourceId", "type": "iri", "references": {"table": "resources", "column": "resourceId"}},
            {"target": "investigatorId", "source": "investigatorId", "type": "iri", "references": {"table": "investigators", "column": "investigatorId"}},
            {"target": "publicationId", "source": "publicationId", "type": "iri", "references": {"table": "publications", "column": "publicationId"}},
            {"target": "funderId", "source": "funderId", "type": "iri", "references": {"table": "funders", "column": "funderId"}},
        ],
    },
    "funders": {
        "synapse_id": "syn26486830",
        "csv_path": Path("data/csv/funders.csv"),
        "raw_filename": "funders_raw.csv",
        "select_clause": FUNDERS_SELECT,
        "columns": [
            {"target": "funderId", "source": "funderId", "type": "iri"},
            {"target": "funderName", "source": "funderName", "type": "text"},
        ],
    },
    "investigators": {
        "synapse_id": "syn26486833",
        "csv_path": Path("data/csv/investigators.csv"),
        "raw_filename": "investigators_raw.csv",
        "select_clause": INVESTIGATORS_SELECT,
        "columns": [
            {"target": "investigatorId", "source": "investigatorId", "type": "iri"},
            {"target": "investigatorSynapseId", "source": "investigatorSynapseId", "type": "iri", "transform": "synapse_id"},
            {"target": "orcid", "source": "orcid", "type": "iri"},
            {"target": "institution", "source": "institution", "type": "text"},
            {"target": "investigatorName", "source": "investigatorName", "type": "text"},
        ],
    },
    "publications": {
        "synapse_id": "syn26486839",
        "csv_path": Path("data/csv/publications.csv"),
        "raw_filename": "publications_raw.csv",
        "select_clause": PUBLICATIONS_SELECT,
        "columns": [
            {"target": "publicationId", "source": "publicationId", "type": "iri"},
            {"target": "doi", "source": "doi", "type": "iri", "transform": "doi"},
            {"target": "pmid", "source": "pmid", "type": "iri", "transform": "pmid"},
            {"target": "abstract", "source": "abstract", "type": "text"},
            {"target": "journal", "source": "journal", "type": "text"},
            {"target": "publicationDate", "source": "publicationDate", "type": "text"},
            {"target": "citation", "source": "citation", "type": "text"},
            {"target": "publicationDateUnix", "source": "publicationDateUnix", "type": "text"},
            {"target": "authors", "source": "authors", "type": "text+", "transform": "string_list"},
            {"target": "publicationTitle", "source": "publicationTitle", "type": "text"},
        ],
    },
    "donor_tool": {
        "synapse_id": "syn51735419",
        "csv_path": Path("data/csv/donor_tool.csv"),
        "raw_filename": "donor_tool_raw.csv",
        "select_clause": DONOR_TOOL_SELECT,
        "columns": [
            {"target": "donorId", "source": "donorId", "type": "iri", "references": {"table": "donors", "column": "donorId"}},
            {"target": "resourceId", "source": "resourceId", "type": "iri", "references": {"table": "resources", "column": "resourceId"}},
        ],
    },
    "mutation_model": {
        "synapse_id": "syn26486834",
        "csv_path": Path("data/csv/mutation_model.csv"),
        "raw_filename": "mutation_model_raw.csv",
        "select_clause": MUTATION_MODEL_SELECT,
        "columns": [
            {"target": "mutationId", "source": "mutationId", "type": "iri", "references": {"table": "mutations", "column": "mutationId"}},
            {"target": "animalModelId", "source": "animalModelId", "type": "iri", "references": {"table": "animal_models", "column": "animalModelId"}},
            {"target": "cellLineId", "source": "cellLineId", "type": "iri", "references": {"table": "cell_lines", "column": "cellLineId"}},
        ],
    },
    "biobanks": {
        "synapse_id": "syn26486821",
        "csv_path": Path("data/csv/biobanks.csv"),
        "raw_filename": "biobanks_raw.csv",
        "select_clause": BIOBANKS_SELECT,
        "columns": [
            {"target": "biobankId", "source": "biobankId", "type": "iri"},
            {"target": "resourceId", "source": "resourceId", "type": "iri", "references": {"table": "resources", "column": "resourceId"}},
            {"target": "diseaseType", "source": "diseaseType", "type": "text+", "transform": "string_list"},
            {"target": "biobankURL", "source": "biobankURL", "type": "iri"},
            {"target": "biobankName", "source": "biobankName", "type": "text"},
            {"target": "specimenPreparationMethod", "source": "specimenPreparationMethod", "type": "text+", "transform": "string_list"},
            {"target": "specimenType", "source": "specimenType", "type": "text+", "transform": "string_list"},
            {"target": "tumorType", "source": "tumorType", "type": "text+", "transform": "string_list"},
            {"target": "specimenFormat", "source": "specimenFormat", "type": "text+", "transform": "string_list"},
            {"target": "specimenTissueType", "source": "specimenTissueType", "type": "text+", "transform": "string_list"},
            {"target": "contact", "source": "contact", "type": "text"},
        ],
    },
}


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple, set)) and len(value) == 0:
        return True
    if isinstance(value, np.ndarray) and value.size == 0:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def format_string(value: Any) -> str:
    if isinstance(value, (list, tuple, np.ndarray)):
        items = [format_string(v) for v in value]
        return "|".join(token for token in items if token)
    if is_missing(value):
        return ""
    return str(value)


def format_number(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def ensure_list(value: Any) -> List[Any]:
    if is_missing(value):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, str):
        if not value.strip():
            return []
        # Handle Python list repr strings from Synapse (e.g. "['val1', 'val2']")
        s = value.strip()
        if s.startswith("[") and s.endswith("]"):
            import ast
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list):
                    return [str(v) for v in parsed]
            except (ValueError, SyntaxError):
                pass
        # Normalize commas to pipes so both separators are handled uniformly
        normalized = value.replace(",", "|")
        return [part.strip() for part in normalized.split("|") if part.strip()]
    return [value]


def format_string_list(value: Any) -> str:
    """Format a string list field, returning empty string if no values."""
    items = ensure_list(value)
    if not items:
        return ""
    values = [format_string(v).strip() for v in items]
    filtered = [v for v in values if v]
    return "|".join(filtered) if filtered else ""


def format_synapse_id(value: Any) -> str:
    raw = format_string(value).strip()
    if not raw:
        return ""
    # Strip spurious "syn:" prefix from materialized views (e.g. "syn:syn2343195" -> "syn2343195")
    if raw.startswith("syn:"):
        raw = raw[len("syn:"):]
    return raw


def format_synapse_list(value: Any) -> str:
    return "|".join(
        token for token in (format_synapse_id(v) for v in ensure_list(value)) if token
    )


def format_pmid(value: Any) -> str:
    """Strip ``PMID:`` prefix so the bare numeric ID can be used in IRI templates."""
    s = format_string(value)
    if s.startswith("PMID:"):
        return s[5:]
    return s


def format_doi(value: Any) -> str:
    """Strip URL prefix so the bare DOI path can be used in IRI templates."""
    s = format_string(value)
    for prefix in ("https://www.doi.org/", "https://doi.org/", "http://doi.org/"):
        if s.startswith(prefix):
            return s[len(prefix):]
    return s


def format_iri_list(value: Any) -> str:
    cleaned: List[str] = []
    for entry in ensure_list(value):
        text = format_string(entry).strip()
        if not text:
            continue
        if text.startswith("http") or text.startswith("doi:"):
            cleaned.append(text)
        elif text.startswith("10."):
            cleaned.append(f"https://doi.org/{text}")
        else:
            cleaned.append(text)
    return "|".join(cleaned)


TRANSFORMS = {
    "string": format_string,
    "string_list": format_string_list,
    "synapse_id": format_synapse_id,
    "synapse_id_list": format_synapse_list,
    "iri_list": format_iri_list,
    "number": format_number,
    "pmid": format_pmid,
    "doi": format_doi,
}


def _normalize_select_clause(text: str) -> str:
    parts = []
    for line in text.strip().splitlines():
        cleaned = line.strip().rstrip(",")
        if cleaned:
            parts.append(cleaned)
    return ", ".join(parts)


def _synapse_select_clause(columns: List[Dict[str, Any]]) -> str:
    parts = []
    for idx, col in enumerate(columns, start=1):
        source = col.get("source", col["target"])
        alias = col["target"]
        if source == alias:
            parts.append(f"{source}")
        else:
            parts.append(f"{source} as {alias}")
    return ", ".join(parts)


def fetch_table(
    syn: synapseclient.Synapse,
    table_id: str,
    columns: List[Dict[str, Any]],
    manual_clause: Optional[str] = None,
) -> pd.DataFrame:
    select_clause = (
        _normalize_select_clause(manual_clause)
        if manual_clause
        else _synapse_select_clause(columns)
    )
    result = syn.tableQuery(f"select {select_clause} from {table_id}")
    return result.asDataFrame()


def build_rows(df: pd.DataFrame, columns: List[Dict[str, Any]]) -> List[List[Optional[str]]]:
    rows: List[List[str]] = []
    for _, record in df.iterrows():
        row: List[str] = []
        for col in columns:
            source = col.get("source", col["target"])
            transform_name = col.get("transform", "string")
            transform = TRANSFORMS.get(transform_name)
            if transform is None:
                raise ValueError(f"Unknown transform '{transform_name}' for column {col['target']}")
            value = record.get(source, "")
            formatted = transform(value)
            # Convert empty strings to None so CSV writer outputs empty cells (null)
            # This prevents RMLMapper from creating triples with empty string values
            row.append(None if formatted == "" else formatted)
        rows.append(row)
    return rows


def write_processed_csv(path: Path, columns: List[Dict[str, Any]], rows: List[List[Optional[str]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        # Use QUOTE_MINIMAL so empty strings are written as empty cells (not "")
        # This allows RMLMapper to skip generating triples for missing values
        writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
        writer.writerow([col["target"] for col in columns])
        writer.writerows(rows)


def write_raw(raw_dir: Path, filename: str, df: pd.DataFrame) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    df.to_csv(path, index=False)


def resolve_table_name(name: str) -> str:
    """Resolve a short table name to its full name.

    Args:
        name: Short name (e.g., 'files') or full name (e.g., 'portal_files')

    Returns:
        Full table name from TABLES dict

    Raises:
        ValueError: If the name cannot be resolved to a valid table
    """
    # Try full name first
    if name in TABLES:
        return name

    # Try alias
    if name in TABLE_ALIASES:
        return TABLE_ALIASES[name]

    # Not found
    valid_names = sorted(set(TABLES.keys()) | set(TABLE_ALIASES.keys()))
    raise ValueError(
        f"Unknown table '{name}'. Valid names: {', '.join(valid_names)}"
    )


def _find_raw_csv(raw_dir: Path, raw_filename: str) -> Optional[Path]:
    """Find a raw CSV in the cache directory."""
    candidate = raw_dir / raw_filename
    if candidate.exists():
        return candidate
    return None


def apply_derived_columns(
    table_name: str,
    df: pd.DataFrame,
    processed_tables: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    if table_name == "animal_models":
        if "species" in df.columns:
            return df

        donors_df = processed_tables.get("donors")
        if donors_df is None:
            raise ValueError("animal_models requires donors to be processed first so species can be derived")

        donor_species = donors_df.loc[:, ["donorId", "species"]].drop_duplicates(
            subset=["donorId"],
            keep="first",
        )
        return df.merge(donor_species, on="donorId", how="left")

    if table_name == "cell_lines":
        if "race" in df.columns:
            return df

        donors_df = processed_tables.get("donors")
        if donors_df is None:
            raise ValueError("cell_lines requires donors to be processed first so race can be derived")

        donor_race = donors_df.loc[:, ["donorId", "race"]].drop_duplicates(
            subset=["donorId"],
            keep="first",
        )
        return df.merge(donor_race, on="donorId", how="left")

    return df


def normalize_fetched_df(
    table_name: str,
    df: pd.DataFrame,
    processed_tables: Dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, int]:
    """Apply post-fetch normalization so all fetch paths behave the same."""
    n_before = len(df)

    # Synapse may return list-typed columns which are unhashable;
    # convert to tuples so drop_duplicates() can hash every cell.
    for col in df.columns:
        if df[col].apply(lambda x: isinstance(x, list)).any():
            df[col] = df[col].apply(lambda x: tuple(x) if isinstance(x, list) else x)

    df = df.drop_duplicates()
    n_dupes = n_before - len(df)
    df = apply_derived_columns(table_name, df, processed_tables)
    return df, n_dupes


def check_config(config_path: Path) -> int:
    """Verify that TABLES and data_sources.yaml agree on names and Synapse IDs."""
    with config_path.open() as f:
        config = yaml.safe_load(f)

    errors: List[str] = []
    for profile_name, profile in config.get("profiles", {}).items():
        ds_tables = profile.get("tables", {})
        ds_names = set(ds_tables.keys())
        local_names = set(TABLES.keys())

        only_ds = sorted(ds_names - local_names)
        only_local = sorted(local_names - ds_names)
        if only_ds:
            errors.append(
                f"[{profile_name}] in data_sources.yaml but not in TABLES: "
                + ", ".join(only_ds)
            )
        if only_local:
            errors.append(
                f"[{profile_name}] in TABLES but not in data_sources.yaml: "
                + ", ".join(only_local)
            )

        for name in sorted(ds_names & local_names):
            ds_id = ds_tables[name]["synapse_id"]
            local_id = TABLES[name]["synapse_id"]
            if ds_id != local_id:
                errors.append(
                    f"[{profile_name}] {name}: synapse_id mismatch "
                    f"(data_sources={ds_id}, TABLES={local_id})"
                )

    if errors:
        print("Config check FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(f"Config check passed: {len(TABLES)} tables consistent with {config_path}")
    return 0


def resolve_source_synapse_ids(config_path: Path, profile: str) -> Dict[str, str]:
    """Resolve table fetch IDs, appending source_version when present."""
    with config_path.open() as f:
        config = yaml.safe_load(f)

    profiles = config.get("profiles", {})
    if profile not in profiles:
        raise ValueError(f"Profile '{profile}' not found in {config_path}")

    resolved: Dict[str, str] = {}
    for table_name, table_info in profiles[profile].get("tables", {}).items():
        synapse_id = table_info["synapse_id"]
        source_version = table_info.get("source_version")
        if source_version:
            resolved[table_name] = f"{synapse_id}.{source_version}"
        else:
            resolved[table_name] = synapse_id
    return resolved


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Table names: study, file, mutation, reagent, animal, cell, donor, antibody, "
               "resource, observation, dev, funder, investigator, publication, "
               "donor_tool, mutation_model, biobank"
    )
    parser.add_argument(
        "tables",
        nargs="*",
        help="Subset of tables to download (defaults to all configured tables). "
             "Examples: 'file study', 'animal', 'mutation'",
    )
    parser.add_argument(
        "--raw-dir",
        default=Path("data/raw"),
        type=Path,
        help="Directory to store the raw Synapse CSV exports.",
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Re-process from cached raw CSVs in --raw-dir instead of fetching from Synapse.",
    )
    parser.add_argument(
        "--check-config",
        type=Path,
        nargs="?",
        const=Path("data_sources.yaml"),
        metavar="PATH",
        help="Check that TABLES matches data_sources.yaml (default path) and exit.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run FK validation on processed CSVs after writing.",
    )
    parser.add_argument(
        "--source-config",
        type=Path,
        default=Path("data_sources.yaml"),
        help="Path to data_sources.yaml for source-versioned fetch IDs (default: data_sources.yaml).",
    )
    parser.add_argument(
        "--source-profile",
        default="release",
        help="Profile in --source-config to use for source-versioned fetch IDs (default: release).",
    )
    args = parser.parse_args(argv)

    if args.check_config is not None:
        return check_config(args.check_config)

    # Resolve table names (handle aliases)
    if args.tables:
        try:
            table_names = [resolve_table_name(name) for name in args.tables]
        except ValueError as e:
            parser.error(str(e))
            return 1
    else:
        table_names = sorted(TABLES.keys())

    if "donors" in table_names:
        table_names = ["donors"] + [name for name in table_names if name != "donors"]

    source_synapse_ids = resolve_source_synapse_ids(args.source_config, args.source_profile)

    syn = None
    if not args.from_cache:
        # Do NOT call login() — anonymous access is used for public data only.
        syn = synapseclient.Synapse()

    processed_tables: Dict[str, pd.DataFrame] = {}
    for table_name in table_names:
        config = TABLES[table_name]

        if args.from_cache:
            raw_path = _find_raw_csv(args.raw_dir, config["raw_filename"])
            if raw_path is None:
                print(f"Skipping {table_name}: no cached raw CSV found in {args.raw_dir}", flush=True)
                continue
            print(f"Processing {table_name} from cache ({raw_path}) ...", flush=True)
            df = pd.read_csv(raw_path, keep_default_na=False, dtype=str)
            print(f"  Read {len(df)} rows", flush=True)
        else:
            fetch_synapse_id = source_synapse_ids.get(table_name, config["synapse_id"])
            print(f"Fetching {table_name} ({fetch_synapse_id}) ...", flush=True)
            select_clause_text = config.get("select_clause")
            df = fetch_table(syn, fetch_synapse_id, config["columns"], select_clause_text)
            print(f"  Retrieved {len(df)} rows", flush=True)
            write_raw(args.raw_dir, config["raw_filename"], df)

        df, n_dupes = normalize_fetched_df(table_name, df, processed_tables)
        if n_dupes:
            print(f"  Dropped {n_dupes} duplicate rows", flush=True)

        processed_tables[table_name] = df.copy()
        data_rows = build_rows(df, config["columns"])
        write_processed_csv(config["csv_path"], config["columns"], data_rows)
        print(f"  Wrote CSV -> {config['csv_path']}")

    if args.validate:
        print("\n--- FK validation ---", flush=True)
        from validate_fks import validate_all, print_human
        csv_dir = Path(TABLES[table_names[0]]["csv_path"]).parent
        results = validate_all(csv_dir)
        print_human(results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
