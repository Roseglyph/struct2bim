from struct2bim.curriculum import (
    ReferenceSceneConfig,
    SampleRecord,
    SplitRatios,
    assign_grouped_splits,
    build_manifest,
    generate_reference_scene,
)
from struct2bim.curriculum.splits import DatasetSplit, validate_no_split_leakage
from struct2bim.domain import ColumnShape


def _record(sample_id: str, scene_seed: int, variant: str) -> SampleRecord:
    return SampleRecord(
        sample_id=sample_id,
        scene_seed=scene_seed,
        variant=variant,
        image_path=f"images/{sample_id}.png",
        segmentation_label_path=f"labels_seg/{sample_id}.txt",
        obb_label_path=f"labels_obb/{sample_id}.txt",
        entity_counts={"column_rectangular": 3, "column_circular": 1},
    )


def test_reference_scene_is_deterministic_and_seed_sensitive() -> None:
    first = generate_reference_scene(101)
    repeated = generate_reference_scene(101)
    different = generate_reference_scene(102)

    assert first == repeated
    assert first.sha256 == repeated.sha256
    assert first.sha256 != different.sha256


def test_reference_scene_has_grid_and_column_curriculum_coverage() -> None:
    config = ReferenceSceneConfig(columns_x=4, columns_y=3)
    scene = generate_reference_scene(22, config)

    assert len(scene.grids) == 7
    assert len(scene.entities) == 12
    assert {entity.subtype for entity in scene.entities} == {
        ColumnShape.RECTANGULAR,
        ColumnShape.CIRCULAR,
    }
    assert any(entity.rotation_deg not in (0, 90) for entity in scene.entities)
    assert all(entity.storey_id == "L01" for entity in scene.entities)


def test_all_reference_footprints_project_inside_canvas() -> None:
    scene = generate_reference_scene(91)
    for entity in scene.entities:
        polygon = scene.transform.polygon_to_image(entity.footprint())
        min_x, min_y, max_x, max_y = polygon.bounds
        assert 0 <= min_x <= max_x <= scene.source.width_px
        assert 0 <= min_y <= max_y <= scene.source.height_px


def test_grouped_split_keeps_variants_together() -> None:
    records = [
        _record(f"scene-{seed}-{variant}", seed, variant)
        for seed in range(20)
        for variant in ("clean", "scan", "perspective")
    ]
    assignments = assign_grouped_splits(records, project_seed=90210)

    validate_no_split_leakage(assignments)
    location = {
        record.scene_seed: split
        for split, split_records in assignments.items()
        for record in split_records
    }
    assert len(location) == 20
    assert sum(len(items) for items in assignments.values()) == 60
    assert set(assignments) == set(DatasetSplit)


def test_manifest_is_deterministic_and_counts_artifacts() -> None:
    records = [_record("a", 1, "clean"), _record("b", 1, "scan"), _record("c", 2, "clean")]

    first = build_manifest(records, project_seed=7, config_payload="sample_count: 3")
    second = build_manifest(records, project_seed=7, config_payload="sample_count: 3")

    assert first == second
    assert first.sha256 == second.sha256
    assert sum(first.sample_counts_by_split.values()) == 3
    assert first.entity_counts_by_class == {
        "column_circular": 3,
        "column_rectangular": 9,
    }
    seeds_to_splits = {(sample.scene_seed, sample.split) for sample in first.samples}
    assert len({split for seed, split in seeds_to_splits if seed == 1}) == 1


def test_custom_split_ratios_are_respected_at_boundaries() -> None:
    records = [_record(str(seed), seed, "clean") for seed in range(30)]
    assignments = assign_grouped_splits(
        records,
        project_seed=5,
        ratios=SplitRatios(train=0.0, validation=0.0, test=1.0),
    )

    assert not assignments[DatasetSplit.TRAIN]
    assert not assignments[DatasetSplit.VALIDATION]
    assert len(assignments[DatasetSplit.TEST]) == 30


def test_small_curriculum_populates_every_enabled_split() -> None:
    records = [_record(str(seed), seed, "clean") for seed in range(12)]
    assignments = assign_grouped_splits(records, project_seed=24017)

    assert all(assignments[split] for split in DatasetSplit)
    assert sum(len(items) for items in assignments.values()) == 12
