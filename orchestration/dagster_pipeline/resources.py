"""Resources for Dagster pipeline."""

import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
import synapseclient
from dagster import ConfigurableResource, InitResourceContext


class SynapseResource(ConfigurableResource):
    """Resource for interacting with Synapse."""

    def setup_for_execution(self, context: InitResourceContext) -> None:
        """Initialize Synapse client with anonymous access."""
        # Do NOT call login() — anonymous access is used for public data only.
        self._client = synapseclient.Synapse()

    def fetch_table(
        self,
        table_id: str,
        columns: List[Dict[str, Any]],
        select_clause: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch a table from Synapse."""
        from scripts.prepare_portal_tables import (
            fetch_table as _fetch_table,
        )
        return _fetch_table(self._client, table_id, columns, select_clause)

    def write_processed_csv(
        self,
        path: Path,
        columns: List[Dict[str, Any]],
        df: pd.DataFrame,
    ) -> None:
        """Write processed CSV file."""
        from scripts.prepare_portal_tables import (
            build_rows,
            write_processed_csv as _write_csv,
        )
        rows = build_rows(df, columns)
        _write_csv(path, columns, rows)


class RMLMapperResource(ConfigurableResource):
    """Resource for running RMLMapper."""

    jar_path: str = "tools/rmlmapper-8.1.0.jar"
    java_max_heap: str = os.environ.get("JAVA_MAX_HEAP", "4g")
    function_files: List[str] = [
        "tools/functions_grel.ttl",
        "tools/grel_java_mapping.ttl",
    ]

    def run(
        self,
        mapping_file: Path,
        output_file: Path,
        log_file: Path,
    ) -> None:
        """Run RMLMapper."""
        # Get project root (parent of orchestration directory)
        project_root = Path(__file__).parent.parent.parent

        # Ensure output directories exist (absolute paths)
        abs_output_file = project_root / output_file
        abs_log_file = project_root / log_file
        abs_output_file.parent.mkdir(parents=True, exist_ok=True)
        abs_log_file.parent.mkdir(parents=True, exist_ok=True)

        # Build command with relative paths (relative to project root)
        logback_config = project_root / "tools" / "logback-rmlmapper.xml"
        cmd = [
            "java",
            f"-Xmx{self.java_max_heap}",
            f"-Dlogback.configurationFile={logback_config}",
            "-jar",
            self.jar_path,
        ]

        # Add function files
        for func_file in self.function_files:
            cmd.extend(["-f", func_file])

        # Add mapping and output
        cmd.extend([
            "-m", str(mapping_file),
            "-s", "turtle",
            "-o", str(output_file),
        ])

        # Run RMLMapper from project root
        with open(abs_log_file, "w") as log:
            result = subprocess.run(
                cmd,
                stderr=log,
                stdout=subprocess.PIPE,
                text=True,
                cwd=str(project_root),  # Run from project root
            )

        if result.returncode != 0:
            log_content = abs_log_file.read_text()
            raise subprocess.CalledProcessError(
                result.returncode, cmd, output=result.stdout, stderr=log_content
            )


# Resource instances
synapse_resource = SynapseResource()
rml_mapper_resource = RMLMapperResource()
