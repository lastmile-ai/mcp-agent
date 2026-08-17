import subprocess
import sys


def test_module_is_importable_on_its_own():
    """The serializer must not require the logging transport to be imported first."""
    subprocess.run(
        [sys.executable, "-c", "import mcp_agent.logging.json_serializer"],
        check=True,
    )
