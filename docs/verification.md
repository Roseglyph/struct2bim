# Verification record

This record describes the checks performed on the committed portfolio state. It is evidence for the implemented non-training pipeline, not a detector benchmark.

## Automated quality gates

| Gate | Result |
|---|---:|
| pytest | 61 tests passed |
| Ruff | passed |
| strict mypy | passed |
| dependency lock | resolved successfully |
| base environment | Python 3.11.11 and Blender verified |
| release audit | passed |

Run the same gates locally:

```powershell
python -m pytest
ruff check .
mypy src scripts
struct2bim doctor
python scripts/release_audit.py
```

The exact test count may increase as the project evolves; a successful command result remains authoritative.

## Generated dataset acceptance

The reference configuration was generated through the real Blender and augmentation pipeline:

- 12 underlying scenes;
- 36 image variants;
- 30 train, 3 validation, and 3 test samples;
- 72 YOLO label files checked;
- scene variants grouped without split leakage;
- all normalized coordinates inside `[0, 1]`;
- every declared image, label, mask, metadata, scene, and DXF artifact present;
- recorded image/label/mask SHA-256 values verified;
- human-reviewed overlay sheet generated from the actual YOLO text files.

## Exchange-model acceptance

The committed reference IFC was reopened with IfcOpenShell and contains the expected project/site/building/storey hierarchy, 12 represented and contained columns, and one structural grid. The reference DXF was reopened with ezdxf and contains 12 columns, 7 grid axes, 12 labels, and millimetre units.

The IFC showcase image is rendered from tessellated IFC geometry and extracted IFC grid axes. Its receiving plane is presentation-only and is not described as a detected building element.

## Visual inspection

The following committed assets were opened at original resolution and checked for legibility, alignment, clipping, and truthful captions:

- `docs/assets/pipeline_overview.png`;
- `docs/assets/generator-interface.png`;
- `docs/assets/curriculum_variations.png`;
- `docs/assets/dataset_alignment_preview.png`;
- `docs/assets/ifc_isometric.png`.

Every annotation-facing public image identifies its content as synthetic ground truth. No panel is presented as a detector prediction.

## Intentionally unverified

- No YOLO training was run.
- No checkpoint was evaluated.
- No accuracy, precision, recall, mAP, or latency result is published.
- No direct DWG round trip is claimed.
- No manual independent-viewer sign-off beyond the programmatic IfcOpenShell reopen and Blender visualization is claimed.
