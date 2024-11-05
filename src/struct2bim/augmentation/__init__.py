"""Deterministic 2D document augmentation applied after clean rendering."""

from struct2bim.augmentation.document import (
    AugmentationProfile,
    AugmentationResult,
    augment_document,
    transform_points,
)

__all__ = [
    "AugmentationProfile",
    "AugmentationResult",
    "augment_document",
    "transform_points",
]

