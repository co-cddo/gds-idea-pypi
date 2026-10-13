"""Tests for hash retry and failure handling in github.py."""

from __future__ import annotations

import httpx
import pytest

from gds_idea_pypi import github
from gds_idea_pypi.github import get_releases

ORG = "acme"
REPO = "pkg-demo"
WHEEL = "pkg_demo-1.0.0-py3-none-any.whl"
SDIST = "pkg_demo-1.0.0.tar.gz"
BASE = "https://downloads.example/"


def _release(tag: str, names: list[str]) -> dict:
    return {
        "tag_name": tag,
        "tarball_url": f"https://api.example/tarball/{tag}",
        "assets": [{"name": n, "browser_download_url": f"{BASE}{tag}/{n}"} for n in names],
    }


def _client(releases: list[dict], download_status: dict[str, list[int]]) -> httpx.Client:
    """Build a client whose downloads return the queued status codes per URL path.

    The last status in each list is repeated once the list is exhausted. Paths not
    listed return 200.
    """
    calls: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            page = int(request.url.params["page"])
            return httpx.Response(200, json=releases if page == 1 else [])
        path = request.url.path
        statuses = download_status.get(path, [200])
        n = calls.get(path, 0)
        calls[path] = n + 1
        status = statuses[min(n, len(statuses) - 1)]
        return httpx.Response(status, content=b"payload")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    client.calls = calls  # type: ignore[attr-defined]
    return client


@pytest.fixture(autouse=True)
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace time.sleep so retries are instant, and record the delays."""
    delays: list[float] = []
    monkeypatch.setattr(github.time, "sleep", delays.append)
    return delays


def test_hash_retries_then_succeeds(sleeps: list[float]) -> None:
    client = _client(
        [_release("v1.0.0", [WHEEL])],
        {f"/v1.0.0/{WHEEL}": [500, 503, 200]},
    )
    pkg = get_releases(ORG, REPO, client)

    asset = pkg.releases[0].assets[0]
    assert asset.sha256 != ""
    assert pkg.hash_failures == []
    assert sleeps == [1.0, 2.0]


def test_hash_not_retried_on_404(sleeps: list[float]) -> None:
    client = _client([_release("v1.0.0", [WHEEL])], {f"/v1.0.0/{WHEEL}": [404]})
    pkg = get_releases(ORG, REPO, client)

    assert client.calls[f"/v1.0.0/{WHEEL}"] == 1  # type: ignore[attr-defined]
    assert sleeps == []
    assert pkg.hash_failures == [f"v1.0.0/{WHEEL}"]


def test_failed_hash_keeps_asset_without_hash(sleeps: list[float]) -> None:
    """One asset failing must not drop it, its sibling, or other versions."""
    client = _client(
        [
            _release("v2.0.0", [WHEEL, SDIST]),
            _release("v1.0.0", [WHEEL]),
        ],
        {f"/v2.0.0/{SDIST}": [500]},
    )
    pkg = get_releases(ORG, REPO, client)

    assert [r.tag for r in pkg.releases] == ["v2.0.0", "v1.0.0"]
    v2_assets = {a.filename: a for a in pkg.releases[0].assets}
    assert set(v2_assets) == {WHEEL, SDIST}
    assert v2_assets[SDIST].sha256 == ""
    assert v2_assets[WHEEL].sha256 != ""
    assert pkg.releases[1].assets[0].sha256 != ""
    assert pkg.hash_failures == [f"v2.0.0/{SDIST}"]
    assert len(sleeps) == 2  # 3 attempts -> 2 backoff sleeps


def test_failed_hash_on_source_tarball_fallback() -> None:
    client = _client([_release("v1.0.0", [])], {"/tarball/v1.0.0": [500]})
    pkg = get_releases(ORG, REPO, client)

    asset = pkg.releases[0].assets[0]
    assert asset.filename == f"{REPO}-1.0.0.tar.gz"
    assert asset.sha256 == ""
    assert pkg.hash_failures == [f"v1.0.0/{REPO}-1.0.0.tar.gz"]


def test_compute_hashes_false_downloads_nothing() -> None:
    client = _client([_release("v1.0.0", [WHEEL])], {f"/v1.0.0/{WHEEL}": [500]})
    pkg = get_releases(ORG, REPO, client, compute_hashes=False)

    assert client.calls == {}  # type: ignore[attr-defined]
    assert pkg.hash_failures == []
    assert pkg.releases[0].assets[0].sha256 == ""


def test_transport_error_is_retried(sleeps: list[float]) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.host == "api.github.com":
            page = int(request.url.params["page"])
            return httpx.Response(
                200, json=[_release("v1.0.0", [WHEEL])] if page == 1 else []
            )
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, content=b"payload")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    pkg = get_releases(ORG, REPO, client)

    assert attempts == 2
    assert pkg.hash_failures == []
    assert sleeps == [1.0]
