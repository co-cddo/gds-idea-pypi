"""Entry point: python -m gds_idea_pypi."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import httpx

from .config import load_config
from .github import (
    PackageReleases,
    discover_repos,
    get_import_names,
    get_releases,
    make_client,
)
from .index import generate_index, generate_landing_page
from .live import carry_forward, fetch_published_index, find_removed_files, make_pages_client
from .report import RebuildProblems, has_failures, needs_report, report_problems

logger = logging.getLogger("gds_idea_pypi")

# Index was written and is deployable, but some repos or assets had errors.
PARTIAL_FAILURE_EXIT_CODE = 3


def _load_published(base_url: str) -> list[PackageReleases]:
    """Fetch the currently published index, or return [] (with a warning) if unavailable."""
    if not base_url:
        logger.warning("No [index].base_url configured; cannot compare with published index")
        return []
    try:
        with make_pages_client() as pages_client:
            return fetch_published_index(base_url, pages_client)
    except httpx.HTTPError:
        logger.warning(
            "Could not fetch the published index at %s; failed repos cannot be carried forward",
            base_url,
            exc_info=True,
        )
        return []


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gds-idea-pypi",
        description="Generate a static PEP 503 PyPI index from GitHub Releases.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to config.toml (default: ./config.toml)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("site"),
        help="Output directory for the generated index (default: ./site)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be indexed without generating files or computing hashes.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    # Suppress noisy HTTP-level debug logging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Load config
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        sys.exit(1)

    logger.info("Org: %s", config.org)

    # Discover releases
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        logger.warning(
            "No GITHUB_TOKEN or GH_TOKEN set. API rate limits will be very low."
        )

    client = make_client(token)

    # Build the full set of repos to scan: explicit + discovered
    repos_to_scan: set[str] = {p.repo for p in config.packages}

    if config.repo_prefix:
        discovered = discover_repos(config.org, client, prefix=config.repo_prefix)
        logger.info(
            "Discovered %d repo(s) matching prefix %r: %s",
            len(discovered),
            config.repo_prefix,
            ", ".join(discovered) if discovered else "(none)",
        )
        repos_to_scan.update(discovered)

    logger.info("Total repos to scan: %d", len(repos_to_scan))
    all_packages: list[PackageReleases] = []
    failed_repos: list[str] = []

    for repo in sorted(repos_to_scan):
        logger.info("Scanning %s/%s ...", config.org, repo)
        try:
            pkg_releases = get_releases(
                config.org,
                repo,
                client,
                compute_hashes=not args.dry_run,
            )
            pkg_releases.import_names = get_import_names(config.org, repo, client)
            all_packages.append(pkg_releases)
        except Exception:
            logger.exception(
                "Failed to fetch releases for %s/%s",
                config.org,
                repo,
            )
            failed_repos.append(repo)
            continue

    # Compare with what is live: reuse last published versions of repos that failed to
    # scan, and note files that have disappeared.
    problems = RebuildProblems(failed_repos=failed_repos)
    if not args.dry_run:
        published = _load_published(config.base_url)
        carried = carry_forward(failed_repos, published)
        for pkg in carried:
            logger.warning(
                "%s/%s: scan failed, carrying forward %d published release(s)",
                config.org,
                pkg.repo,
                len(pkg.releases),
            )
            pkg.import_names = get_import_names(config.org, pkg.repo, client)
        all_packages.extend(carried)
        problems.carried_forward = sorted({pkg.repo for pkg in carried})
        problems.removed_files = find_removed_files(
            published, all_packages, ignore_repos=set(failed_repos)
        )

    # Report
    for pkg in all_packages:
        total_files = sum(len(r.assets) for r in pkg.releases)
        logger.info(
            "  %s: %d releases, %d files (name: %s)",
            pkg.repo,
            len(pkg.releases),
            total_files,
            pkg.package_name,
        )
        for rel in pkg.releases:
            for asset in rel.assets:
                marker = "whl" if asset.is_wheel else "sdist/src"
                logger.info("    %s %s [%s]", rel.version, asset.filename, marker)

    if args.dry_run:
        logger.info("Dry run complete. No files written.")
        return

    # Generate index
    generate_index(all_packages, args.output)
    generate_landing_page(all_packages, args.output)
    logger.info("Index written to %s/simple/", args.output)
    logger.info("Landing page written to %s/index.html", args.output)

    if needs_report(problems, all_packages):
        report_problems(config.org, problems, all_packages)
    if has_failures(problems, all_packages):
        sys.exit(PARTIAL_FAILURE_EXIT_CODE)


if __name__ == "__main__":
    main()
