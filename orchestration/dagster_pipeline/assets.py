"""Asset definitions for portal tables pipeline."""

from pathlib import Path
from typing import List

from dagster import (
    AssetExecutionContext,
    Config,
    asset,
    multi_asset,
    AssetOut,
    Output,
)
import pandas as pd

from .resources import RMLMapperResource, SynapseResource
from .config import TABLE_CONFIGS, TableConfig


# =============================================================================
# Asset Factories
# =============================================================================


def create_csv_asset(table_name: str, config: TableConfig):
    """Create a Dagster asset for downloading a CSV table from Synapse."""

    @asset(
        name=f"{table_name}_csv",
        key_prefix=["portal", "csv"],
        compute_kind="synapse",
        group_name=table_name,
        metadata={
            "synapse_id": config.synapse_id,
            "table": table_name,
        },
    )
    def _csv_asset(context: AssetExecutionContext, synapse: SynapseResource) -> pd.DataFrame:
        """Download and process table from Synapse."""
        context.log.info(f"Fetching {table_name} from Synapse ({config.synapse_id})")

        # Use the existing prepare_portal_tables.py logic
        df = synapse.fetch_table(config.synapse_id, config.columns, config.select_clause)

        # Write processed CSV
        csv_path = config.csv_path
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        synapse.write_processed_csv(csv_path, config.columns, df)

        context.log.info(f"Wrote {len(df)} rows to {csv_path}")
        context.add_output_metadata({
            "num_rows": len(df),
            "num_columns": len(df.columns),
            "path": str(csv_path),
        })

        return df

    return _csv_asset


def create_harmonize_asset(table_name: str, config: TableConfig):
    """Create a Dagster asset for harmonizing CSV data before RML mapping."""

    if not config.harmonize_script:
        return None

    csv_asset_key = ["portal", "csv", f"{table_name}_csv"]

    @asset(
        name=f"{table_name}_harmonized",
        key_prefix=["portal", "csv"],
        compute_kind="python",
        group_name=table_name,
        deps=[csv_asset_key],
        metadata={
            "table": table_name,
            "script": config.harmonize_script,
        },
    )
    def _harmonize_asset(context: AssetExecutionContext) -> Path:
        """Harmonize CSV data using a classification script."""
        import subprocess

        project_root = Path(__file__).parent.parent.parent

        cmd = ["python", config.harmonize_script] + (config.harmonize_args or [])

        context.log.info(f"Running harmonization for {table_name}: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )

        if result.stdout:
            context.log.info(f"Harmonize output:\n{result.stdout}")
        if result.stderr:
            context.log.warning(f"Harmonize stderr: {result.stderr}")

        if result.returncode != 0:
            raise RuntimeError(
                f"Harmonization script failed with code {result.returncode}: {result.stderr}"
            )

        abs_output = project_root / config.harmonize_output
        num_rows = sum(1 for _ in open(abs_output)) - 1  # subtract header

        context.add_output_metadata({
            "path": str(config.harmonize_output),
            "num_rows": num_rows,
        })

        return config.harmonize_output

    return _harmonize_asset


def create_rdf_asset(table_name: str, config: TableConfig):
    """Create a Dagster asset for RML mapping (CSV -> RDF)."""

    # Depend on harmonized asset if it exists, otherwise on the CSV asset
    if config.harmonize_script:
        dep_key = ["portal", "csv", f"{table_name}_harmonized"]
    else:
        dep_key = ["portal", "csv", f"{table_name}_csv"]

    @asset(
        name=f"{table_name}_rdf",
        key_prefix=["portal", "rdf"],
        compute_kind="rml",
        group_name=table_name,
        deps=[dep_key],
        metadata={
            "table": table_name,
        },
    )
    def _rdf_asset(context: AssetExecutionContext, rml_mapper: RMLMapperResource) -> Path:
        """Generate RDF from CSV using RMLMapper."""
        project_root = Path(__file__).parent.parent.parent

        rml_file = config.rml_path
        output_file = config.rdf_path

        context.log.info(f"Running RMLMapper for {table_name}")
        rml_mapper.run(
            mapping_file=rml_file,
            output_file=output_file,
            log_file=config.log_path,
        )

        abs_output = project_root / output_file
        size_mb = abs_output.stat().st_size / (1024 * 1024)

        context.add_output_metadata({
            "path": str(output_file),
            "size_mb": round(size_mb, 2),
        })

        return output_file

    return _rdf_asset


# =============================================================================
# Generate all assets
# =============================================================================


def generate_portal_assets() -> List:
    """Generate all portal table assets."""
    assets = []

    for table_name, config in TABLE_CONFIGS.items():
        # Create CSV download asset
        csv_asset = create_csv_asset(table_name, config)
        assets.append(csv_asset)

        # Create harmonize asset if needed (runs between CSV and RDF)
        if config.harmonize_script:
            harmonize_asset = create_harmonize_asset(table_name, config)
            if harmonize_asset:
                assets.append(harmonize_asset)

        # Create RDF generation asset
        rdf_asset = create_rdf_asset(table_name, config)
        assets.append(rdf_asset)

    return assets


portal_assets = generate_portal_assets()
