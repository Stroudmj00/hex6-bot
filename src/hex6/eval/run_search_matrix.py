"""CLI entry point for search variant comparison."""

from __future__ import annotations

import argparse
import json

from hex6.eval.search_matrix import run_search_variant_matrix


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
    args = parser.parse_args()

    summary = run_search_variant_matrix(args.matrix, output_dir=args.output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
