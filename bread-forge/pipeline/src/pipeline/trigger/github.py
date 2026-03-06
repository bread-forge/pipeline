"""GitHub trigger — polls the GitHub REST API for merged pull requests.

The module reads ``GH_TOKEN`` from the environment at call time and silently
skips all network activity when the variable is absent, so callers in
environments without credentials (e.g. unit tests) are unaffected.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime

_GH_API_BASE = "https://api.github.com"
_GH_TOKEN_ENV = "GH_TOKEN"
_REQUEST_TIMEOUT_SECONDS = 10
_PRS_PER_PAGE = 50


def _get_gh_token() -> str:
    """Return the GitHub token from the environment, or an empty string."""
    return os.environ.get(_GH_TOKEN_ENV, "")


def fetch_merged_prs(repo: str, gh_token: str, since: datetime) -> list[dict]:
    """Return closed PRs for *repo* that were merged after *since*.

    Makes a single paginated request to the GitHub REST API (up to
    ``_PRS_PER_PAGE`` results).  Returns an empty list on any network or
    HTTP error so that the caller's poll loop can continue safely.

    Args:
        repo: Repository in ``owner/repo`` format.
        gh_token: GitHub personal access token with at least ``repo`` scope.
        since: Only include PRs whose ``merged_at`` timestamp is strictly
            after this datetime.  Naive datetimes are treated as UTC.

    Returns:
        List of pull-request objects (dicts) as returned by the GitHub API.

    Raises:
        ValueError: If *repo* does not contain a ``/`` separator.
    """
    if "/" not in repo:
        raise ValueError(f"repo must be 'owner/repo', got: {repo!r}")

    url = (
        f"{_GH_API_BASE}/repos/{repo}/pulls"
        f"?state=closed&sort=updated&direction=desc&per_page={_PRS_PER_PAGE}"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as resp:
            pulls: list[dict] = json.loads(resp.read())
    except urllib.error.URLError:
        return []

    # Normalise *since* to UTC for comparison.
    since_utc = since if since.tzinfo is not None else since.replace(tzinfo=UTC)

    merged: list[dict] = []
    for pr in pulls:
        merged_at = pr.get("merged_at")
        if not merged_at:
            continue
        pr_merged_at = datetime.strptime(merged_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        if pr_merged_at > since_utc:
            merged.append(pr)

    return merged


def has_merged_prs_since(repo: str, since: datetime) -> bool:
    """Return True if *repo* has at least one PR merged after *since*.

    Reads ``GH_TOKEN`` from the environment.  Returns ``False`` immediately
    (without making any network call) when the token is absent.

    Args:
        repo: Repository in ``owner/repo`` format.
        since: Cutoff datetime; PRs merged at or before this time are ignored.

    Returns:
        ``True`` if one or more PRs were merged after *since*, ``False``
        otherwise (including when ``GH_TOKEN`` is missing or the request
        fails).
    """
    gh_token = _get_gh_token()
    if not gh_token:
        return False

    return len(fetch_merged_prs(repo=repo, gh_token=gh_token, since=since)) > 0
