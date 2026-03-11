"""Run the local Hex6 play server."""

from __future__ import annotations

import argparse

from hex6.web import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Hex6 play server.")
    parser.add_argument("--config", default="configs/play.toml", help="Path to the play config.")
    parser.add_argument("--checkpoint", default="", help="Optional checkpoint path for model-guided play.")
    parser.add_argument(
        "--spectator-opponent-checkpoint",
        default="",
        help="Optional checkpoint path for the O-side spectator bot. Defaults to heuristic baseline.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", default=5000, type=int, help="Port to bind.")
    args = parser.parse_args()

    app = create_app(
        args.config,
        checkpoint_path=args.checkpoint or None,
        spectator_opponent_checkpoint=args.spectator_opponent_checkpoint or None,
    )
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
