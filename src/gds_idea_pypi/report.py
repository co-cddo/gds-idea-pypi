"""Report rebuild problems to the log, GitHub Actions annotations and the job summary."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from .github import PackageReleases

logger = logging.getLogger(__name__)

# Annotations show a handful of items; the full list goes in the job summary.
_MAX_ANNOTATED = 10


@dataclass
class RebuildProblems:
    """Everything that went wrong or changed unexpectedly during a rebuild."""

    failed_repos: list[str] = field(default_factory=list)
    # Subset of failed_repos whose last published versions were reused
    carried_forward: list[str] = field(default_factory=list)
    # "package/filename" entries that were published before but are absent now
    removed_files: list[str] = field(default_factory=list)

    @property
    def missing_repos(self) -> list[str]:
        """Failed repos that could not be carried forward and are absent from the index."""
        return [r for r in self.failed_repos if r not in self.carried_forward]


def has_failures(problems: RebuildProblems, packages: list[PackageReleases]) -> bool:
    """Return True if any repo failed to scan or any asset was indexed without a hash.

    Removed files alone are informational and do not count as failures.
    """
    return bool(problems.failed_repos) or any(pkg.hash_failures for pkg in packages)


def needs_report(problems: RebuildProblems, packages: list[PackageReleases]) -> bool:
    """Return True if there is anything to tell the user about."""
    return has_failures(problems, packages) or bool(problems.removed_files)


def render_summary(
    org: str,
    problems: RebuildProblems,
    packages: list[PackageReleases],
) -> str:
    """Render a Markdown summary of problems, or "" if there is nothing to report."""
    if not needs_report(problems, packages):
        return ""

    lines = ["## Index rebuild report", ""]
    if problems.carried_forward:
        lines += [
            "These repos could not be scanned. The **last published versions are being "
            "served**; new releases will appear after the next successful rebuild:",
            "",
            *(f"- `{org}/{repo}`" for repo in problems.carried_forward),
            "",
        ]
    if problems.missing_repos:
        lines += [
            "These repos could not be scanned and have nothing to fall back on, so they are "
            "**missing from the index**:",
            "",
            *(f"- `{org}/{repo}`" for repo in problems.missing_repos),
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
    if problems.removed_files:
        lines += [
            "These files were in the previously published index and are **no longer "
            "listed** (expected if a release or repo was deleted or archived):",
            "",
            *(f"- `{entry}`" for entry in problems.removed_files),
            "",
        ]
    return "\n".join(lines)


def report_problems(
    org: str,
    problems: RebuildProblems,
    packages: list[PackageReleases],
) -> None:
    """Log problems, emit GitHub Actions annotations and append to the job summary."""
    for repo in problems.carried_forward:
        logger.error("%s/%s: scan failed, serving last published versions", org, repo)
        print(
            f"::error title=Repo scan failed::{org}/{repo} could not be scanned; "
            "serving its last published versions"
        )
    for repo in problems.missing_repos:
        logger.error("%s/%s: missing from index (scan failed)", org, repo)
        print(f"::error title=Repo missing from index::{org}/{repo} could not be scanned")
    for pkg in packages:
        for label in pkg.hash_failures:
            logger.error("%s/%s: %s indexed without sha256", org, pkg.repo, label)
            print(
                f"::error title=Asset indexed without sha256::"
                f"{org}/{pkg.repo} {label} could not be hashed after retries"
            )
    if problems.removed_files:
        logger.warning("%d file(s) removed since last publish", len(problems.removed_files))
        shown = ", ".join(problems.removed_files[:_MAX_ANNOTATED])
        extra = len(problems.removed_files) - _MAX_ANNOTATED
        if extra > 0:
            shown += f" (and {extra} more)"
        print(
            f"::warning title=Files removed since last publish::"
            f"{len(problems.removed_files)} file(s) no longer listed: {shown}"
        )

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        summary = render_summary(org, problems, packages)
        with Path(summary_path).open("a", encoding="utf-8") as f:
            f.write(summary + "\n")
