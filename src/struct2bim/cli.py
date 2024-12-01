"""Command-line entry point."""

from pathlib import Path
import json

import typer

app = typer.Typer(no_args_is_help=True, help="Struct2BIM project tools.")


@app.callback()
def main() -> None:
    """Run Struct2BIM project tools."""


@app.command()
def version() -> None:
    """Print the package version."""
    from struct2bim import __version__

    typer.echo(__version__)


@app.command()
def train(
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False),
) -> None:
    """Start or resume an optional local model-training run."""
    from struct2bim.training import TrainingDependencyError, run_training

    try:
        run_directory = run_training(config, Path.cwd())
    except TrainingDependencyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Training run directory: {run_directory}")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _blender_runner() -> object:
    from struct2bim.rendering import BlenderRunner, BlenderToolConfig

    root = _project_root()
    return BlenderRunner(BlenderToolConfig.discover(root), root)


@app.command()
def generate(
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False),
    output: Path = typer.Option(Path("outputs/dataset"), "--output"),
) -> None:
    """Generate a YOLO-ready synthetic dataset with exact annotations."""
    from struct2bim.application import DatasetBuildConfig, build_dataset

    build_config = DatasetBuildConfig.from_yaml(config)
    result = build_dataset(build_config, output, _blender_runner())  # type: ignore[arg-type]
    typer.echo(f"Generated {result.sample_count} samples at {result.root.resolve()}")
    typer.echo(f"Manifest: {result.manifest.resolve()}")


@app.command()
def showcase(
    output: Path = typer.Option(Path("outputs/showcase"), "--output"),
    seed: int = typer.Option(24017, "--seed"),
) -> None:
    """Build the verified synthetic-ground-truth-to-IFC showcase."""
    from struct2bim.curriculum import ReferenceSceneConfig, generate_reference_scene
    from struct2bim.exporters import export_dxf, export_ifc, validate_ifc_file
    from struct2bim.showcase import build_showcase
    from struct2bim.validation import validate_scene

    output.mkdir(parents=True, exist_ok=True)
    scene = generate_reference_scene(
        seed,
        ReferenceSceneConfig(
            canvas_width_px=1600,
            canvas_height_px=1200,
            pixels_per_mm=0.08,
            margin_mm=900,
        ),
    )
    scene_report = validate_scene(scene)
    if not scene_report.is_valid:
        raise typer.BadParameter("Generated canonical scene failed validation")
    scene_path = output / "structural_scene.json"
    scene_path.write_text(scene.canonical_json(), encoding="utf-8", newline="\n")
    dxf_path = export_dxf(scene, output / "model.dxf")
    ifc_path = export_ifc(scene, output / "model.ifc")
    ifc_report = validate_ifc_file(ifc_path, expected_scene=scene)
    if not ifc_report.is_valid:
        raise typer.BadParameter("Generated IFC failed reopen validation")
    artifacts = build_showcase(scene, ifc_path, output, _blender_runner(), seed=seed)  # type: ignore[arg-type]
    report = {
        "scene_valid": scene_report.is_valid,
        "scene_warnings": [issue.message for issue in scene_report.warnings],
        "ifc_valid": ifc_report.is_valid,
        "ifc_counts": ifc_report.counts,
        "dxf": dxf_path.name,
        "ifc": ifc_path.name,
        "hero": artifacts.hero.name,
        "provenance": "synthetic_ground_truth",
        "model_predictions_included": False,
    }
    (output / "verification_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8", newline="\n"
    )
    typer.echo(f"Showcase generated at {output.resolve()}")
    typer.echo(f"Hero: {artifacts.hero.resolve()}")


@app.command("export")
def export_scene(
    scene: Path = typer.Option(..., "--scene", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output"),
) -> None:
    """Export canonical scene JSON to IFC or DXF based on the output suffix."""
    from struct2bim.domain import StructuralScene
    from struct2bim.exporters import export_dxf, export_ifc

    canonical = StructuralScene.model_validate_json(scene.read_text(encoding="utf-8"))
    suffix = output.suffix.lower()
    if suffix == ".ifc":
        export_ifc(canonical, output)
    elif suffix == ".dxf":
        export_dxf(canonical, output)
    else:
        raise typer.BadParameter("Output must use .ifc or .dxf")
    typer.echo(f"Exported: {output.resolve()}")


@app.command("validate-ifc")
def validate_ifc(path: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Reopen an IFC and report its structural contents."""
    from struct2bim.exporters import validate_ifc_file

    result = validate_ifc_file(path)
    typer.echo(json.dumps({"valid": result.is_valid, "errors": result.errors, "counts": result.counts}, indent=2))
    if not result.is_valid:
        raise typer.Exit(code=1)


@app.command("validate-dataset")
def validate_dataset_command(
    dataset: Path = typer.Option(..., "--dataset", exists=True, file_okay=False),
) -> None:
    """Validate generated images, labels, manifest and leak-free splits."""
    from struct2bim.validation import validate_dataset

    result = validate_dataset(dataset)
    typer.echo(result.model_dump_json(indent=2))
    if not result.valid:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
