"""CLI entry point for the file-backed Colab autopilot broker."""

from __future__ import annotations

import argparse
import json

from hex6.integration.autopilot import (
    build_research_prompt,
    claim_next_research_idea,
    complete_research_idea,
    generate_request_id,
    list_job_requests,
    load_autopilot_config,
    load_research_backlog,
    read_research_state,
    run_worker_loop,
    submit_job_request,
)


JOB_KINDS = ("bootstrap", "cycle", "tournament", "search_matrix", "runtime_benchmark", "ladder")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_autopilot_config(args.plan)
    args.handler(args, config)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Colab job requests and research backlog for Hex6.")
    parser.add_argument(
        "--plan",
        default="configs/colab_autopilot.toml",
        help="Path to the Colab autopilot plan TOML.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    submit = subparsers.add_parser("submit", help="Submit a new Colab job request.")
    submit.add_argument("--request-id", default=None)
    submit.add_argument("--kind", required=True, choices=JOB_KINDS)
    submit.add_argument("--priority", type=int, default=50)
    submit.add_argument("--notes", default="")
    submit.add_argument("--return-policy", default="auto")
    submit.add_argument("--config", default=None)
    submit.add_argument("--output", default=None)
    submit.add_argument("--output-root", default=None)
    submit.add_argument("--minutes", type=float, default=None)
    submit.add_argument("--cycles", type=int, default=None)
    submit.add_argument("--start-checkpoint", default=None)
    submit.add_argument("--matrix", default=None)
    submit.add_argument("--manifest", default=None)
    submit.add_argument("--state", default=None)
    submit.add_argument("--ledger", default=None)
    submit.add_argument("--games-per-match", type=int, default=None)
    submit.add_argument("--max-game-plies", type=int, default=None)
    submit.add_argument("--max-checkpoints", type=int, default=None)
    submit.add_argument("--checkpoint-glob", default=None)
    submit.add_argument("--opening-suite", default=None)
    submit.add_argument("--include-baseline", action=argparse.BooleanOptionalAction, default=None)
    submit.add_argument("--include-random", action=argparse.BooleanOptionalAction, default=None)
    submit.add_argument("--random-seed", type=int, default=None)
    submit.add_argument("--max-submissions", type=int, default=None)
    submit.add_argument("--resume", action=argparse.BooleanOptionalAction, default=None)
    submit.add_argument(
        "--option",
        action="append",
        default=[],
        help="Additional request option in key=value form. May be passed multiple times.",
    )
    submit.set_defaults(handler=handle_submit)

    list_parser = subparsers.add_parser("list", help="List known Colab job requests and research status.")
    list_parser.set_defaults(handler=handle_list)

    worker = subparsers.add_parser("worker", help="Run the Colab worker loop against pending requests.")
    worker.add_argument("--repo-root", default=".")
    worker.add_argument("--python-exe", default="python")
    worker.add_argument("--worker-id", default="colab-worker-01")
    worker.add_argument("--status-backend", default=None)
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--max-jobs", type=int, default=None)
    worker.add_argument("--dry-run", action="store_true")
    worker.set_defaults(handler=handle_worker)

    research = subparsers.add_parser("next-research", help="Claim the next research idea and print a ready prompt.")
    research.add_argument("--researcher-id", default="codex-research-01")
    research.set_defaults(handler=handle_next_research)

    complete = subparsers.add_parser("complete-research", help="Mark a research idea complete.")
    complete.add_argument("--idea-id", required=True)
    complete.add_argument("--note-path", default="")
    complete.set_defaults(handler=handle_complete_research)

    return parser


def handle_submit(args: argparse.Namespace, config) -> None:
    request_id = args.request_id or generate_request_id(args.kind)
    options = _collect_request_options(args)
    path = submit_job_request(
        config,
        request_id=request_id,
        kind=args.kind,
        priority=args.priority,
        notes=args.notes,
        return_policy=args.return_policy,
        options=options,
    )
    print(
        json.dumps(
            {
                "request_id": request_id,
                "kind": args.kind,
                "priority": args.priority,
                "path": str(path),
                "options": options,
            },
            indent=2,
        )
    )


def handle_list(args: argparse.Namespace, config) -> None:
    del args
    backlog = load_research_backlog(config)
    research_state = read_research_state(config.research_state_path)
    active = research_state.get("active", {})
    completed = set(str(value) for value in research_state.get("completed", []))
    pending_ideas = [
        {
            "idea_id": idea.idea_id,
            "title": idea.title,
            "priority": idea.priority,
        }
        for idea in backlog
        if idea.idea_id not in completed and idea.idea_id not in active
    ]
    pending_ideas.sort(key=lambda item: (-item["priority"], item["idea_id"]))
    print(
        json.dumps(
            {
                "requests": list_job_requests(config),
                "research": {
                    "active": active,
                    "completed": sorted(completed),
                    "pending": pending_ideas,
                },
            },
            indent=2,
        )
    )


def handle_worker(args: argparse.Namespace, config) -> None:
    run_worker_loop(
        config,
        repo_root=args.repo_root,
        python_exe=args.python_exe,
        worker_id=args.worker_id,
        status_backend=args.status_backend,
        once=args.once,
        max_jobs=args.max_jobs,
        dry_run=args.dry_run,
    )


def handle_next_research(args: argparse.Namespace, config) -> None:
    idea = claim_next_research_idea(config, researcher_id=args.researcher_id)
    if idea is None:
        print(json.dumps({"stage": "idle", "message": "no pending research ideas"}, indent=2))
        return
    print(
        json.dumps(
            {
                "idea_id": idea.idea_id,
                "title": idea.title,
                "priority": idea.priority,
                "prompt": build_research_prompt(idea),
            },
            indent=2,
        )
    )


def handle_complete_research(args: argparse.Namespace, config) -> None:
    complete_research_idea(config, idea_id=args.idea_id, note_path=args.note_path)
    print(
        json.dumps(
            {
                "idea_id": args.idea_id,
                "note_path": args.note_path,
                "status": "completed",
            },
            indent=2,
        )
    )


def _collect_request_options(args: argparse.Namespace) -> dict[str, object]:
    options: dict[str, object] = {}
    for key in (
        "config",
        "output",
        "output_root",
        "minutes",
        "cycles",
        "start_checkpoint",
        "matrix",
        "manifest",
        "state",
        "ledger",
        "games_per_match",
        "max_game_plies",
        "max_checkpoints",
        "checkpoint_glob",
        "opening_suite",
        "include_baseline",
        "include_random",
        "random_seed",
        "max_submissions",
        "resume",
    ):
        value = getattr(args, key, None)
        if value is not None:
            options[key] = value
    for entry in args.option:
        if "=" not in entry:
            raise ValueError(f"invalid --option value, expected key=value: {entry}")
        key, raw_value = entry.split("=", 1)
        options[key.strip()] = _coerce_option_value(raw_value.strip())
    return options


def _coerce_option_value(value: str) -> object:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


if __name__ == "__main__":
    main()
