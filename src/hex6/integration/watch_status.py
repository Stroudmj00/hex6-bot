"""CLI to watch the explicit Colab status bridge."""

from __future__ import annotations

import argparse
import json
import time

from hex6.config import load_config
from hex6.integration.status import TERMINAL_STAGES, fetch_status


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch remote Hex6 status updates.")
    parser.add_argument(
        "--config",
        default="configs/colab.toml",
        help="Path to the TOML config file.",
    )
    parser.add_argument(
        "--run-id",
        default="latest",
        help="Run id to watch, or 'latest' to follow the latest status file.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=None,
        help="Polling interval override.",
    )
    parser.add_argument(
        "--status-backend",
        default=None,
        help="Override the configured status backend.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    poll_seconds = args.poll_seconds or config.integration.watch_poll_seconds
    last_sequence: int | None = None
    announced_wait = False

    while True:
        status = fetch_status(config, run_id=args.run_id, backend_override=args.status_backend)
        if status is None:
            if not announced_wait:
                print("Waiting for status document...")
                announced_wait = True
            time.sleep(poll_seconds)
            continue

        sequence = int(status.get("sequence", -1))
        if sequence != last_sequence:
            announced_wait = False
            print(json.dumps(status, indent=2))
            last_sequence = sequence
            stage = str(status.get("stage", ""))
            if stage in TERMINAL_STAGES:
                print("\a", end="")
                return

        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
