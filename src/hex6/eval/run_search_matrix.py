"""CLI entry point for search variant comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import traceback

from hex6.eval.search_matrix import load_search_matrix, run_search_variant_matrix
from hex6.integration import build_status_publisher


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Hex6 search variant matrix.")
    parser.add_argument(
        "--matrix",
        default="configs/experiments/search_matrix.toml",
        help="Path to the matrix TOML file.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/search_matrix",
        help="Directory where experiment results will be written.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Explicit run id for status publishing.",
    )
    parser.add_argument(
        "--status-backend",
        default=None,
        help="Override the configured status backend.",
    )
    args = parser.parse_args()

    spec = load_search_matrix(args.matrix)
    status = build_status_publisher(
        spec.base_config,
        config_path=str(spec.base_path),
        output_dir=args.output,
        run_id=args.run_id,
        backend_override=args.status_backend,
    )
    print(
        json.dumps(
            {
                "run_id": status.run_id,
                "status_backend": status.backend,
                "status_target": status.target_description(),
            },
            indent=2,
        )
    )
    if status.enabled:
        status.publish(
            {
                "stage": "starting",
                "matrix_path": args.matrix,
                "base_config": str(spec.base_path),
                "variant_count": len(spec.variants),
                "games_per_match": spec.games,
            }
        )
    try:
        summary = run_search_variant_matrix(
            args.matrix,
            output_dir=args.output,
            progress_callback=status.publish if status.enabled else None,
        )
    except Exception as exc:
        if status.enabled:
            status.publish(
                {
                    "stage": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
        raise

    if status.enabled:
        best = summary["results"][0] if summary["results"] else None
        payload: dict[str, object] = {
            "stage": "complete",
            "matrix_path": args.matrix,
            "summary_path": str((Path(args.output) / "summary.json").resolve()),
            "best_variant": summary["best_variant"],
            "variant_count": len(summary["results"]),
            "games_per_match": summary["games_per_match"],
            "opening_suite_size": summary["opening_suite_size"],
        }
        if best is not None:
            payload["best_elo_delta"] = best["elo_delta"]
            payload["best_win_rate"] = best["win_rate"]
        status.publish(payload)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
