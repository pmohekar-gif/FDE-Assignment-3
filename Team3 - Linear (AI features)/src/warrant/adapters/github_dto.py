from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GitHubRepositoryDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    full_name: str
    default_branch: str


class GitHubPullRequestDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    number: int
    html_url: str
    state: str
    draft: bool
    merged: bool
    base_ref: str
    head_sha: str
    title: str
    # PR bodies are intentionally omitted in MVP to avoid storing customer data.


class GitHubCommitDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha: str
    html_url: str
    message: str


class GitHubCheckRunDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    status: str
    conclusion: str | None = None
    started_at: str
    completed_at: str | None = None
    html_url: str


class GitHubChangedFileDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    status: str
    additions: int
    deletions: int
