"""Configuration for portal tables."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional


@dataclass
class TableConfig:
    """Configuration for a portal table."""

    name: str
    synapse_id: str
    csv_path: Path
    rml_path: Path
    rdf_path: Path
    rdf_raw_path: Path
    log_path: Path
    select_clause: str
    columns: List[Dict[str, Any]]
    needs_transform: bool = False


# Import from prepare_portal_tables.py
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.prepare_portal_tables import (
    TABLES,
    PORTAL_STUDIES_SELECT,
    PORTAL_FILES_SELECT,
    PORTAL_MUTATIONS_SELECT,
    PORTAL_GENETIC_REAGENTS_SELECT,
    PORTAL_ANIMAL_MODELS_SELECT,
    PORTAL_CELL_LINES_SELECT,
    PORTAL_DONORS_SELECT,
    PORTAL_ANTIBODIES_SELECT,
)

# Tables that need IRI transform
TRANSFORM_TABLES = {"portal_studies", "portal_files"}

# Custom RML filenames (for tables where RML filename differs from table name)
CUSTOM_RML_NAMES = {
    "donor_tool": "donor_tool",
    "resources": "resources",
    "development_funder": "development_funder",
    "development_investigator": "development_investigator",
    "development_publication": "development_publication",
}

# Build TableConfig objects
TABLE_CONFIGS: Dict[str, TableConfig] = {}

for table_name, table_data in TABLES.items():
    # Use custom RML name if available, otherwise use table_name
    rml_name = CUSTOM_RML_NAMES.get(table_name, table_name)

    config = TableConfig(
        name=table_name,
        synapse_id=table_data["synapse_id"],
        csv_path=table_data["csv_path"],
        rml_path=Path(f"mappings/rml/{rml_name}.rml.ttl"),
        rdf_path=Path(f"data/rdf/{table_name}.ttl"),
        rdf_raw_path=Path(f"data/rdf/{table_name}.rml.ttl"),
        log_path=Path(f"logs/{table_name}_rml.log"),
        select_clause=table_data["select_clause"],
        columns=table_data["columns"],
        needs_transform=table_name in TRANSFORM_TABLES,
    )
    TABLE_CONFIGS[table_name] = config
