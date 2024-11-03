"""Command-line entry point."""

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


if __name__ == "__main__":
    app()
