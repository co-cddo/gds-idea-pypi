"""Generate PEP 503 compliant static HTML index pages."""

from __future__ import annotations

import logging
from html import escape
from pathlib import Path

from .github import PackageReleases

logger = logging.getLogger(__name__)


def _render_root_index(packages: list[PackageReleases]) -> str:
    """Render the root index.html listing all packages."""
    links = []
    for pkg in sorted(packages, key=lambda p: p.package_name):
        name = escape(pkg.package_name)
        links.append(f'    <a href="{name}/">{name}</a>')

    body = "\n".join(links)
    return f"""\
<!DOCTYPE html>
<html>
  <head>
    <meta name="pypi:repository-version" content="1.0">
    <title>Simple Index</title>
  </head>
  <body>
{body}
  </body>
</html>
"""


def _render_package_index(pkg: PackageReleases) -> str:
    """Render a per-package index.html listing all versions/files."""
    links = []
    # Sort releases by version (newest first for readability, though order doesn't matter to pip)
    for release in sorted(pkg.releases, key=lambda r: r.version, reverse=True):
        for asset in release.assets:
            href = escape(asset.url)
            filename = escape(asset.filename)
            if asset.sha256:
                href += f"#sha256={asset.sha256}"
            links.append(f'    <a href="{href}">{filename}</a>')

    body = "\n".join(links)
    name = escape(pkg.package_name)
    return f"""\
<!DOCTYPE html>
<html>
  <head>
    <meta name="pypi:repository-version" content="1.0">
    <title>Links for {name}</title>
  </head>
  <body>
    <h1>Links for {name}</h1>
{body}
  </body>
</html>
"""


def generate_index(
    packages: list[PackageReleases],
    output_dir: Path,
) -> None:
    """Generate the full static PEP 503 index to output_dir/simple/."""
    simple_dir = output_dir / "simple"
    simple_dir.mkdir(parents=True, exist_ok=True)

    # Root index
    root_html = _render_root_index(packages)
    root_index = simple_dir / "index.html"
    root_index.write_text(root_html)
    logger.info("Wrote %s", root_index)

    # Per-package indexes
    for pkg in packages:
        pkg_dir = simple_dir / pkg.package_name
        pkg_dir.mkdir(parents=True, exist_ok=True)
        pkg_html = _render_package_index(pkg)
        pkg_index = pkg_dir / "index.html"
        pkg_index.write_text(pkg_html)
        total_files = sum(len(r.assets) for r in pkg.releases)
        logger.info(
            "Wrote %s (%d releases, %d files)",
            pkg_index,
            len(pkg.releases),
            total_files,
        )
