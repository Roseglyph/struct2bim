"""Deterministic 2D document augmentation applied after clean rendering."""

from struct2bim.augmentation.document import (
    AugmentationProfile,
    AugmentationResult,
    augment_document,
    transform_points,
)
from struct2bim.augmentation.annotations import transform_annotation_set

__all__ = [
    "AugmentationProfile",
    "AugmentationResult",
    "augment_document",
    "transform_points",
    "transform_annotation_set",
]
