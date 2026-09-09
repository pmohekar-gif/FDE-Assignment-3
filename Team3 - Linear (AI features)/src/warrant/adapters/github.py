from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from ..config import Settings
from ..service import DomainError, NotFound
from .github_dto import GitHubChangedFileDTO, GitHubCheckRunDTO, GitHubPullRequestDTO
from .github_fixture import STUB_GITHUB_CHECKS, STUB_GITHUB_FILES, STUB_GITHUB_PR

_REQUEST_TIMEOUT = 15.0
_GITHUB_API_VERSION = "2022-11-28"
_MAX_LIMIT = 100


class AdapterConfigError(DomainError):
    """Raised when the GitHub adapter is called but not properly configured."""

    status_code = 503


class GitHubRequestError(DomainError):
    """Raised when a caller supplies an invalid GitHub lookup parameter."""

    status_code = 422


class GitHubNotFoundError(NotFound):
    """Raised when the requested GitHub resource does not exist."""


class GitHubAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def source(self) -> str:
        return "github-stub" if self._settings.github_stub_mode else "github"

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _GITHUB_API_VERSION,
        }
        if self._settings.github_token:
            headers["Authorization"] = f"Bearer {self._settings.github_token}"
        return headers

    def _check_config(self) -> None:
        mode = self._settings.github_mode
        if mode == "off":
            raise AdapterConfigError(
                "GitHub adapter is not configured. Set GITHUB_MODE=stub or GITHUB_MODE=live."
            )
        if mode not in {"stub", "live"}:
            raise AdapterConfigError(
                f"Unknown GITHUB_MODE={mode!r}. Must be 'off', 'stub', or 'live'."
            )
        if mode == "live" and not self._settings.github_token:
            raise AdapterConfigError("GITHUB_MODE=live requires GITHUB_TOKEN to be set.")
        if mode == "live":
            self._validated_base_url()

    def _validated_base_url(self) -> str:
        raw = self._settings.github_api_base_url.rstrip("/")
        parsed = urlparse(raw)
        if parsed.scheme != "https" or not parsed.netloc:
            raise AdapterConfigError("GITHUB_API_BASE_URL must be an https URL.")
        host = parsed.hostname or ""
        if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
            raise AdapterConfigError("GITHUB_API_BASE_URL must not target a local host.")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and (address.is_private or address.is_loopback or address.is_link_local):
            raise AdapterConfigError("GITHUB_API_BASE_URL must not target a private IP address.")
        return raw

    @staticmethod
    def _safe_path_part(name: str, field: str) -> str:
        value = name.strip()
        if not value or "/" in value or "?" in value or "#" in value:
            raise GitHubRequestError(f"{field} must be a single GitHub path segment")
        return quote(value, safe="")

    @staticmethod
    def _limit(value: int) -> int:
        return min(max(int(value), 1), _MAX_LIMIT)

    def _repo_path(self, owner: str, repo: str) -> str:
        return f"repos/{self._safe_path_part(owner, 'owner')}/{self._safe_path_part(repo, 'repo')}"

    def _get_json(self, path: str, missing: str) -> Any:
        url = f"{self._validated_base_url()}/{path}"
        try:
            response = httpx.get(url, headers=self._get_headers(), timeout=_REQUEST_TIMEOUT)
            if response.status_code == 404:
                raise GitHubNotFoundError(missing)
            response.raise_for_status()
            return response.json()
        except GitHubNotFoundError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise AdapterConfigError(
                f"GitHub API request failed: {type(exc).__name__}: {exc}"
            ) from exc

    def get_pull_request(self, owner: str, repo: str, number: int) -> GitHubPullRequestDTO:
        self._check_config()
        if number < 1:
            raise GitHubRequestError("number must be greater than zero")
        if self._settings.github_stub_mode:
            data: dict[str, Any] = dict(STUB_GITHUB_PR)
            data["number"] = number
            data["html_url"] = f"https://github.com/{owner}/{repo}/pull/{number}"
        else:
            path = f"{self._repo_path(owner, repo)}/pulls/{number}"
            data = self._get_json(path, f"Pull request {owner}/{repo}#{number} not found.")

        return GitHubPullRequestDTO(
            id=int(data["id"]),
            number=int(data["number"]),
            html_url=str(data["html_url"]),
            state=str(data["state"]),
            draft=bool(data.get("draft", False)),
            merged=bool(data.get("merged", False)),
            base_ref=str(data["base"]["ref"]),
            head_sha=str(data["head"]["sha"]),
            title=str(data["title"]),
        )

    def get_pull_request_files(
        self, owner: str, repo: str, number: int, limit: int = _MAX_LIMIT
    ) -> list[GitHubChangedFileDTO]:
        self._check_config()
        if number < 1:
            raise GitHubRequestError("number must be greater than zero")
        bounded_limit = self._limit(limit)
        if self._settings.github_stub_mode:
            data: list[dict[str, Any]] = list(STUB_GITHUB_FILES)
        else:
            path = f"{self._repo_path(owner, repo)}/pulls/{number}/files?per_page={bounded_limit}"
            data = self._get_json(path, f"Pull request files {owner}/{repo}#{number} not found.")

        return [
            GitHubChangedFileDTO(
                filename=str(item["filename"]),
                status=str(item["status"]),
                additions=int(item["additions"]),
                deletions=int(item["deletions"]),
            )
            for item in data
        ][:bounded_limit]

    def get_pull_request_checks(
        self, owner: str, repo: str, ref: str, limit: int = _MAX_LIMIT
    ) -> list[GitHubCheckRunDTO]:
        self._check_config()
        safe_ref = self._safe_path_part(ref, "ref")
        bounded_limit = self._limit(limit)
        if self._settings.github_stub_mode:
            runs: list[dict[str, Any]] = list(STUB_GITHUB_CHECKS)
        else:
            path = (
                f"{self._repo_path(owner, repo)}/commits/{safe_ref}/check-runs"
                f"?per_page={bounded_limit}"
            )
            data = self._get_json(path, f"Check runs for {owner}/{repo}@{ref} not found.")
            runs = data.get("check_runs", []) if isinstance(data, dict) else []

        return [
            GitHubCheckRunDTO(
                id=int(item["id"]),
                name=str(item["name"]),
                status=str(item["status"]),
                conclusion=str(item["conclusion"]) if item.get("conclusion") else None,
                started_at=str(item["started_at"]),
                completed_at=str(item["completed_at"]) if item.get("completed_at") else None,
                html_url=str(item["html_url"]),
            )
            for item in runs
        ][:bounded_limit]
