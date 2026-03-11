"""GitHub API client for discovering releases and assets."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# Matches wheel and sdist filenames (not the auto-generated source archives)
_WHEEL_RE = re.compile(r"\.whl$")
_SDIST_RE = re.compile(r"\.tar\.gz$")

# Tag patterns to extract version
_TAG_VERSION_RE = re.compile(
    r"^v?\.?(\d+(?:\.\d+)*(?:[-._]?(?:a|b|rc|dev|post)\d*)?)$"
)


@dataclass
class Asset:
    """A downloadable file attached to a release."""

    filename: str
    url: str
    sha256: str = ""
    is_wheel: bool = False
    is_sdist: bool = False


@dataclass
class Release:
    """A single release of a package."""

    tag: str
    version: str
    assets: list[Asset] = field(default_factory=list)


@dataclass
class PackageReleases:
    """All releases for a single repo/package."""

    org: str
    repo: str
    package_name: str  # normalised name from the wheel or derived from repo
    releases: list[Release] = field(default_factory=list)


def parse_version_from_tag(tag: str) -> str | None:
    """Extract a PEP 440-ish version string from a git tag.

    Handles: v1.2.3, 1.2.3, v.1.2.3, v3.6
    Returns None if the tag doesn't look like a version.
    """
    m = _TAG_VERSION_RE.match(tag)
    if m:
        return m.group(1)
    return None


def _package_name_from_wheel(filename: str) -> str | None:
    """Extract the normalised package name from a wheel filename.

    Wheel filenames follow: {name}-{version}(-{build})?-{python}-{abi}-{platform}.whl
    """
    parts = filename.split("-")
    if len(parts) >= 3:
        return _normalise_name(parts[0])
    return None


def _normalise_name(name: str) -> str:
    """PEP 503 normalise a package name: lowercase, replace runs of [-_.] with -."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _package_name_from_repo(repo: str) -> str:
    """Derive a normalised package name from a repo name."""
    return _normalise_name(repo)


def _is_auto_generated_archive(filename: str) -> bool:
    """Check if a filename looks like GitHub's auto-generated source archive.

    GitHub auto-generates archives named like the tag or repo, not like
    a Python sdist (which is named {package}-{version}.tar.gz).
    """
    # Auto-generated archives don't have a version pattern like pkg-1.0.0.tar.gz
    # They're typically just the tag name or repo name
    # A real sdist has: {name}-{version}.tar.gz where version is numeric
    if not filename.endswith(".tar.gz"):
        return False
    stem = filename.removesuffix(".tar.gz")
    # Real sdists contain a version-like suffix after a dash: name-1.2.3
    if re.search(r"-\d+(\.\d+)+$", stem):
        return False
    return True


def _compute_sha256(client: httpx.Client, url: str) -> str:
    """Stream-download a URL and compute its SHA-256 hash."""
    h = hashlib.sha256()
    with client.stream("GET", url, follow_redirects=True) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_bytes(chunk_size=8192):
            h.update(chunk)
    return h.hexdigest()


def get_releases(
    org: str,
    repo: str,
    client: httpx.Client,
    *,
    compute_hashes: bool = True,
) -> PackageReleases:
    """Fetch all releases for a repo and categorise their assets.

    For releases with wheel/sdist assets, records their download URLs.
    For releases without built assets, uses the auto-generated source tarball
    as a fallback.
    """
    url = f"https://api.github.com/repos/{org}/{repo}/releases"
    releases: list[Release] = []
    package_name: str | None = None

    page = 1
    while True:
        resp = client.get(url, params={"per_page": 100, "page": page})
        resp.raise_for_status()
        data = resp.json()

        if not data:
            break

        for rel in data:
            tag = rel["tag_name"]
            version = parse_version_from_tag(tag)
            if version is None:
                logger.warning(
                    "%s/%s: skipping tag %r (can't parse version)", org, repo, tag
                )
                continue

            assets: list[Asset] = []
            has_built_asset = False

            # Check release assets for wheels and sdists
            for asset in rel.get("assets", []):
                name = asset["name"]
                download_url = asset["browser_download_url"]

                if _WHEEL_RE.search(name):
                    sha = (
                        _compute_sha256(client, download_url)
                        if compute_hashes
                        else ""
                    )
                    assets.append(
                        Asset(
                            filename=name,
                            url=download_url,
                            sha256=sha,
                            is_wheel=True,
                        )
                    )
                    has_built_asset = True
                    # Try to detect package name from wheel
                    if package_name is None:
                        package_name = _package_name_from_wheel(name)

                elif _SDIST_RE.search(name) and not _is_auto_generated_archive(name):
                    sha = (
                        _compute_sha256(client, download_url)
                        if compute_hashes
                        else ""
                    )
                    assets.append(
                        Asset(
                            filename=name,
                            url=download_url,
                            sha256=sha,
                            is_sdist=True,
                        )
                    )
                    has_built_asset = True

            # Fallback: use the auto-generated source tarball
            if not has_built_asset:
                tarball_url = rel.get("tarball_url", "")
                if tarball_url:
                    # Construct a proper filename for the source archive
                    fallback_name = f"{repo}-{version}.tar.gz"
                    sha = (
                        _compute_sha256(client, tarball_url)
                        if compute_hashes
                        else ""
                    )
                    assets.append(
                        Asset(
                            filename=fallback_name,
                            url=tarball_url,
                            sha256=sha,
                            is_sdist=True,
                        )
                    )
                    logger.info(
                        "%s/%s %s: no built assets, using source tarball",
                        org,
                        repo,
                        tag,
                    )

            if assets:
                releases.append(Release(tag=tag, version=version, assets=assets))

        page += 1

    if package_name is None:
        package_name = _package_name_from_repo(repo)

    return PackageReleases(
        org=org,
        repo=repo,
        package_name=package_name,
        releases=releases,
    )


def make_client(token: str | None = None) -> httpx.Client:
    """Create an httpx client with optional GitHub token auth."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    return httpx.Client(
        headers=headers,
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
    )
