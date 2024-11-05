"""Image-space document variations kept separate from Blender."""

from __future__ import annotations

from enum import StrEnum
from typing import TypeAlias, cast

import cv2
import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict

UInt8Image: TypeAlias = npt.NDArray[np.uint8]
FloatArray: TypeAlias = npt.NDArray[np.float64]


class AugmentationProfile(StrEnum):
    CLEAN = "clean"
    SCAN = "scan"
    PERSPECTIVE_PHOTO = "perspective_photo"


class AugmentationResult(BaseModel):
    """An augmented image and the exact source-to-output homography."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    image: UInt8Image
    homography: FloatArray
    profile: AugmentationProfile
    seed: int


def _validate_image(image: UInt8Image) -> None:
    if image.ndim not in (2, 3):
        raise ValueError("image must be grayscale or color")
    if image.shape[0] < 32 or image.shape[1] < 32:
        raise ValueError("image is too small for document augmentation")
    if image.dtype != np.uint8:
        raise ValueError("image must use uint8 pixels")


def _scan_variant(image: UInt8Image, rng: np.random.Generator) -> UInt8Image:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    background = np.linspace(0.96, 1.04, gray.shape[1], dtype=np.float32)[None, :]
    noise = rng.normal(0.0, 2.2, size=gray.shape).astype(np.float32)
    scanned_float = gray.astype(np.float32) * background + noise
    scanned_uint8 = cv2.GaussianBlur(
        np.clip(scanned_float, 0, 255).astype(np.uint8), (3, 3), 0.45
    )
    return cast(UInt8Image, cv2.cvtColor(scanned_uint8, cv2.COLOR_GRAY2BGR))


def _perspective_variant(
    image: UInt8Image, rng: np.random.Generator
) -> tuple[UInt8Image, FloatArray]:
    height, width = image.shape[:2]
    maximum = min(width, height) * 0.035
    offsets = rng.uniform(-maximum, maximum, size=(4, 2)).astype(np.float32)
    source = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    destination = source + offsets
    homography = cv2.getPerspectiveTransform(source, destination)
    warped = cv2.warpPerspective(
        image,
        homography,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(236, 232, 222),
    )
    x_gradient = np.linspace(0.88, 1.07, width, dtype=np.float32)[None, :, None]
    lit = np.clip(warped.astype(np.float32) * x_gradient, 0, 255).astype(np.uint8)
    blurred = cast(UInt8Image, cv2.GaussianBlur(lit, (3, 3), 0.35))
    return blurred, cast(FloatArray, homography.astype(np.float64))


def augment_document(
    image: UInt8Image,
    profile: AugmentationProfile,
    seed: int,
) -> AugmentationResult:
    """Apply a deterministic 2D variation without invoking Blender."""
    _validate_image(image)
    rng = np.random.default_rng(seed)
    identity = np.eye(3, dtype=np.float64)

    if profile == AugmentationProfile.CLEAN:
        output, homography = image.copy(), identity
    elif profile == AugmentationProfile.SCAN:
        output, homography = _scan_variant(image, rng), identity
    else:
        output, homography = _perspective_variant(image, rng)

    return AugmentationResult(
        image=output,
        homography=homography,
        profile=profile,
        seed=seed,
    )


def transform_points(points: FloatArray, homography: FloatArray) -> FloatArray:
    """Transform an N×2 point array with a document homography."""
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("points must have shape (N, 2)")
    if homography.shape != (3, 3):
        raise ValueError("homography must have shape (3, 3)")
    source = points.astype(np.float64).reshape(1, -1, 2)
    transformed = cv2.perspectiveTransform(source, homography.astype(np.float64))[0]
    return cast(FloatArray, transformed)
