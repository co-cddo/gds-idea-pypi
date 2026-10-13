"""Fetch and parse the currently published index, to carry packages forward on failure."""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser

import httpx

from .github import Asset, PackageReleases, Release

logger = logging.getLogger(__name__)

# Asset URLs written by github.py: release downloads and the auto-generated tarball.
_DOWNLOAD_URL_RE = re.compile(
    r"^https://github\.com/(?P<org>[^/]+)/(?P<repo>[^/]+)/releases/download/(?P<tag>[^/]+)/"
)
_TARBALL_URL_RE = re.compile(
    r"^https://api\.github\.com/repos/(?P<org>[^/]+)/(?P<repo>[^/]+)/tarball/(?P<tag>[^/]+)$"
)
_MAX_LISTED_FILES = 10


class _AnchorParser(HTMLParser):
    """Collect (href, text) pairs for every <a> tag."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._text).strip()))
            self._href = None


def _parse_links(html: str) -> list[tuple[str, str]]:
    """Return (href, text) for every anchor in an HTML document."""
    parser = _AnchorParser()
    parser.feed(html)
    return parser.links


def _version_from_filename(filename: str) -> str | None:
    """Extract the version from a wheel ({name}-{version}-...whl) or sdist filename."""
    if filename.endswith(".whl"):
        parts = filename.split("-")
        return parts[1] if len(parts) >= 3 else None
    if filename.endswith(".tar.gz"):
        stem = filename.removesuffix(".tar.gz")
        return stem.rsplit("-", 1)[1] if "-" in stem else None
    return None


def _parse_package_page(package_name: str, html: str) -> PackageReleases | None:
    """Rebuild a PackageReleases from a published per-package index page.

    Returns None if no link could be parsed into a known repo and version.
    """
    org = repo = ""
    releases: dict[tuple[str, str], Release] = {}

    for href, filename in _parse_links(html):
        url, _, fragment = href.partition("#")
        match = _DOWNLOAD_URL_RE.match(url) or _TARBALL_URL_RE.match(url)
        version = _version_from_filename(filename)
        if match is None or version is None:
            logger.warning("%s: ignoring unrecognised link %r", package_name, href)
            continue

        org, repo = match["org"], match["repo"]
        tag = match["tag"]
        release = releases.setdefault((tag, version), Release(tag=tag, version=version))
        release.assets.append(
            Asset(
                filename=filename,
                url=url,
                sha256=fragment.removeprefix("sha256=") if fragment.startswith("sha256=") else "",
                is_wheel=filename.endswith(".whl"),
                is_sdist=filename.endswith(".tar.gz"),
            )
        )

    if not releases:
        return None
    return PackageReleases(
        org=org,
        repo=repo,
        package_name=package_name,
        releases=list(releases.values()),
    )


def make_pages_client() -> httpx.Client:
    """Create a plain httpx client for the published index (no GitHub credentials)."""
    return httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)


def fetch_published_index(base_url: str, client: httpx.Client) -> list[PackageReleases]:
    """Fetch and parse the currently published index at base_url.

    Raises httpx.HTTPError if the root index cannot be fetched. A package page that
    cannot be fetched or parsed is skipped with a warning.
    """
    base = base_url.rstrip("/") + "/"
    resp = client.get(base)
    resp.raise_for_status()

    packages: list[PackageReleases] = []
    for _, name in _parse_links(resp.text):
        try:
            page = client.get(f"{base}{name}/")
            page.raise_for_status()
        except httpx.HTTPError:
            logger.warning("Could not fetch published page for %s", name, exc_info=True)
            continue
        pkg = _parse_package_page(name, page.text)
        if pkg is None:
            logger.warning("Published page for %s had no recognisable links", name)
            continue
        packages.append(pkg)

    logger.info("Fetched %d package(s) from the published index", len(packages))
    return packages


def carry_forward(
    failed_repos: list[str],
    published: list[PackageReleases],
) -> list[PackageReleases]:
    """Return the published packages that belong to repos which failed to scan."""
    failed = set(failed_repos)
    return [pkg for pkg in published if pkg.repo in failed]


def find_removed_files(
    published: list[PackageReleases],
    current: list[PackageReleases],
    *,
    ignore_repos: set[str],
) -> list[str]:
    """List "package/filename" entries that were published but are absent from current.

    Packages from ignore_repos (repos that failed to scan) are skipped, since their
    failure is reported separately.
    """
    present = {
        (pkg.package_name, asset.filename)
        for pkg in current
        for rel in pkg.releases
        for asset in rel.assets
    }
    removed = [
        f"{pkg.package_name}/{asset.filename}"
        for pkg in published
        if pkg.repo not in ignore_repos
        for rel in pkg.releases
        for asset in rel.assets
        if (pkg.package_name, asset.filename) not in present
    ]
    return sorted(removed)
