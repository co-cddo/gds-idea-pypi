"""Report rebuild failures to the log, GitHub Actions annotations and the job summary."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .github import PackageReleases

logger = logging.getLogger(__name__)


def has_failures(failed_repos: list[str], packages: list[PackageReleases]) -> bool:
    """Return True if any repo failed to scan or any asset was indexed without a hash."""
    return bool(failed_repos) or any(pkg.hash_failures for pkg in packages)


def render_failure_summary(
    org: str,
    failed_repos: list[str],
    packages: list[PackageReleases],
) -> str:
    """Render a Markdown summary of failures, or "" if there were none."""
    if not has_failures(failed_repos, packages):
        return ""

    lines = ["## Index rebuilt with errors", ""]
    if failed_repos:
        lines += [
            "These repos could not be scanned and are **missing from the index**:",
            "",
            *(f"- `{org}/{repo}`" for repo in failed_repos),
            "",
        ]
    unhashed = [pkg for pkg in packages if pkg.hash_failures]
    if unhashed:
        lines += [
            "These files are in the index **without a sha256** because the download "
            "failed after retries. They are still installable; the next rebuild "
            "should restore the hash:",
            "",
        ]
        for pkg in unhashed:
            lines += [f"- `{org}/{pkg.repo}` `{label}`" for label in pkg.hash_failures]
        lines.append("")
    return "\n".join(lines)


def report_failures(
    org: str,
    failed_repos: list[str],
    packages: list[PackageReleases],
) -> None:
    """Log failures, emit GitHub Actions annotations and append to the job summary."""
    for repo in failed_repos:
        logger.error("%s/%s: missing from index (scan failed)", org, repo)
        print(f"::error title=Repo missing from index::{org}/{repo} could not be scanned")
    for pkg in packages:
        for label in pkg.hash_failures:
            logger.error("%s/%s: %s indexed without sha256", org, pkg.repo, label)
            print(
                f"::error title=Asset indexed without sha256::"
                f"{org}/{pkg.repo} {label} could not be hashed after retries"
            )

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        summary = render_failure_summary(org, failed_repos, packages)
        with Path(summary_path).open("a", encoding="utf-8") as f:
            f.write(summary + "\n")
