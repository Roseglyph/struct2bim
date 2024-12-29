from pathlib import Path

from struct2bim.diagnostics import DiagnosticReport


def test_diagnostic_report_keeps_optional_training_separate() -> None:
    report = DiagnosticReport(
        ready=True,
        python="3.11.11",
        blender=str(Path("blender")),
        base_dependencies={"Pillow": True},
        optional_training_dependencies={"torch": False, "ultralytics": False},
        example_ifc_valid=True,
        example_dxf_valid=True,
        notes=("optional training is absent",),
    )

    assert report.ready
    assert not any(report.optional_training_dependencies.values())
