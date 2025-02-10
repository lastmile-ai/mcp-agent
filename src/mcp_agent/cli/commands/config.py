import typer

app = typer.Typer()


@app.command()
def show():
    """Show the configuration."""
    raise NotImplementedError("The show configuration command has not been implemented yet")