"""Dagster pipeline for NF Knowledge Graph generation."""

from dagster import Definitions

from .assets import portal_assets
from .resources import rml_mapper_resource, synapse_resource

defs = Definitions(
    assets=[*portal_assets],
    resources={
        "rml_mapper": rml_mapper_resource,
        "synapse": synapse_resource,
    },
)
