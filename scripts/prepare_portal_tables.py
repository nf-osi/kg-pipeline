#!/usr/bin/env python3
"""Download portal tables from Synapse and emit raw + processed CSV exports.

The raw files are untouched Synapse exports for archival/debugging, while the
processed CSVs normalize IDs, flatten to pipe-delimited lists, and coerce numeric
columns so downstream mapping jobs see consistent values. The SELECT clauses are
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

PORTAL_STUDIES_SELECT = """
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

PORTAL_FILES_SELECT = """
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
modelSystemName as modelSystemName
"""

PORTAL_MUTATIONS_SELECT = """
mutationDetailsId as mutationDetailsId,
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

PORTAL_GENETIC_REAGENTS_SELECT = """
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

PORTAL_ANIMAL_MODELS_SELECT = """
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

PORTAL_CELL_LINES_SELECT = """
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

# Short name aliases for convenience
TABLE_ALIASES = {
    "studies": "portal_studies",
    "study": "portal_studies",
    "files": "portal_files",
    "file": "portal_files",
    "mutations": "portal_mutations",
    "mutation": "portal_mutations",
    "genetic_reagents": "portal_genetic_reagents",
    "genetic_reagent": "portal_genetic_reagents",
    "reagents": "portal_genetic_reagents",
    "reagent": "portal_genetic_reagents",
    "animal_models": "portal_animal_models",
    "animal_model": "portal_animal_models",
    "animals": "portal_animal_models",
    "animal": "portal_animal_models",
    "cell_lines": "portal_cell_lines",
    "cell_line": "portal_cell_lines",
    "cells": "portal_cell_lines",
    "cell": "portal_cell_lines",
}

TABLES: Dict[str, Dict[str, Any]] = {
    "portal_studies": {
        "synapse_id": "syn52694652",
        "csv_path": Path("data/csv/portal_studies.csv"),
        "raw_filename": "portal_studies_raw.csv",
        "select_clause": PORTAL_STUDIES_SELECT,
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
    "portal_files": {
        "synapse_id": "syn16858331",
        "csv_path": Path("data/csv/portal_files.csv"),
        "raw_filename": "portal_files_raw.csv",
        "select_clause": PORTAL_FILES_SELECT,
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
            {"target": "individualID", "source": "individualID", "type": "text"},
            {"target": "diagnosis", "source": "diagnosis", "type": "text+", "transform": "string_list"},
            {"target": "nf1Genotype", "source": "nf1Genotype", "type": "text"},
            {"target": "nf2Genotype", "source": "nf2Genotype", "type": "text"},
            {"target": "sex", "source": "sex", "type": "text"},
            {"target": "species", "source": "species", "type": "text"},
            {"target": "specimenID", "source": "specimenID", "type": "text+", "transform": "string_list"},
            {"target": "cellType", "source": "cellType", "type": "text"},
            {"target": "tissue", "source": "tissue", "type": "text"},
            {"target": "tumorType", "source": "tumorType", "type": "text+", "transform": "string_list"},
            {"target": "fundingAgency", "source": "fundingAgency", "type": "text"},
            {
                "target": "reportMilestone",
                "source": "progressReportNumber",
                "type": "text",
                "transform": "number",
            },
            {"target": "compoundName", "source": "compoundName", "type": "text"},
            {
                "target": "experimentalCondition",
                "source": "experimentalCondition",
                "type": "text",
            },
            {"target": "modelSystemName", "source": "modelSystemName", "type": "text"},
        ],
    },
    "portal_mutations": {
        "synapse_id": "syn26486835",
        "csv_path": Path("data/csv/portal_mutations.csv"),
        "raw_filename": "portal_mutations_raw.csv",
        "select_clause": PORTAL_MUTATIONS_SELECT,
        "columns": [
            {"target": "mutationDetailsId", "source": "mutationDetailsId", "type": "iri"},
            {"target": "humanClinVarMutation", "source": "humanClinVarMutation", "type": "text"},
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
    "portal_genetic_reagents": {
        "synapse_id": "syn26486832",
        "csv_path": Path("data/csv/portal_genetic_reagents.csv"),
        "raw_filename": "portal_genetic_reagents_raw.csv",
        "select_clause": PORTAL_GENETIC_REAGENTS_SELECT,
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
    "portal_animal_models": {
        "synapse_id": "syn26486808",
        "csv_path": Path("data/csv/portal_animal_models.csv"),
        "raw_filename": "portal_animal_models_raw.csv",
        "select_clause": PORTAL_ANIMAL_MODELS_SELECT,
        "columns": [
            {"target": "animalModelId", "source": "animalModelId", "type": "iri"},
            {"target": "donorId", "source": "donorId", "type": "iri"},
            {"target": "transplantationDonorId", "source": "transplantationDonorId", "type": "iri"},
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
    "portal_cell_lines": {
        "synapse_id": "syn26486823",
        "csv_path": Path("data/csv/portal_cell_lines.csv"),
        "raw_filename": "portal_cell_lines_raw.csv",
        "select_clause": PORTAL_CELL_LINES_SELECT,
        "columns": [
            {"target": "cellLineId", "source": "cellLineId", "type": "iri"},
            {"target": "donorId", "source": "donorId", "type": "iri"},
            {"target": "originYear", "source": "originYear", "type": "text"},
            {"target": "organ", "source": "organ", "type": "text"},
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
        return [part.strip() for part in value.split("|") if part.strip()]
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
    if raw.startswith("syn:") or raw.startswith("http"):
        return raw
    if raw.startswith("syn"):
        return f"syn:{raw}"
    return raw


def format_synapse_list(value: Any) -> str:
    return "|".join(
        token for token in (format_synapse_id(v) for v in ensure_list(value)) if token
    )


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


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Table names can be specified using short forms (e.g., 'files', 'studies') "
               "or full forms (e.g., 'portal_files', 'portal_studies')."
    )
    parser.add_argument(
        "tables",
        nargs="*",
        help="Subset of tables to download (defaults to all configured tables). "
             "Examples: 'files studies', 'animal_models', 'portal_mutations'",
    )
    parser.add_argument(
        "--raw-dir",
        default=Path("data/raw"),
        type=Path,
        help="Directory to store the raw Synapse CSV exports.",
    )
    args = parser.parse_args(argv)

    syn = synapseclient.Synapse()
    syn.login(silent=True)

    # Resolve table names (handle aliases)
    if args.tables:
        try:
            table_names = [resolve_table_name(name) for name in args.tables]
        except ValueError as e:
            parser.error(str(e))
            return 1
    else:
        table_names = sorted(TABLES.keys())

    for table_name in table_names:
        config = TABLES[table_name]
        print(f"Fetching {table_name} ({config['synapse_id']}) ...", flush=True)
        select_clause_text = config.get("select_clause")
        df = fetch_table(syn, config["synapse_id"], config["columns"], select_clause_text)
        print(f"  Retrieved {len(df)} rows", flush=True)
        write_raw(args.raw_dir, config["raw_filename"], df)
        data_rows = build_rows(df, config["columns"])
        write_processed_csv(config["csv_path"], config["columns"], data_rows)
        print(f"  Wrote CSV -> {config['csv_path']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
