from mcp_agent.console import console, error_console


class Application:
    def __init__(self, verbosity: int = 0, enable_color: bool = True):
        self.verbosity = verbosity
        # Use the central console instances, respecting color setting
        if not enable_color:
            # Create new instances without color if color is disabled
            self.console = console.__class__(color_system=None)
            self.error_console = error_console.__class__(color_system=None, stderr=True)
        else:
            self.console = console
            self.error_console = error_console

    def log(self, message: str, level: str = "info"):
        if level == "info" or (level == "debug" and self.verbosity > 0):
            if level == "error":
                self.error_console.print(f"[{level.upper()}] {message}")
            else:
                self.console.print(f"[{level.upper()}] {message}")

    def status(self, message: str):
        return self.console.status(f"[bold cyan]{message}[/bold cyan]")