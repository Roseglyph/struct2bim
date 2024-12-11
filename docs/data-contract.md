# Data contract

## Canonical scene

`StructuralScene` is the exchange format between generation, inference, validation, and CAD/BIM exporters. It records:

- project and source identity;
- image dimensions and scene seed;
- reversible pixel-to-millimetre transform and scale source;
- storeys and grid axes;
- structural entities with shape, centre, dimensions, rotation, class, label, confidence, and provenance.

Synthetic truth uses confidence `1.0` and `synthetic_ground_truth`. Inference outputs use `model_prediction` plus checkpoint identity and returned confidence.

## Dataset manifest

`manifest.json` records every sample, its underlying `scene_seed`, augmentation profile, split, image/label paths, rich artifact paths, class counts, and hashes. Split grouping occurs at the scene level; visual variants can never cross splits.

## Labels and masks

- Segmentation: `class x1 y1 ... xn yn`, normalized to image dimensions.
- OBB: `class x1 y1 x2 y2 x3 y3 x4 y4`, normalized.
- Semantic mask: background `0`; detector class IDs offset by one.
- Instance mask: background `0`; positive values identify instances within a sample.

## Scale and IFC

Synthetic and CAD scenes carry known metric scale. Raster predictions remain pixel-space results until a declared or measured scale is provided. The inference command therefore creates IFC only with `--mm-per-pixel`.
