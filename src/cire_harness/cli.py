import typer

from cire_harness import __version__

app = typer.Typer(no_args_is_help=True)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"cire {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=version_callback, is_eager=True, help="Show version"
    ),
) -> None:
    pass
