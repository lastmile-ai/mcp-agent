"""Test event progress conversion from log events."""

import subprocess
from pathlib import Path
from rich import print


def test_event_conversion():
    """Test conversion of log events to progress events using gold master approach."""
    # Get the paths
    log_file = str(
        Path(__file__).parent / "fixture" / "mcp_basic_agent_20250131_205604.jsonl"
    )
    expected_output_file = Path(__file__).parent / "fixture" / "expected_output.txt"

    # Run the event_summary script to get current output
    result = subprocess.run(
        ["uv", "run", "python3", "scripts/event_summary.py", log_file],
        capture_output=True,
        text=True,
    )
    current_output = result.stdout

    # Load expected output
    with open(expected_output_file) as f:
        expected_output = f.read()

    # Compare outputs
    assert current_output.strip() == expected_output.strip(), (
        "Event summary output does not match expected output"
    )


def update_test_fixtures():
    """
    Utility method to update test fixtures with latest output.
    This should only be run manually when intentionally updating the expected behavior.

    Usage:
        python3 -c "from tests.test_event_progress import update_test_fixtures; update_test_fixtures()"
    """
    # Paths
    fixture_dir = Path(__file__).parent / "fixture"
    log_file = fixture_dir / "mcp_basic_agent_20250131_205604.jsonl"
    expected_output_file = fixture_dir / "expected_output.txt"

    if not log_file.exists():
        print(f"Log file not found: {log_file}")
        print(
            "Please run an example to generate a log file and copy it to the fixture directory"
        )
        return

    # Run command and capture output
    result = subprocess.run(
        ["uv", "run", "python3", "scripts/event_summary.py", str(log_file)],
        capture_output=True,
        text=True,
        check=True,
    )

    # Update expected output file
    with open(expected_output_file, "w") as f:
        f.write(result.stdout)

    print(f"Updated test fixtures:\n- {expected_output_file}")


if __name__ == "__main__":
    test_event_conversion()
