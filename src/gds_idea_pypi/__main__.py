"""Entry point: python -m gds_idea_pypi."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .config import load_config
from .github import get_releases, make_client
from .index import generate_index

logger = logging.getLogger("gds_idea_pypi")


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
    logger.info("Packages: %s", ", ".join(p.repo for p in config.packages))

    # Discover releases
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        logger.warning(
            "No GITHUB_TOKEN or GH_TOKEN set. API rate limits will be very low."
        )

    client = make_client(token)
    all_packages = []

    for pkg_config in config.packages:
        logger.info("Scanning %s/%s ...", config.org, pkg_config.repo)
        try:
            pkg_releases = get_releases(
                config.org,
                pkg_config.repo,
                client,
                compute_hashes=not args.dry_run,
            )
            all_packages.append(pkg_releases)
        except Exception:
            logger.exception(
                "Failed to fetch releases for %s/%s",
                config.org,
                pkg_config.repo,
            )
            continue

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
    logger.info("Index written to %s/simple/", args.output)


if __name__ == "__main__":
    main()
