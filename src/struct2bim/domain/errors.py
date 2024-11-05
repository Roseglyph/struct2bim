"""Stable domain errors shared by generation and export adapters."""


class Struct2BIMDomainError(ValueError):
    """A domain invariant was violated."""

    code = "DOMAIN_ERROR"


class InvalidGeometryError(Struct2BIMDomainError):
    """Geometry is degenerate or inconsistent."""

    code = "GEOMETRY_INVALID"


class AnnotationOutOfBoundsError(Struct2BIMDomainError):
    """Projected annotation geometry leaves the image canvas."""

    code = "ANNOTATION_OUT_OF_BOUNDS"


class DatasetSplitLeakageError(Struct2BIMDomainError):
    """Variants of one scene occur in multiple dataset splits."""

    code = "DATASET_SPLIT_LEAKAGE"
