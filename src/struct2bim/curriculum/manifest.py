"""Machine-readable records for generated dataset artifacts."""

from __future__ import annotations

import hashlib
from collections import Counter

from pydantic import Field

from struct2bim.curriculum.splits import DatasetSplit, SplitRatios, assign_grouped_splits
from struct2bim.curriculum.splits import validate_no_split_leakage
from struct2bim.domain.geometry import DomainModel


class SampleRecord(DomainModel):
    sample_id: str = Field(min_length=1)
    scene_seed: int
    variant: str = Field(min_length=1)
    image_path: str = Field(min_length=1)
    segmentation_label_path: str = Field(min_length=1)
    obb_label_path: str = Field(min_length=1)
    entity_counts: dict[str, int]
    semantic_mask_path: str | None = None
    instance_mask_path: str | None = None
    metadata_path: str | None = None
    scene_path: str | None = None
    dxf_path: str | None = None
    artifact_sha256: dict[str, str] = Field(default_factory=dict)


class ManifestSample(SampleRecord):
    split: DatasetSplit


class DatasetManifest(DomainModel):
    schema_version: str = "1.0"
    generator_version: str
    ontology_version: str
    project_seed: int
    config_sha256: str
    samples: tuple[ManifestSample, ...]
    sample_counts_by_split: dict[str, int]
    entity_counts_by_class: dict[str, int]

    @property
    def sha256(self) -> str:
        payload = self.model_dump_json(exclude_none=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_manifest(
    records: list[SampleRecord],
    *,
    project_seed: int,
    config_payload: str,
    generator_version: str = "0.1.0",
    ontology_version: str = "1.0",
    ratios: SplitRatios | None = None,
) -> DatasetManifest:
    assignments = assign_grouped_splits(records, project_seed=project_seed, ratios=ratios)
    validate_no_split_leakage(assignments)
    samples = tuple(
        ManifestSample(**record.model_dump(), split=split)
        for split in DatasetSplit
        for record in assignments[split]
    )
    entity_counts: Counter[str] = Counter()
    for sample in samples:
        entity_counts.update(sample.entity_counts)
    return DatasetManifest(
        generator_version=generator_version,
        ontology_version=ontology_version,
        project_seed=project_seed,
        config_sha256=hashlib.sha256(config_payload.encode("utf-8")).hexdigest(),
        samples=samples,
        sample_counts_by_split={
            split.value: len(assignments[split]) for split in DatasetSplit
        },
        entity_counts_by_class=dict(sorted(entity_counts.items())),
    )
