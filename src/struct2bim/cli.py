"""Command-line entry point."""

from pathlib import Path

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


if __name__ == "__main__":
    app()
