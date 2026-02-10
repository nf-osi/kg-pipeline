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


def create_rdf_asset(table_name: str, config: TableConfig):
    """Create a Dagster asset for RML mapping (CSV -> RDF)."""
    import shutil

    csv_asset_key = ["portal", "csv", f"{table_name}_csv"]

    # For tables with transform, this creates the .rml.ttl intermediate file
    # For tables without transform, this creates .rml.ttl and copies to .ttl
    asset_name = f"{table_name}_rdf_rml" if config.needs_transform else f"{table_name}_rdf"

    @asset(
        name=asset_name,
        key_prefix=["portal", "rdf"],
        compute_kind="rml",
        group_name=table_name,
        deps=[csv_asset_key],
        metadata={
            "table": table_name,
            "needs_transform": config.needs_transform,
        },
    )
    def _rdf_asset(context: AssetExecutionContext, rml_mapper: RMLMapperResource) -> Path:
        """Generate RDF from CSV using RMLMapper."""
        # Get project root
        project_root = Path(__file__).parent.parent.parent

        rml_file = config.rml_path
        csv_file = config.csv_path
        # Always output to .rml.ttl first
        rml_output = config.rdf_raw_path

        context.log.info(f"Running RMLMapper for {table_name}")
        rml_mapper.run(
            mapping_file=rml_file,
            output_file=rml_output,
            log_file=config.log_path,
        )

        # Get file size for metadata (use absolute path)
        abs_rml_output = project_root / rml_output
        size_mb = abs_rml_output.stat().st_size / (1024 * 1024)

        context.add_output_metadata({
            "path": str(rml_output),
            "size_mb": round(size_mb, 2),
        })

        # For tables without transform, copy .rml.ttl to .ttl (final output)
        if not config.needs_transform:
            abs_final = project_root / config.rdf_path
            context.log.info(f"Copying {rml_output} to {config.rdf_path} (final output)")
            shutil.copy2(abs_rml_output, abs_final)

            context.add_output_metadata({
                "final_path": str(config.rdf_path),
            })

        return rml_output

    return _rdf_asset


def create_transform_asset(table_name: str, config: TableConfig):
    """Create a Dagster asset for IRI transformation (RML RDF -> final RDF)."""

    if not config.needs_transform:
        return None

    rml_rdf_asset_key = ["portal", "rdf", f"{table_name}_rdf_rml"]

    @asset(
        name=f"{table_name}_rdf",
        key_prefix=["portal", "rdf"],
        compute_kind="transform",
        group_name=table_name,
        deps=[rml_rdf_asset_key],
        metadata={
            "table": table_name,
        },
    )
    def _transform_asset(context: AssetExecutionContext) -> Path:
        """Transform literal values to IRIs using SPARQL."""
        import subprocess

        # Get project root
        project_root = Path(__file__).parent.parent.parent

        rml_file = config.rdf_raw_path  # Input: .rml.ttl
        final_file = config.rdf_path     # Output: .ttl
        lookup_file = Path("mappings/data_lookup.ttl")

        context.log.info(f"Running IRI transform for {table_name}")

        result = subprocess.run(
            [
                "python",
                "scripts/transform_iris.py",
                "--input", str(rml_file),
                "--output", str(final_file),
                "--lookup", str(lookup_file),
            ],
            capture_output=True,
            text=True,
            cwd=str(project_root),  # Run from project root
        )

        # Log output
        if result.stdout:
            context.log.info(f"Transform output: {result.stdout}")
        if result.stderr:
            context.log.warning(f"Transform stderr: {result.stderr}")

        # Check return code
        if result.returncode != 0:
            raise RuntimeError(f"Transform script failed with code {result.returncode}")

        # Get file size (use absolute path)
        abs_final_file = project_root / final_file
        size_mb = abs_final_file.stat().st_size / (1024 * 1024)

        context.add_output_metadata({
            "path": str(final_file),
            "size_mb": round(size_mb, 2),
        })

        return final_file

    return _transform_asset


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

        # Create RDF generation asset
        rdf_asset = create_rdf_asset(table_name, config)
        assets.append(rdf_asset)

        # Create transform asset if needed
        if config.needs_transform:
            transform_asset = create_transform_asset(table_name, config)
            if transform_asset:
                assets.append(transform_asset)

    return assets


portal_assets = generate_portal_assets()
