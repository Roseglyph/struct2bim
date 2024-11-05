import cv2
import numpy as np
import pytest

from struct2bim.augmentation import (
    AugmentationProfile,
    augment_document,
    transform_points,
    transform_annotation_set,
)
from struct2bim.annotations import annotations_from_scene
from struct2bim.curriculum import generate_reference_scene


@pytest.fixture
def drawing() -> np.ndarray:
    image = np.full((128, 192, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (60, 40), (120, 90), (0, 0, 0), thickness=-1)
    return image


def test_clean_profile_is_identity(drawing: np.ndarray) -> None:
    result = augment_document(drawing, AugmentationProfile.CLEAN, seed=1)
    assert np.array_equal(result.image, drawing)
    assert np.array_equal(result.homography, np.eye(3))


def test_scan_profile_is_deterministic(drawing: np.ndarray) -> None:
    first = augment_document(drawing, AugmentationProfile.SCAN, seed=7)
    second = augment_document(drawing, AugmentationProfile.SCAN, seed=7)
    assert np.array_equal(first.image, second.image)
    assert not np.array_equal(first.image, drawing)


def test_perspective_profile_transforms_points(drawing: np.ndarray) -> None:
    result = augment_document(drawing, AugmentationProfile.PERSPECTIVE_PHOTO, seed=11)
    points = np.array([[60.0, 40.0], [120.0, 90.0]], dtype=np.float64)
    transformed = transform_points(points, result.homography)
    assert transformed.shape == (2, 2)
    assert not np.allclose(transformed, points)


def test_invalid_image_is_rejected() -> None:
    with pytest.raises(ValueError, match="too small"):
        augment_document(np.zeros((8, 8), dtype=np.uint8), AugmentationProfile.SCAN, seed=1)


def test_perspective_transform_keeps_annotations_valid(drawing: np.ndarray) -> None:
    scene = generate_reference_scene(42)
    annotations = annotations_from_scene(scene)
    large_drawing = np.full(
        (scene.source.height_px, scene.source.width_px, 3), 255, dtype=np.uint8
    )
    result = augment_document(large_drawing, AugmentationProfile.PERSPECTIVE_PHOTO, seed=4)
    transformed = transform_annotation_set(annotations, result.homography)
    assert len(transformed.records) == len(scene.entities)
    assert transformed.records[0].polygon_px != annotations.records[0].polygon_px
