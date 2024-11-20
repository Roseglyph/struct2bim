"""Leak-free deterministic grouping of scene variants into dataset splits."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from enum import StrEnum
from collections.abc import Mapping
from typing import Protocol, Sequence, TypeVar

from pydantic import model_validator

from struct2bim.domain.errors import DatasetSplitLeakageError
from struct2bim.domain.geometry import DomainModel


class DatasetSplit(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class SplitRatios(DomainModel):
    train: float = 0.8
    validation: float = 0.1
    test: float = 0.1

    @model_validator(mode="after")
    def validate_sum(self) -> SplitRatios:
        if any(value < 0 for value in (self.train, self.validation, self.test)):
            raise ValueError("split ratios cannot be negative")
        if abs(self.train + self.validation + self.test - 1.0) > 1e-9:
            raise ValueError("split ratios must sum to one")
        return self


class SceneVariant(Protocol):
    scene_seed: int


VariantT = TypeVar("VariantT", bound=SceneVariant)


def _stable_score(scene_seed: int, project_seed: int) -> float:
    digest = hashlib.sha256(f"{project_seed}:{scene_seed}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big") / (2**64)


def assign_grouped_splits(
    records: Sequence[VariantT],
    *,
    project_seed: int,
    ratios: SplitRatios | None = None,
) -> dict[DatasetSplit, tuple[VariantT, ...]]:
    """Assign every variant of a scene seed to exactly one stable split."""

    resolved = ratios or SplitRatios()
    grouped: dict[int, list[VariantT]] = defaultdict(list)
    for record in records:
        grouped[record.scene_seed].append(record)

    result: dict[DatasetSplit, list[VariantT]] = {split: [] for split in DatasetSplit}
    active = [
        (DatasetSplit.TRAIN, resolved.train),
        (DatasetSplit.VALIDATION, resolved.validation),
        (DatasetSplit.TEST, resolved.test),
    ]
    active = [(split, ratio) for split, ratio in active if ratio > 0]
    ranked_seeds = sorted(grouped, key=lambda seed: (_stable_score(seed, project_seed), seed))
    total = len(ranked_seeds)
    counts = {split: int(total * ratio) for split, ratio in active}
    if total >= len(active):
        for split, _ in active:
            counts[split] = max(1, counts[split])
    while sum(counts.values()) < total:
        split = max(active, key=lambda item: (item[1] * total - counts[item[0]], item[1]))[0]
        counts[split] += 1
    while sum(counts.values()) > total:
        candidates = [(split, ratio) for split, ratio in active if counts[split] > 1]
        split = min(candidates, key=lambda item: (item[1] * total - counts[item[0]], item[1]))[0]
        counts[split] -= 1

    cursor = 0
    for split, _ in active:
        for scene_seed in ranked_seeds[cursor : cursor + counts[split]]:
            result[split].extend(sorted(grouped[scene_seed], key=lambda item: repr(item)))
        cursor += counts[split]
    return {split: tuple(items) for split, items in result.items()}


def validate_no_split_leakage(
    assignments: Mapping[DatasetSplit, Sequence[SceneVariant]],
) -> None:
    seen: dict[int, DatasetSplit] = {}
    for split, records in assignments.items():
        for record in records:
            previous = seen.setdefault(record.scene_seed, split)
            if previous != split:
                raise DatasetSplitLeakageError(
                    f"scene seed {record.scene_seed} appears in {previous} and {split}"
                )
