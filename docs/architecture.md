# Architecture

Struct2BIM separates semantic truth, appearance, prediction, and BIM export so no raster-processing shortcut becomes authoritative geometry.

```text
curriculum --> StructuralScene --> Blender renderer --> clean drawing
                     |                    |
                     |                    `--> 2D augmentation --> images
                     `--> annotations -------- homography ------> labels/masks
                     `--> DXF exporter
                     `--> IFC4 exporter --> IfcOpenShell reopen validation

input adapter --> supplied checkpoint --> predictions.json
                                      `--> scale calibration --> StructuralScene --> IFC4
```

## Boundaries

- `domain/`: immutable metric geometry, entities, provenance, transforms, and canonical scene schema.
- `curriculum/`: deterministic layout generation, manifest records, and leak-free grouped splitting.
- `annotations/`: exact segmentation and OBB exports derived from scene truth.
- `augmentation/`: scan/perspective raster transformations and matching annotation homographies. Blender does not simulate phone photographs.
- `application/`: transactional dataset orchestration, masks, metadata, hashes, and task packaging.
- `inputs.py`: image/PDF normalization and basic DXF rasterization; DWG rejects explicitly.
- `training/`: lazy optional Ultralytics integration for train/resume/evaluate/infer.
- `exporters/`: DXF and deterministic IFC4 creation plus reopen checks.
- `rendering/` and `showcase/`: isolated headless Blender execution and truthful portfolio visuals.

The drawing context is sampled independently from the column ontology. Footing outlines,
tie and grade beams, hatching, labels, dimensions, intersections, missing grid positions,
and line-style changes act as non-target drafting context. The column polygons remain the
source of truth for segmentation and oriented-box labels.

## Coordinate contract

World geometry uses millimetres with positive Y upward. Images use top-left origin pixels with positive Y downward. `CoordinateTransform` provides reversible mapping. The Blender orthographic camera reads that exact transform; it does not independently reframe the model. Each document augmentation returns a 3x3 homography, applied to both the image and exact annotation polygons.

IFC and DXF are downstream representations of canonical geometry. Detector boxes are never treated as BIM geometry without polygon/OBB conversion and scale calibration.
