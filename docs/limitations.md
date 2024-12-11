# Limitations and non-claims

- No custom detector weights or measured detector performance are included.
- Showcase overlays are synthetic ground truth, never predictions.
- The initial trainable ontology covers rectangular and circular structural columns. Other generated drafting elements are context/metadata.
- Input DXF rendering supports common `LINE`, `LWPOLYLINE`, and `CIRCLE` geometry. Complex blocks, hatches, dimensions, layouts, external references, and custom entities require future adapters.
- DWG is not read or written directly. Convert it to DXF or PDF with a trusted CAD tool and inspect conversion fidelity.
- PDF/image prediction cannot yield metric BIM safely without calibration.
- IFC output is programmatically reopened with IfcOpenShell. An independent viewer check is still recommended before publication or downstream exchange.
- Generated dimensions and layouts are demonstrative data-generation rules, not code compliance, structural design, or construction advice.
- Optional Ultralytics training is local and resumable, but has not been run in this repository; compatibility must be verified with the user-selected hardware and checkpoint.
