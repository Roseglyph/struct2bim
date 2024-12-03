"""Deterministic code-informed structural reference-scene generation."""

from __future__ import annotations

import random
import string
from typing import Literal

from pydantic import Field, model_validator

from struct2bim.domain.entities import (
    ColumnDimensions,
    ColumnShape,
    GridAxis,
    Storey,
    StructuralEntity,
)
from struct2bim.domain.geometry import CoordinateTransform, DomainModel, Point2D
from struct2bim.domain.provenance import Provenance, ScaleSource, SourceType
from struct2bim.domain.scene import SceneProject, SceneSource, StructuralScene


class ReferenceSceneConfig(DomainModel):
    """Controls a compact but visually varied column-and-grid reference floor."""

    project_name: str = "struct2bim_reference"
    canvas_width_px: int = Field(default=2048, gt=0)
    canvas_height_px: int = Field(default=2048, gt=0)
    pixels_per_mm: float = Field(default=0.12, gt=0)
    columns_x: int = Field(default=4, ge=2, le=12)
    columns_y: int = Field(default=3, ge=2, le=12)
    spacing_x_mm: float = Field(default=4000.0, gt=0)
    spacing_y_mm: float = Field(default=4500.0, gt=0)
    storey_height_mm: float = Field(default=3200.0, gt=0)
    margin_mm: float = Field(default=800.0, ge=0)
    layout_mode: Literal["isolated", "regular", "irregular"] = "regular"
    irregularity_ratio: float = Field(default=0.12, ge=0.0, le=0.25)

    @model_validator(mode="after")
    def validate_canvas_fit(self) -> ReferenceSceneConfig:
        drawing_width = (self.columns_x - 1) * self.spacing_x_mm + 2 * self.margin_mm
        drawing_height = (self.columns_y - 1) * self.spacing_y_mm + 2 * self.margin_mm
        if drawing_width * self.pixels_per_mm > self.canvas_width_px:
            raise ValueError("configured X grid does not fit the image canvas")
        if drawing_height * self.pixels_per_mm > self.canvas_height_px:
            raise ValueError("configured Y grid does not fit the image canvas")
        return self


def _centered_positions(count: int, spacing: float) -> tuple[float, ...]:
    start = -((count - 1) * spacing) / 2
    return tuple(start + index * spacing for index in range(count))


def _column_for_position(
    *, index: int, variation_index: int, x: float, y: float, storey: Storey, rng: random.Random
) -> StructuralEntity:
    # A fixed cycle guarantees ontology coverage; seeded choices vary the exact dimensions.
    variation = variation_index % 4
    if variation == 2:
        diameter = float(rng.choice((350, 400, 450, 500)))
        subtype = ColumnShape.CIRCULAR
        dimensions = ColumnDimensions(diameter=diameter, height=storey.height_mm)
        rotation = 0.0
        class_id = 1
    else:
        if variation == 0:
            width = depth = float(rng.choice((300, 350, 400, 450)))
            rotation = 0.0
        else:
            width = float(rng.choice((300, 350, 400)))
            depth = float(rng.choice((500, 600, 700)))
            rotation = float(rng.choice((0, 30, 45, 90))) if variation == 3 else 0.0
        subtype = ColumnShape.RECTANGULAR
        dimensions = ColumnDimensions(width=width, depth=depth, height=storey.height_mm)
        class_id = 0
    return StructuralEntity(
        id=f"COL-{index + 1:03d}",
        subtype=subtype,
        storey_id=storey.id,
        center_mm=Point2D(x=x, y=y),
        dimensions_mm=dimensions,
        rotation_deg=rotation,
        label=f"C{index + 1}",
        class_id=class_id,
        provenance=Provenance.synthetic(),
    )


def generate_reference_scene(
    scene_seed: int, config: ReferenceSceneConfig | None = None
) -> StructuralScene:
    """Generate a reproducible structural scene before any renderer is invoked."""

    resolved = config or ReferenceSceneConfig()
    rng = random.Random(scene_seed)
    x_positions: tuple[float, ...]
    y_positions: tuple[float, ...]
    if resolved.layout_mode == "isolated":
        x_positions = (0.0,)
        y_positions = (0.0,)
    else:
        x_positions = _centered_positions(resolved.columns_x, resolved.spacing_x_mm)
        y_positions = _centered_positions(resolved.columns_y, resolved.spacing_y_mm)
        if resolved.layout_mode == "irregular":
            x_positions = tuple(
                value + rng.uniform(-1, 1) * resolved.spacing_x_mm * resolved.irregularity_ratio
                for value in x_positions
            )
            y_positions = tuple(
                value + rng.uniform(-1, 1) * resolved.spacing_y_mm * resolved.irregularity_ratio
                for value in y_positions
            )
    min_x, max_x = x_positions[0] - resolved.margin_mm, x_positions[-1] + resolved.margin_mm
    min_y, max_y = y_positions[0] - resolved.margin_mm, y_positions[-1] + resolved.margin_mm

    grids: list[GridAxis] = []
    for index, x in enumerate(x_positions):
        grids.append(
            GridAxis(
                id=f"GRID-X-{index + 1:02d}",
                label=str(index + 1),
                start_mm=Point2D(x=x, y=min_y),
                end_mm=Point2D(x=x, y=max_y),
            )
        )
    for index, y in enumerate(y_positions):
        label = string.ascii_uppercase[index]
        grids.append(
            GridAxis(
                id=f"GRID-Y-{index + 1:02d}",
                label=label,
                start_mm=Point2D(x=min_x, y=y),
                end_mm=Point2D(x=max_x, y=y),
            )
        )

    storey = Storey(
        id="L01", name="Ground Floor", elevation_mm=0.0, height_mm=resolved.storey_height_mm
    )
    entities = tuple(
        _column_for_position(
            index=index,
            variation_index=index + scene_seed,
            x=x,
            y=y,
            storey=storey,
            rng=rng,
        )
        for index, (y, x) in enumerate(
            (position for y_value in y_positions for position in ((y_value, x_value) for x_value in x_positions))
        )
    )
    return StructuralScene(
        project=SceneProject(name=resolved.project_name),
        source=SceneSource(
            type=SourceType.SYNTHETIC_GROUND_TRUTH,
            image=None,
            width_px=resolved.canvas_width_px,
            height_px=resolved.canvas_height_px,
            scene_seed=scene_seed,
        ),
        transform=CoordinateTransform(
            pixels_per_mm=resolved.pixels_per_mm,
            origin_px=Point2D(
                x=resolved.canvas_width_px / 2,
                y=resolved.canvas_height_px / 2,
            ),
        ),
        scale_source=ScaleSource.SYNTHETIC_GROUND_TRUTH,
        storeys=(storey,),
        grids=tuple(grids),
        entities=entities,
    )
