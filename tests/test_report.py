"""Tests for failure reporting and the CLI exit code."""

from __future__ import annotations

from pathlib import Path

import pytest

from gds_idea_pypi import __main__ as cli
from gds_idea_pypi.github import Asset, PackageReleases, Release
from gds_idea_pypi.report import has_failures, render_failure_summary, report_failures


def _pkg(repo: str, hash_failures: list[str] | None = None) -> PackageReleases:
    return PackageReleases(
        org="acme",
        repo=repo,
        package_name=repo,
        releases=[
            Release(
                tag="v1.0.0",
                version="1.0.0",
                assets=[Asset(filename=f"{repo}-1.0.0.tar.gz", url="https://x/y")],
            )
        ],
        hash_failures=hash_failures or [],
    )


def test_no_failures_renders_nothing() -> None:
    assert not has_failures([], [_pkg("ok")])
    assert render_failure_summary("acme", [], [_pkg("ok")]) == ""


def test_summary_lists_repos_and_assets() -> None:
    pkgs = [_pkg("ok"), _pkg("flaky", ["v1.0.0/flaky-1.0.0.tar.gz"])]
    summary = render_failure_summary("acme", ["gone"], pkgs)

    assert "`acme/gone`" in summary
    assert "`acme/flaky` `v1.0.0/flaky-1.0.0.tar.gz`" in summary
    assert "acme/ok" not in summary


def test_report_writes_annotations_and_step_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    report_failures("acme", ["gone"], [_pkg("flaky", ["v1.0.0/f.tar.gz"])])

    out = capsys.readouterr().out
    assert "::error title=Repo missing from index::acme/gone" in out
    assert "::error title=Asset indexed without sha256::acme/flaky v1.0.0/f.tar.gz" in out
    assert "acme/flaky" in summary_file.read_text()


def _run_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pkg: PackageReleases | Exception,
) -> Path:
    config = tmp_path / "config.toml"
    config.write_text(
        '[index]\norg = "acme"\nbase_url = "https://x/simple"\n\n'
        '[[packages]]\nrepo = "flaky"\n'
    )
    out = tmp_path / "site"

    def fake_get_releases(*args: object, **kwargs: object) -> PackageReleases:
        if isinstance(pkg, Exception):
            raise pkg
        return pkg

    monkeypatch.setattr(cli, "make_client", lambda token: None)
    monkeypatch.setattr(cli, "get_releases", fake_get_releases)
    monkeypatch.setattr(cli, "get_import_names", lambda *a, **k: [])
    monkeypatch.setattr(
        "sys.argv", ["gds-idea-pypi", "--config", str(config), "--output", str(out)]
    )
    return out


def test_main_writes_index_then_exits_3_on_hash_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _run_main(tmp_path, monkeypatch, _pkg("flaky", ["v1.0.0/flaky-1.0.0.tar.gz"]))

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == cli.PARTIAL_FAILURE_EXIT_CODE
    page = (out / "simple" / "flaky" / "index.html").read_text()
    assert "flaky-1.0.0.tar.gz" in page
    assert "#sha256=" not in page


def test_main_writes_index_then_exits_3_on_repo_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _run_main(tmp_path, monkeypatch, RuntimeError("boom"))

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == cli.PARTIAL_FAILURE_EXIT_CODE
    assert (out / "simple" / "index.html").exists()


def test_main_exits_cleanly_without_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _run_main(tmp_path, monkeypatch, _pkg("flaky"))

    cli.main()

    assert (out / "simple" / "flaky" / "index.html").exists()
