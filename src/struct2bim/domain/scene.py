"""Aggregate root for canonical structural scenes."""

from __future__ import annotations

import hashlib

from pydantic import Field, model_validator

from struct2bim.domain.entities import GridAxis, Storey, StructuralEntity
from struct2bim.domain.geometry import CoordinateTransform, DomainModel
from struct2bim.domain.provenance import ScaleSource, SourceType


class SceneProject(DomainModel):
    name: str = Field(min_length=1)
    units: str = "mm"


class SceneSource(DomainModel):
    type: SourceType
    image: str | None = None
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    scene_seed: int


class StructuralScene(DomainModel):
    schema_version: str = "1.0"
    project: SceneProject
    source: SceneSource
    transform: CoordinateTransform
    scale_source: ScaleSource
    storeys: tuple[Storey, ...] = Field(min_length=1)
    grids: tuple[GridAxis, ...] = ()
    entities: tuple[StructuralEntity, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> StructuralScene:
        identifiers = [entity.id for entity in self.entities]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("entity IDs must be unique")
        grid_ids = [axis.id for axis in self.grids]
        if len(grid_ids) != len(set(grid_ids)):
            raise ValueError("grid IDs must be unique")
        storey_ids = {storey.id for storey in self.storeys}
        missing = {entity.storey_id for entity in self.entities} - storey_ids
        if missing:
            raise ValueError(f"entities reference missing storeys: {sorted(missing)}")
        return self

    def canonical_json(self) -> str:
        """Stable serialization suitable for hashing and committed fixtures."""

        return self.model_dump_json(indent=2, exclude_none=True)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
