"""Procedural curricula and dataset grouping."""

from struct2bim.curriculum.generator import ReferenceSceneConfig, generate_reference_scene
from struct2bim.curriculum.manifest import DatasetManifest, SampleRecord, build_manifest
from struct2bim.curriculum.splits import DatasetSplit, SplitRatios, assign_grouped_splits

__all__ = [
    "DatasetManifest",
    "DatasetSplit",
    "ReferenceSceneConfig",
    "SampleRecord",
    "SplitRatios",
    "assign_grouped_splits",
    "build_manifest",
    "generate_reference_scene",
]
