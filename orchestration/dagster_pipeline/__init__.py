"""Dagster pipeline for NF Knowledge Graph generation."""

from dagster import Definitions

from .assets import portal_assets, variant_assets
from .resources import rml_mapper_resource, synapse_resource

defs = Definitions(
    # variant_assets is empty unless KG_INCLUDE_VARIANTS is set -- see assets.py.
    assets=[*portal_assets, *variant_assets],
    resources={
        "rml_mapper": rml_mapper_resource,
        "synapse": synapse_resource,
    },
)
