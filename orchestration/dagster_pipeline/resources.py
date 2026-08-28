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

    @property
    def client(self) -> synapseclient.Synapse:
        """The underlying anonymous client, for code that needs to query directly."""
        return self._client

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
    java_max_heap: str = os.environ.get("JAVA_MAX_HEAP", "6g")
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

    def run_chunked(
        self,
        mapping_file: Path,
        output_file: Path,
        log_file: Path,
        chunk_rows: int,
    ) -> None:
        """Run RMLMapper in chunks to stay within memory limits.

        Splits the source CSV into chunks, runs RMLMapper on each with a
        patched mapping file, and concatenates the turtle outputs.
        """
        import csv as csv_mod
        import re
        import tempfile

        project_root = Path(__file__).parent.parent.parent
        abs_mapping = project_root / mapping_file
        abs_output = project_root / output_file

        # Find the CSV source path from the mapping file
        mapping_text = abs_mapping.read_text()
        match = re.search(r'rml:source\s+"([^"]+)"', mapping_text)
        if not match:
            raise ValueError(f"Could not find rml:source in {mapping_file}")
        csv_source = match.group(1)
        abs_csv = project_root / csv_source

        # Read CSV and split into chunks
        with open(abs_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv_mod.reader(f)
            header = next(reader)
            chunks: List[List[list]] = [[]]
            for row in reader:
                if len(chunks[-1]) >= chunk_rows:
                    chunks.append([])
                chunks[-1].append(row)

        abs_output.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=str(project_root)) as tmpdir:
            chunk_outputs = []
            for i, chunk in enumerate(chunks):
                # Write chunk CSV
                chunk_csv = Path(tmpdir) / f"chunk_{i}.csv"
                with open(chunk_csv, "w", newline="", encoding="utf-8") as f:
                    writer = csv_mod.writer(f)
                    writer.writerow(header)
                    writer.writerows(chunk)

                # Patch mapping to point to chunk CSV
                chunk_mapping = Path(tmpdir) / f"chunk_{i}.rml.ttl"
                rel_chunk_csv = chunk_csv.relative_to(project_root)
                patched = mapping_text.replace(csv_source, str(rel_chunk_csv))
                chunk_mapping.write_text(patched)

                # Run RMLMapper on chunk
                chunk_output = Path(tmpdir) / f"chunk_{i}.ttl"
                rel_mapping = chunk_mapping.relative_to(project_root)
                rel_output = chunk_output.relative_to(project_root)
                chunk_log = Path(tmpdir) / f"chunk_{i}.log"
                rel_log = chunk_log.relative_to(project_root)

                self.run(
                    mapping_file=rel_mapping,
                    output_file=rel_output,
                    log_file=rel_log,
                )
                chunk_outputs.append(chunk_output)

            # Concatenate turtle outputs (duplicate @prefix declarations are valid)
            with open(abs_output, "w", encoding="utf-8") as out:
                for chunk_output in chunk_outputs:
                    out.write(chunk_output.read_text())


# Resource instances
synapse_resource = SynapseResource()
rml_mapper_resource = RMLMapperResource()
