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
    log_path: Path
    select_clause: str
    columns: List[Dict[str, Any]]
    harmonize_script: Optional[str] = None
    harmonize_output: Optional[Path] = None
    harmonize_args: Optional[List[str]] = None
    chunk_rows: Optional[int] = None


# Import from prepare_portal_tables.py
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.prepare_portal_tables import TABLES

# Build TableConfig objects
TABLE_CONFIGS: Dict[str, TableConfig] = {}

for table_name, table_data in TABLES.items():
    config = TableConfig(
        name=table_name,
        synapse_id=table_data["synapse_id"],
        csv_path=table_data["csv_path"],
        rml_path=Path(f"mappings/rml/{table_name}.rml.ttl"),
        rdf_path=Path(f"data/rdf/{table_name}.ttl"),
        log_path=Path(f"logs/{table_name}_rml.log"),
        select_clause=table_data["select_clause"],
        columns=table_data["columns"],
    )
    TABLE_CONFIGS[table_name] = config

# Configure harmonization for studies (dataType labels to IRIs)
TABLE_CONFIGS["studies"].harmonize_script = "scripts/classify_datatypes.py"
TABLE_CONFIGS["studies"].harmonize_output = Path("data/csv/studies_harmonized.csv")
TABLE_CONFIGS["studies"].harmonize_args = [
    "--input", "data/csv/studies.csv",
    "--output", "data/csv/studies_harmonized.csv",
    "--lookup", "mappings/sssom/data_lookup.sssom.tsv",
]

# Configure harmonization for observations
TABLE_CONFIGS["observations"].harmonize_script = "scripts/classify_observations.py"
TABLE_CONFIGS["observations"].harmonize_output = Path("data/csv/observation_harmonized.csv")
TABLE_CONFIGS["observations"].harmonize_args = [
    "--observations", "data/csv/observations.csv",
    "--mapping", "mappings/sssom/observation_type_mapping.sssom.tsv",
    "--output", "data/csv/observation_harmonized.csv",
]

# Configure harmonization for files (link modelSystemName to entity IRIs + dataType to IRIs)
TABLE_CONFIGS["files"].harmonize_script = "scripts/harmonize_files.py"
TABLE_CONFIGS["files"].harmonize_output = Path("data/csv/files_harmonized.csv")
TABLE_CONFIGS["files"].harmonize_args = [
    "--files", "data/csv/files.csv",
    "--resources", "data/csv/resources.csv",
    "--output", "data/csv/files_harmonized.csv",
    "--lookup", "mappings/sssom/data_lookup.sssom.tsv",
    "--nf1-lookup", "mappings/sssom/nf1_genotype_lookup.sssom.tsv",
    "--nf2-lookup", "mappings/sssom/nf2_genotype_lookup.sssom.tsv",
]
TABLE_CONFIGS["files"].chunk_rows = 100_000

# Configure harmonization for cell lines (cellLineCategory to subclass IRIs)
TABLE_CONFIGS["cell_lines"].harmonize_script = "scripts/classify_cell_lines.py"
TABLE_CONFIGS["cell_lines"].harmonize_output = Path("data/csv/cell_lines_harmonized.csv")
TABLE_CONFIGS["cell_lines"].harmonize_args = [
    "--input", "data/csv/cell_lines.csv",
    "--output", "data/csv/cell_lines_harmonized.csv",
    "--lookup", "mappings/sssom/cell_line_category_lookup.sssom.tsv",
]

# Configure harmonization for genetic reagents (vectorType to subclass IRIs)
TABLE_CONFIGS["genetic_reagents"].harmonize_script = "scripts/classify_genetic_reagents.py"
TABLE_CONFIGS["genetic_reagents"].harmonize_output = Path("data/csv/genetic_reagents_harmonized.csv")
TABLE_CONFIGS["genetic_reagents"].harmonize_args = [
    "--input", "data/csv/genetic_reagents.csv",
    "--output", "data/csv/genetic_reagents_harmonized.csv",
    "--lookup", "mappings/sssom/reagent_type_lookup.sssom.tsv",
]

# Configure harmonization for mutations (mutationType to subclass IRIs)
TABLE_CONFIGS["mutations"].harmonize_script = "scripts/classify_mutations.py"
TABLE_CONFIGS["mutations"].harmonize_output = Path("data/csv/mutations_harmonized.csv")
TABLE_CONFIGS["mutations"].harmonize_args = [
    "--input", "data/csv/mutations.csv",
    "--output", "data/csv/mutations_harmonized.csv",
    "--lookup", "mappings/sssom/mutation_type_lookup.sssom.tsv",
]
