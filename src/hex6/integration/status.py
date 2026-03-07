"""Explicit status bridge between local tooling and remote training runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import base64
import json
import os
import shutil
import socket
import subprocess
import urllib.error
import urllib.request

from hex6.config import AppConfig

TERMINAL_STAGES = frozenset({"complete", "failed"})


@dataclass(frozen=True)
class RunContext:
    run_id: str
    project_name: str
    phase: str
    config_path: str
    output_dir: str
    backend: str
    host: str
    started_at: str


class StatusTransport:
    def write_json(self, path: str, payload: dict[str, object], message: str) -> None:
        raise NotImplementedError

    def read_json(self, path: str) -> dict[str, object] | None:
        raise NotImplementedError


class NullStatusPublisher:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.backend = "none"
        self.enabled = False

    def publish(self, payload: dict[str, object]) -> dict[str, object]:
        return payload

    def target_description(self) -> str:
        return "disabled"


class StatusPublisher:
    def __init__(
        self,
        transport: StatusTransport,
        context: RunContext,
        latest_path: str,
        run_history_path: str,
    ) -> None:
        self._transport = transport
        self._context = context
        self._latest_path = _normalize_repo_path(latest_path)
        self._run_history_path = _normalize_repo_path(run_history_path)
        self._sequence = 0
        self.run_id = context.run_id
        self.backend = context.backend
        self.enabled = True

    def publish(self, payload: dict[str, object]) -> dict[str, object]:
        self._sequence += 1
        document = {
            "run_id": self._context.run_id,
            "project": self._context.project_name,
            "phase": self._context.phase,
            "config_path": self._context.config_path,
            "output_dir": self._context.output_dir,
            "status_backend": self._context.backend,
            "host": self._context.host,
            "started_at": self._context.started_at,
            "updated_at": _utc_now(),
            "sequence": self._sequence,
            **payload,
        }
        message = (
            f"hex6 status {self._context.run_id} "
            f"{document.get('stage', 'update')} #{self._sequence}"
        )
        self._transport.write_json(self._latest_path, document, message)
        self._transport.write_json(self._history_path(), document, message)
        return document

    def target_description(self) -> str:
        return f"{self.backend}:{self._latest_path}"

    def _history_path(self) -> str:
        return _normalize_repo_path(f"{self._run_history_path}/{self._context.run_id}.json")


class FileStatusTransport(StatusTransport):
    def __init__(self, root: Path) -> None:
        self._root = root

    def write_json(self, path: str, payload: dict[str, object], message: str) -> None:
        del message
        target = self._root / Path(PurePosixPath(path))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="ascii")

    def read_json(self, path: str) -> dict[str, object] | None:
        target = self._root / Path(PurePosixPath(path))
        if not target.exists():
            return None
        return json.loads(target.read_text(encoding="ascii"))


class GitHubBranchTransport(StatusTransport):
    def __init__(
        self,
        repo: str,
        branch: str,
        base_branch: str,
        token: str,
    ) -> None:
        self._repo = repo
        self._branch = branch
        self._base_branch = base_branch
        self._token = token
        self._branch_checked = False

    def write_json(self, path: str, payload: dict[str, object], message: str) -> None:
        self._ensure_branch_exists()
        path = _normalize_repo_path(path)
        existing = self._get_contents(path)
        body = {
            "message": message,
            "content": base64.b64encode(json.dumps(payload, indent=2).encode("ascii")).decode("ascii"),
            "branch": self._branch,
        }
        if existing is not None and "sha" in existing:
            body["sha"] = existing["sha"]
        self._api_json(
            f"https://api.github.com/repos/{self._repo}/contents/{path}",
            method="PUT",
            payload=body,
        )

    def read_json(self, path: str) -> dict[str, object] | None:
        contents = self._get_contents(path)
        if contents is None:
            return None
        encoded = contents["content"].replace("\n", "")
        return json.loads(base64.b64decode(encoded).decode("ascii"))

    def _ensure_branch_exists(self) -> None:
        if self._branch_checked:
            return
        ref_url = f"https://api.github.com/repos/{self._repo}/git/ref/heads/{self._branch}"
        try:
            self._api_json(ref_url, method="GET")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            base_ref = self._api_json(
                f"https://api.github.com/repos/{self._repo}/git/ref/heads/{self._base_branch}",
                method="GET",
            )
            self._api_json(
                f"https://api.github.com/repos/{self._repo}/git/refs",
                method="POST",
                payload={
                    "ref": f"refs/heads/{self._branch}",
                    "sha": base_ref["object"]["sha"],
                },
            )
        self._branch_checked = True

    def _get_contents(self, path: str) -> dict[str, object] | None:
        path = _normalize_repo_path(path)
        try:
            return self._api_json(
                f"https://api.github.com/repos/{self._repo}/contents/{path}?ref={self._branch}",
                method="GET",
            )
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def _api_json(
        self,
        url: str,
        method: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "hex6-status-bridge",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


def build_status_publisher(
    config: AppConfig,
    *,
    config_path: str,
    output_dir: str,
    run_id: str | None = None,
    backend_override: str | None = None,
) -> NullStatusPublisher | StatusPublisher:
    backend = backend_override or config.integration.status_backend
    run_id = run_id or generate_run_id()
    if backend == "none":
        return NullStatusPublisher(run_id)

    context = RunContext(
        run_id=run_id,
        project_name=config.project.name,
        phase=config.project.phase,
        config_path=config_path,
        output_dir=output_dir,
        backend=backend,
        host=socket.gethostname(),
        started_at=_utc_now(),
    )

    if backend == "file":
        transport = FileStatusTransport(Path.cwd())
    elif backend == "github_branch":
        token = resolve_github_token(require=True)
        transport = GitHubBranchTransport(
            repo=config.integration.github_repo,
            branch=config.integration.github_branch,
            base_branch=config.integration.github_base_branch,
            token=token,
        )
    else:
        raise ValueError(f"unsupported status backend: {backend}")

    return StatusPublisher(
        transport=transport,
        context=context,
        latest_path=config.integration.status_path,
        run_history_path=config.integration.run_history_path,
    )


def fetch_status(
    config: AppConfig,
    *,
    run_id: str = "latest",
    backend_override: str | None = None,
) -> dict[str, object] | None:
    backend = backend_override or config.integration.status_backend
    if backend == "none":
        return None

    target_path = _resolve_status_path(config, run_id)
    if backend == "file":
        return FileStatusTransport(Path.cwd()).read_json(target_path)
    if backend == "github_branch":
        token = resolve_github_token(require=True)
        transport = GitHubBranchTransport(
            repo=config.integration.github_repo,
            branch=config.integration.github_branch,
            base_branch=config.integration.github_base_branch,
            token=token,
        )
        return transport.read_json(target_path)
    raise ValueError(f"unsupported status backend: {backend}")


def resolve_github_token(require: bool) -> str | None:
    for env_name in ("HEX6_GITHUB_TOKEN", "GITHUB_TOKEN"):
        token = os.environ.get(env_name)
        if token:
            return token

    gh_path = _find_gh_cli()
    if gh_path is not None:
        result = subprocess.run(
            [gh_path, "auth", "token"],
            capture_output=True,
            text=True,
            check=False,
        )
        token = result.stdout.strip()
        if result.returncode == 0 and token:
            return token

    if require:
        raise RuntimeError(
            "GitHub token not available. Set HEX6_GITHUB_TOKEN in Colab or authenticate gh locally."
        )
    return None


def generate_run_id(prefix: str = "colab") -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}"


def _resolve_status_path(config: AppConfig, run_id: str) -> str:
    if run_id == "latest":
        return _normalize_repo_path(config.integration.status_path)
    return _normalize_repo_path(f"{config.integration.run_history_path}/{run_id}.json")


def _normalize_repo_path(path: str) -> str:
    return PurePosixPath(path).as_posix().lstrip("/")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _find_gh_cli() -> str | None:
    gh_path = shutil.which("gh")
    if gh_path is not None:
        return gh_path

    windows_candidates = (
        r"C:\Program Files\GitHub CLI\gh.exe",
        r"C:\Program Files (x86)\GitHub CLI\gh.exe",
    )
    for candidate in windows_candidates:
        if Path(candidate).exists():
            return candidate
    return None
