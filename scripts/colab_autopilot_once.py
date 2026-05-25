"""Submit one Colab autopilot cycle request and execute one worker pass."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from hex6.integration.autopilot import (
    generate_request_id,
    load_autopilot_config,
    peek_next_job_request,
    run_worker_loop,
    submit_job_request,
)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config = load_autopilot_config(repo_root / "configs" / "colab_autopilot.toml")
    cycle_config = os.environ.get("HEX6_AUTOPILOT_CYCLE_CONFIG", "configs/colab_strongest_v2_safe.toml")
    output_root = os.environ.get("HEX6_AUTOPILOT_OUTPUT_ROOT", "artifacts/bootstrap_colab_strongest_v2_safe")
    minutes = float(os.environ.get("HEX6_AUTOPILOT_MINUTES", "60"))
    worker_id = os.environ.get("HEX6_AUTOPILOT_WORKER_ID", "colab-g4-safe-01")
    request = peek_next_job_request(config)
    submitted_request_id: str | None = None
    if request is None:
        submitted_request_id = generate_request_id("cycle")
        submit_job_request(
            config,
            request_id=submitted_request_id,
            kind="cycle",
            priority=90,
            notes=(
                "One-hour safer strongest-v2 retry from the temporary Colab autopilot branch "
                "after the initial G4 launch was killed with exit code -9."
            ),
            options={
                "config": cycle_config,
                "output_root": output_root,
                "minutes": minutes,
            },
        )
    print(
        json.dumps(
            {
                "submitted_request_id": submitted_request_id,
                "next_request_id": peek_next_job_request(config).request_id if peek_next_job_request(config) else None,
                "repo_root": str(repo_root),
            },
            indent=2,
        )
    )
    run_worker_loop(
        config,
        repo_root=str(repo_root),
        python_exe=sys.executable,
        worker_id=worker_id,
        status_backend="none",
        once=True,
    )


if __name__ == "__main__":
    main()
