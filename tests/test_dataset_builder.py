from pathlib import Path

import cv2
import numpy as np

from struct2bim.application import DatasetBuildConfig, build_dataset
from struct2bim.augmentation import AugmentationProfile
from struct2bim.curriculum import ReferenceSceneConfig


class FakeRenderer:
    def render_clean_drawing(
        self, scene_json: Path, output_png: Path, *, seed: int = 24017
    ) -> None:
        del scene_json, seed
        output_png.parent.mkdir(parents=True, exist_ok=True)
        image = np.full((320, 480, 3), 255, dtype=np.uint8)
        assert cv2.imwrite(str(output_png), image)


def test_dataset_build_packages_both_tasks(tmp_path: Path) -> None:
    config = DatasetBuildConfig(
        project_seed=9,
        scene_seed_start=20,
        scene_count=3,
        variants=(AugmentationProfile.CLEAN,),
        scene=ReferenceSceneConfig(
            canvas_width_px=480,
            canvas_height_px=320,
            pixels_per_mm=0.02,
        ),
    )
    result = build_dataset(config, tmp_path / "dataset", FakeRenderer())
    assert result.sample_count == 3
    assert result.manifest.is_file()
    assert result.segmentation_yaml.is_file()
    assert result.obb_yaml.is_file()
    assert len(list((result.root / "segment" / "labels").rglob("*.txt"))) == 3
    assert len(list((result.root / "obb" / "labels").rglob("*.txt"))) == 3
    assert not (result.root / ".staging").exists()

