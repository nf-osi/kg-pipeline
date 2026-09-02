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

# Tool nodes live in these nine per-type graphs. Kept in sync with
# prepare_portal_tables.TOOL_TABLES, which is imported lazily inside assets to
# avoid a hard dependency at module import time.
from scripts.prepare_portal_tables import TOOL_TABLES as TOOL_GRAPHS


# =============================================================================
# Asset Factories
# =============================================================================


def create_csv_asset(table_name: str, config: TableConfig):
    """Create a Dagster asset for downloading a CSV table from Synapse."""

    deps = []
    if table_name == "animal_models":
        deps.append(["portal", "csv", "donors"])
    if table_name == "cell_lines":
        deps.append(["portal", "csv", "donors"])

    @asset(
        name=table_name,
        key_prefix=["portal", "csv"],
        compute_kind="synapse",
        group_name=table_name,
        deps=deps,
        metadata={
            "synapse_id": config.synapse_id,
            "table": table_name,
        },
    )
    def _csv_asset(context: AssetExecutionContext, synapse: SynapseResource) -> pd.DataFrame:
        """Download and process table from Synapse."""
        from scripts.prepare_portal_tables import (
            normalize_fetched_df,
            resolve_source_synapse_ids,
            write_raw,
        )

        project_root = Path(__file__).parent.parent.parent
        raw_dir = project_root / "data" / "raw"
        raw_path = raw_dir / config.raw_filename

        if raw_path.exists():
            context.log.info(f"Using cached raw table for {table_name} from {raw_path}")
            df = pd.read_csv(raw_path, keep_default_na=False, dtype=str)
        else:
            source_ids = resolve_source_synapse_ids(project_root / "data_sources.yaml", "release")
            fetch_id = source_ids.get(table_name, config.synapse_id)
            context.log.info(f"Fetching {table_name} from Synapse ({fetch_id})")

            df = synapse.fetch_table(fetch_id, config.columns, config.select_clause)
            write_raw(raw_dir, config.raw_filename, df)
            context.log.info(f"Wrote raw cache {raw_path}")

        processed_tables = {}
        if table_name in {"animal_models", "cell_lines"}:
            donors_csv = project_root / "data" / "csv" / "donors.csv"
            if not donors_csv.exists():
                raise RuntimeError(f"{table_name} requires data/csv/donors.csv before processing")
            processed_tables["donors"] = pd.read_csv(donors_csv, keep_default_na=False, dtype=str)

        df, n_dupes = normalize_fetched_df(table_name, df, processed_tables)
        if n_dupes:
            context.log.info(f"Dropped {n_dupes} duplicate rows for {table_name}")

        csv_path = config.csv_path
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        synapse.write_processed_csv(csv_path, config.columns, df)

        context.log.info(f"Wrote {len(df)} rows to {csv_path}")
        context.add_output_metadata({
            "num_rows": len(df),
            "num_columns": len(df.columns),
            "path": str(csv_path),
            "raw_cache_path": str(raw_path.relative_to(project_root)),
        })

        return df

    return _csv_asset


def create_harmonize_asset(table_name: str, config: TableConfig):
    """Create a Dagster asset for harmonizing CSV data before RML mapping."""

    if not config.harmonize_script:
        return None

    csv_asset_key = ["portal", "csv", table_name]

    # Some harmonization scripts read other tables' CSVs as lookups (files, for
    # instance, resolves modelSystemName against animal_models and cell_lines),
    # so those CSV assets have to materialize first. Derive the extra deps from
    # the script arguments rather than restating them, so a new lookup argument
    # cannot drift out of sync with the dependency graph.
    csv_path_to_table = {
        str(cfg.csv_path): name for name, cfg in TABLE_CONFIGS.items()
    }
    deps = [csv_asset_key]
    for arg in config.harmonize_args or []:
        dep_table = csv_path_to_table.get(arg)
        if dep_table and dep_table != table_name:
            dep_key = ["portal", "csv", dep_table]
            if dep_key not in deps:
                deps.append(dep_key)

    @asset(
        name=table_name,
        key_prefix=["portal", "harmonized"],
        compute_kind="python",
        group_name=table_name,
        deps=deps,
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

        # Save harmonization report for artifact upload
        report_dir = project_root / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"{table_name}_harmonize.txt"
        report_file.write_text(
            (result.stdout or "") + (result.stderr or "")
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Harmonization script failed with code {result.returncode}: {result.stderr}"
            )

        abs_output = project_root / config.harmonize_output
        num_rows = sum(1 for _ in open(abs_output)) - 1  # subtract header

        context.add_output_metadata({
            "path": str(config.harmonize_output),
            "num_rows": num_rows,
            "report": str(report_file.relative_to(project_root)),
        })

        return config.harmonize_output

    return _harmonize_asset


def create_validation_asset(csv_asset_keys: list):
    """Create a Dagster asset that validates FK constraints across all CSVs.

    Non-blocking: logs results and attaches violation counts as metadata,
    but never raises.
    """

    @asset(
        name="fk_validation",
        key_prefix=["portal", "quality"],
        compute_kind="python",
        group_name="validation",
        deps=csv_asset_keys,
    )
    def _validation_asset(context: AssetExecutionContext) -> None:
        """Run FK validation across all processed CSVs."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from validate_fks import validate_all

        project_root = Path(__file__).parent.parent.parent
        data_dir = project_root / "data" / "csv"

        results = validate_all(data_dir)

        failures = 0
        for r in results:
            label = f"{r.constraint.source_table}.{r.constraint.source_column}"
            target = r.constraint.target_label
            if r.passed:
                context.log.info(f" ok   {label} -> {target}")
            else:
                failures += 1
                context.log.warning(
                    f"FAIL  {label} -> {target}: "
                    f"{r.orphaned}/{r.populated} orphaned ({r.orphan_pct:.1f}%)"
                )

        context.add_output_metadata({
            "total_constraints": len(results),
            "failures": failures,
            "passed": len(results) - failures,
        })

    return _validation_asset


def create_rdf_asset(table_name: str, config: TableConfig):
    """Create a Dagster asset for RML mapping (CSV -> RDF)."""

    # Depend on harmonized asset if it exists, otherwise on the CSV asset
    if config.harmonize_script:
        dep_key = ["portal", "harmonized", table_name]
    else:
        dep_key = ["portal", "csv", table_name]

    @asset(
        name=table_name,
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
        import subprocess

        project_root = Path(__file__).parent.parent.parent

        rml_file = config.rml_path
        output_file = config.rdf_path

        context.log.info(f"Running RMLMapper for {table_name}")
        try:
            if config.chunk_rows:
                context.log.info(f"Using chunked processing ({config.chunk_rows} rows per chunk)")
                rml_mapper.run_chunked(
                    mapping_file=rml_file,
                    output_file=output_file,
                    log_file=config.log_path,
                    chunk_rows=config.chunk_rows,
                )
            else:
                rml_mapper.run(
                    mapping_file=rml_file,
                    output_file=output_file,
                    log_file=config.log_path,
                )
        except subprocess.CalledProcessError as e:
            stderr = e.stderr or ""
            # Show full log when short (real errors), summarize when long (known warnings)
            if len(stderr) < 5000:
                context.log.warning(
                    f"RMLMapper for {table_name} exited {e.returncode}:\n{stderr}"
                )
            else:
                lines = stderr.splitlines()
                unique_errors = set(lines)
                summary = f"RMLMapper for {table_name} exited {e.returncode}: {len(lines)} log lines, {len(unique_errors)} unique"
                for line in list(unique_errors)[:5]:
                    summary += f"\n  {line[:200]}"
                context.log.warning(summary)

        abs_output = project_root / output_file
        if not abs_output.exists() or abs_output.stat().st_size == 0:
            raise RuntimeError(f"RMLMapper did not produce output: {output_file}")

        size_mb = abs_output.stat().st_size / (1024 * 1024)
        context.add_output_metadata({
            "path": str(output_file),
            "size_mb": round(size_mb, 2),
        })

        return output_file

    return _rdf_asset


@asset(
    name="shared_donor_links",
    key_prefix=["portal", "rdf"],
    compute_kind="python",
    group_name="relationships",
    deps=[["portal", "rdf", "cell_lines"], ["portal", "rdf", "animal_models"]],
)
def shared_donor_links_asset(context: AssetExecutionContext) -> Path:
    """Generate derived sharedDonor links after core RDF is available."""
    from scripts.materialize_shared_donor_links import materialize_shared_donor_links

    project_root = Path(__file__).parent.parent.parent
    output_file = project_root / "data" / "rdf" / "shared_donor_links.ttl"

    materialize_shared_donor_links(
        cell_lines_ttl=project_root / "data" / "rdf" / "cell_lines.ttl",
        animal_models_ttl=project_root / "data" / "rdf" / "animal_models.ttl",
        output_ttl=output_file,
    )

    size_mb = output_file.stat().st_size / (1024 * 1024)
    context.add_output_metadata({
        "path": str(output_file.relative_to(project_root)),
        "size_mb": round(size_mb, 4),
    })

    return output_file


@asset(
    name="observation_links",
    key_prefix=["portal", "rdf"],
    compute_kind="python",
    group_name="relationships",
    deps=[
        *[["portal", "rdf", name] for name in TOOL_GRAPHS],
        ["portal", "rdf", "observations"],
    ],
)
def observation_links_asset(context: AssetExecutionContext) -> Path:
    """Generate derived hasObservation/aboutResource links after core RDF is available."""
    from scripts.materialize_observation_links import materialize_observation_links

    project_root = Path(__file__).parent.parent.parent
    output_file = project_root / "data" / "rdf" / "observation_links.ttl"

    materialize_observation_links(
        resources_ttl=[
            project_root / "data" / "rdf" / f"{name}.ttl" for name in TOOL_GRAPHS
        ],
        observations_ttl=project_root / "data" / "rdf" / "observations.ttl",
        output_ttl=output_file,
    )

    size_mb = output_file.stat().st_size / (1024 * 1024)
    context.add_output_metadata({
        "path": str(output_file.relative_to(project_root)),
        "size_mb": round(size_mb, 4),
    })

    return output_file


@asset(
    name="nf1_mutation_sets",
    key_prefix=["portal", "rdf"],
    compute_kind="python",
    group_name="relationships",
    deps=[["portal", "rdf", "cell_lines"], ["portal", "rdf", "mutations"], ["portal", "rdf", "mutation_model"]],
)
def nf1_mutation_sets_asset(context: AssetExecutionContext) -> Path:
    """Generate derived NF1 mutation set nodes after core RDF is available."""
    from scripts.materialize_nf1_mutation_sets import materialize_nf1_mutation_sets

    project_root = Path(__file__).parent.parent.parent
    output_file = project_root / "data" / "rdf" / "nf1_mutation_sets.ttl"

    materialize_nf1_mutation_sets(
        cell_lines_ttl=project_root / "data" / "rdf" / "cell_lines.ttl",
        mutations_ttl=project_root / "data" / "rdf" / "mutations.ttl",
        output_ttl=output_file,
        mutation_model_ttl=project_root / "data" / "rdf" / "mutation_model.ttl",
    )

    size_mb = output_file.stat().st_size / (1024 * 1024)
    context.add_output_metadata({
        "path": str(output_file.relative_to(project_root)),
        "size_mb": round(size_mb, 4),
    })

    return output_file


def create_build_metadata_asset(rdf_asset_keys: list):
    """Create a Dagster asset that writes graph build metadata (build datetime as
    graph build version, source table versions from data_sources.yaml) after all
    RDF has been generated.
    """

    @asset(
        name="build_metadata",
        key_prefix=["portal", "rdf"],
        compute_kind="python",
        group_name="relationships",
        deps=rdf_asset_keys + [["portal", "rdf", "shared_donor_links"], ["portal", "rdf", "nf1_mutation_sets"], ["portal", "rdf", "observation_links"]],
    )
    def _build_metadata_asset(context: AssetExecutionContext) -> Path:
        """Generate graph-level VoID/PROV build metadata TTL."""
        from scripts.build_metadata import write_metadata_ttl

        project_root = Path(__file__).parent.parent.parent
        output_file = project_root / "data" / "rdf" / "build_metadata.ttl"

        write_metadata_ttl(
            data_sources_path=project_root / "data_sources.yaml",
            profile_name="release",
            output_path=output_file,
        )

        size_mb = output_file.stat().st_size / (1024 * 1024)
        context.add_output_metadata({
            "path": str(output_file.relative_to(project_root)),
            "size_mb": round(size_mb, 4),
        })

        return output_file

    return _build_metadata_asset


# =============================================================================
# Generate all assets
# =============================================================================


def generate_portal_assets() -> List:
    """Generate all portal table assets."""
    assets = []
    csv_asset_keys = []
    rdf_asset_keys = []

    for table_name, config in TABLE_CONFIGS.items():
        # Create CSV download asset
        csv_asset = create_csv_asset(table_name, config)
        assets.append(csv_asset)
        csv_asset_keys.append(["portal", "csv", table_name])

        # Create harmonize asset if needed (runs between CSV and RDF)
        if config.harmonize_script:
            harmonize_asset = create_harmonize_asset(table_name, config)
            if harmonize_asset:
                assets.append(harmonize_asset)

        # Create RDF generation asset
        rdf_asset = create_rdf_asset(table_name, config)
        assets.append(rdf_asset)
        rdf_asset_keys.append(["portal", "rdf", table_name])

    # Add FK validation asset (depends on all CSV assets)
    validation_asset = create_validation_asset(csv_asset_keys)
    assets.append(validation_asset)
    assets.append(shared_donor_links_asset)
    assets.append(nf1_mutation_sets_asset)
    assets.append(observation_links_asset)
    assets.append(create_build_metadata_asset(rdf_asset_keys))

    return assets


portal_assets = generate_portal_assets()
