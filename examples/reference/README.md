# Verified reference artifacts

These small committed files let reviewers inspect the pipeline without generating the full dataset.

- `structural_scene.json`: canonical metric source of truth.
- `model.dxf`: millimetre CAD interchange with column, grid, and label layers.
- `model.ifc`: deterministic IFC4 spatial model with columns, grid, and provenance properties.
- `verification_report.json`: actual reopen counts and artifact hashes from the showcase command.
- `dataset_sample/`: one generated image with segmentation/OBB labels, semantic/instance masks, and augmentation metadata.

The sample is synthetic ground truth. It is not the output of a trained detector.
