"""Record a py-spy profile for a Hex6 command."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile a Hex6 command with py-spy.")
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for the profile file, for example artifacts/profiles/fast_bootstrap.svg",
    )
    parser.add_argument(
        "--format",
        default="speedscope",
        choices=("flamegraph", "raw", "speedscope"),
        help="py-spy output format.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to profile. Prefix with -- to separate wrapper args from the profiled command.",
    )
    args = parser.parse_args()

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("provide a command to profile after --")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    py_spy = Path(sys.executable).with_name("py-spy.exe")
    if not py_spy.exists():
        raise FileNotFoundError(f"py-spy executable not found next to interpreter: {py_spy}")

    wrapped = [
        str(py_spy),
        "record",
        "-o",
        str(output_path),
        "--format",
        args.format,
        "--",
        *command,
    ]
    print("profiling:", " ".join(wrapped))
    completed = subprocess.run(wrapped, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
