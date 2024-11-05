"""Source and scale provenance carried through every pipeline stage."""

from enum import StrEnum

from pydantic import Field

from struct2bim.domain.geometry import DomainModel


class SourceType(StrEnum):
    SYNTHETIC_GROUND_TRUTH = "synthetic_ground_truth"
    MODEL_PREDICTION = "model_prediction"
    CAD_GEOMETRY = "cad_geometry"


class ScaleSource(StrEnum):
    SYNTHETIC_GROUND_TRUTH = "synthetic_ground_truth"
    CAD_UNITS = "cad_units"
    DIMENSION_ANNOTATION = "dimension_annotation"
    DECLARED_DRAWING_SCALE = "declared_drawing_scale"
    MANUAL_CALIBRATION = "manual_calibration"
    UNKNOWN = "unknown"


class Provenance(DomainModel):
    source: SourceType
    confidence: float = Field(ge=0.0, le=1.0)
    checkpoint: str | None = None

    @classmethod
    def synthetic(cls) -> "Provenance":
        return cls(source=SourceType.SYNTHETIC_GROUND_TRUTH, confidence=1.0)
