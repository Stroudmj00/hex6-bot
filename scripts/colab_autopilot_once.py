"""Submit one Colab autopilot cycle request and execute one worker pass."""

from __future__ import annotations

import json
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
    request = peek_next_job_request(config)
    submitted_request_id: str | None = None
    if request is None:
        submitted_request_id = generate_request_id("cycle")
        submit_job_request(
            config,
            request_id=submitted_request_id,
            kind="cycle",
            priority=90,
            notes="One-hour strongest-v2 cycle from the temporary Colab autopilot branch without a seed checkpoint.",
            options={
                "config": "configs/colab_strongest_v2.toml",
                "output_root": "artifacts/bootstrap_colab_strongest_v2",
                "minutes": 60.0,
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
        worker_id="colab-g4-01",
        status_backend="none",
        once=True,
    )


if __name__ == "__main__":
    main()
