"""
pytest configuration and shared fixtures for NF-OSI KG pipeline tests

This file is automatically loaded by pytest and provides reusable fixtures
for all test files.
"""

import pytest
from pathlib import Path
from rdflib import Graph, Namespace
import subprocess
import tempfile
import os

# Define namespaces
NF = Namespace("http://nf-osi.github.com/terms#")
SYN = Namespace("https://www.synapse.org/#!Synapse:")

# Project paths
PROJECT_DIR = Path(__file__).parent.parent
RMLMAPPER_JAR = PROJECT_DIR / "tools" / "rmlmapper-8.1.0.jar"
FUNCTIONS_GREL = PROJECT_DIR / "tools" / "functions_grel.ttl"
GREL_MAPPING = PROJECT_DIR / "tools" / "grel_java_mapping.ttl"
TEST_DATA_DIR = PROJECT_DIR / "test"
MAPPINGS_DIR = PROJECT_DIR / "mappings" / "rml"


@pytest.fixture(scope="session")
def project_paths():
    """Provide project paths to all tests"""
    return {
        "project_dir": PROJECT_DIR,
        "rmlmapper_jar": RMLMAPPER_JAR,
        "functions_grel": FUNCTIONS_GREL,
        "grel_mapping": GREL_MAPPING,
        "test_data_dir": TEST_DATA_DIR,
        "mappings_dir": MAPPINGS_DIR,
    }


@pytest.fixture(scope="session")
def namespaces():
    """Provide RDF namespaces to all tests"""
    return {
        "nf": NF,
        "syn": SYN,
    }


@pytest.fixture
def rml_runner(project_paths):
    """
    Fixture to run RMLMapper on a given mapping file with test CSV

    Usage:
        graph = rml_runner(
            mapping_file="portal_mutations.rml.ttl",
            csv_replacements={"data/csv/mutations.csv": "test/mutations.csv"}
        )
    """
    def _run(mapping_file: str, csv_replacements: dict) -> Graph:
        """
        Run RMLMapper with CSV path replacements

        Args:
            mapping_file: Name of RML mapping file in mappings/rml/
            csv_replacements: Dict of {original_path: test_path}

        Returns:
            RDFLib Graph of the output
        """
        mapping_path = project_paths["mappings_dir"] / mapping_file

        if not mapping_path.exists():
            raise FileNotFoundError(f"Mapping file not found: {mapping_path}")

        # Create temporary mapping file with replaced CSV paths
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.rml.ttl', delete=False, dir=project_paths["test_data_dir"]
        ) as temp_mapping:
            content = mapping_path.read_text()
            for original, replacement in csv_replacements.items():
                content = content.replace(original, replacement)
            temp_mapping.write(content)
            temp_mapping_path = temp_mapping.name

        # Create temporary output file
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.ttl', delete=False, dir=project_paths["test_data_dir"]
        ) as temp_output:
            output_path = temp_output.name

        try:
            # Run RMLMapper
            cmd = [
                "java", "-jar", str(project_paths["rmlmapper_jar"]),
                "-f", str(project_paths["functions_grel"]),
                "-f", str(project_paths["grel_mapping"]),
                "-m", temp_mapping_path,
                "-s", "turtle",
                "-o", output_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(project_paths["project_dir"])
            )

            if result.returncode != 0:
                raise RuntimeError(f"RMLMapper failed: {result.stderr}")

            # Load output into RDFLib graph
            g = Graph()
            g.parse(output_path, format="turtle")

            # Bind namespaces for prettier SPARQL queries
            g.bind("nf", NF)
            g.bind("syn", SYN)

            return g

        finally:
            # Cleanup temp files
            try:
                os.unlink(temp_mapping_path)
            except:
                pass
            try:
                os.unlink(output_path)
            except:
                pass

    return _run


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
