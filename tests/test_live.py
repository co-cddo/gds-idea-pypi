"""Tests for parsing the published index and carrying packages forward."""

from __future__ import annotations

import httpx
import pytest

from gds_idea_pypi.github import Asset, PackageReleases, Release
from gds_idea_pypi.index import _render_package_index, _render_root_index
from gds_idea_pypi.live import (
    _parse_package_page,
    _version_from_filename,
    carry_forward,
    fetch_published_index,
    find_removed_files,
)

WHEEL = "pkg_demo-1.0.0-py3-none-any.whl"
SDIST = "pkg_demo-1.0.0.tar.gz"
DL = "https://github.com/acme/pkg-demo/releases/download/v1.0.0"


def _pkg(repo: str = "pkg-demo", name: str = "pkg-demo") -> PackageReleases:
    return PackageReleases(
        org="acme",
        repo=repo,
        package_name=name,
        releases=[
            Release(
                tag="v1.0.0",
                version="1.0.0",
                assets=[
                    Asset(filename=WHEEL, url=f"{DL}/{WHEEL}", sha256="a" * 64, is_wheel=True),
                    Asset(filename=SDIST, url=f"{DL}/{SDIST}", sha256="", is_sdist=True),
                ],
            ),
            Release(
                tag="v0.9.0",
                version="0.9.0",
                assets=[
                    Asset(
                        filename="pkg-demo-0.9.0.tar.gz",
                        url="https://api.github.com/repos/acme/pkg-demo/tarball/v0.9.0",
                        sha256="b" * 64,
                        is_sdist=True,
                    )
                ],
            ),
        ],
    )


@pytest.mark.parametrize(
    ("filename", "version"),
    [
        (WHEEL, "1.0.0"),
        (SDIST, "1.0.0"),
        ("gds-idea-box2.0-0.3.1.tar.gz", "0.3.1"),
        ("notes.txt", None),
    ],
)
def test_version_from_filename(filename: str, version: str | None) -> None:
    assert _version_from_filename(filename) == version


def test_round_trip_through_rendered_page() -> None:
    """What index.py writes is what live.py reads back."""
    original = _pkg()
    parsed = _parse_package_page("pkg-demo", _render_package_index(original))

    assert parsed is not None
    assert (parsed.org, parsed.repo) == ("acme", "pkg-demo")
    by_tag = {r.tag: r for r in parsed.releases}
    assert set(by_tag) == {"v1.0.0", "v0.9.0"}
    assert by_tag["v1.0.0"].version == "1.0.0"
    files = {a.filename: a for a in by_tag["v1.0.0"].assets}
    assert files[WHEEL].sha256 == "a" * 64
    assert files[WHEEL].is_wheel
    assert files[SDIST].sha256 == ""
    assert files[SDIST].is_sdist
    assert by_tag["v0.9.0"].assets[0].url.endswith("/tarball/v0.9.0")


def test_unparseable_page_returns_none() -> None:
    assert _parse_package_page("x", "<html><a href='https://example.com/f'>f</a></html>") is None


def _pages_client(pages: dict[str, tuple[int, str]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        status, body = pages.get(request.url.path, (404, ""))
        return httpx.Response(status, text=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_published_index() -> None:
    a, b = _pkg(), _pkg("other-repo", "other")
    b.releases = b.releases[:1]
    for asset in b.releases[0].assets:
        asset.url = asset.url.replace("pkg-demo", "other-repo")
    client = _pages_client(
        {
            "/simple/": (200, _render_root_index([a, b])),
            "/simple/pkg-demo/": (200, _render_package_index(a)),
            "/simple/other/": (200, _render_package_index(b)),
        }
    )

    got = fetch_published_index("https://pages.example/simple", client)

    assert {(p.package_name, p.repo) for p in got} == {
        ("pkg-demo", "pkg-demo"),
        ("other", "other-repo"),
    }


def test_fetch_skips_one_broken_package_page() -> None:
    a, b = _pkg(), _pkg("other-repo", "other")
    client = _pages_client(
        {
            "/simple/": (200, _render_root_index([a, b])),
            "/simple/pkg-demo/": (200, _render_package_index(a)),
            "/simple/other/": (500, ""),
        }
    )

    got = fetch_published_index("https://pages.example/simple/", client)

    assert [p.package_name for p in got] == ["pkg-demo"]


def test_fetch_raises_when_root_unavailable() -> None:
    client = _pages_client({})
    with pytest.raises(httpx.HTTPStatusError):
        fetch_published_index("https://pages.example/simple", client)


def test_carry_forward_selects_failed_repos_only() -> None:
    published = [_pkg(), _pkg("other-repo", "other")]
    assert [p.repo for p in carry_forward(["other-repo", "unknown"], published)] == ["other-repo"]


def test_find_removed_files() -> None:
    published = [_pkg(), _pkg("failed-repo", "failed")]
    current = [_pkg()]
    current[0].releases = current[0].releases[:1]  # drop v0.9.0

    removed = find_removed_files(published, current, ignore_repos={"failed-repo"})

    assert removed == ["pkg-demo/pkg-demo-0.9.0.tar.gz"]
