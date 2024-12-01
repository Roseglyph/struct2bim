from pathlib import Path

from struct2bim.curriculum import SampleRecord, build_manifest
from struct2bim.validation import validate_dataset


def test_dataset_validator_checks_pairs_labels_and_splits(tmp_path: Path) -> None:
    records = []
    for index, split_seed in enumerate((1, 2, 3)):
        sample_id = f"sample-{index}"
        image = tmp_path / "artifacts" / "images" / "train" / f"{sample_id}.png"
        segment = tmp_path / "segment" / "labels" / "train" / f"{sample_id}.txt"
        obb = tmp_path / "obb" / "labels" / "train" / f"{sample_id}.txt"
        image.parent.mkdir(parents=True, exist_ok=True)
        segment.parent.mkdir(parents=True, exist_ok=True)
        obb.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"png")
        segment.write_text("0 0.1 0.1 0.2 0.1 0.2 0.2\n", encoding="utf-8")
        obb.write_text("0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2\n", encoding="utf-8")
        records.append(
            SampleRecord(
                sample_id=sample_id,
                scene_seed=split_seed,
                variant="clean",
                image_path=image.relative_to(tmp_path).as_posix(),
                segmentation_label_path=segment.relative_to(tmp_path).as_posix(),
                obb_label_path=obb.relative_to(tmp_path).as_posix(),
                entity_counts={"column_rectangular": 1},
            )
        )
    manifest = build_manifest(records, project_seed=7, config_payload="test")
    (tmp_path / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")

    report = validate_dataset(tmp_path)

    assert report.valid
    assert report.sample_count == 3
    assert report.checked_label_files == 6
