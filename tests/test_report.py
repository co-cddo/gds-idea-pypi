"""Tests for problem reporting and the CLI's carry-forward and exit-code behaviour."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from gds_idea_pypi import __main__ as cli
from gds_idea_pypi.github import Asset, PackageReleases, Release
from gds_idea_pypi.report import (
    RebuildProblems,
    has_failures,
    needs_report,
    render_summary,
    report_problems,
)


def _pkg(
    repo: str,
    hash_failures: list[str] | None = None,
    filename: str | None = None,
) -> PackageReleases:
    filename = filename or f"{repo}-1.0.0.tar.gz"
    return PackageReleases(
        org="acme",
        repo=repo,
        package_name=repo,
        releases=[
            Release(
                tag="v1.0.0",
                version="1.0.0",
                assets=[
                    Asset(
                        filename=filename,
                        url=f"https://github.com/acme/{repo}/releases/download/v1.0.0/{filename}",
                        sha256="c" * 64,
                        is_sdist=True,
                    )
                ],
            )
        ],
        hash_failures=hash_failures or [],
    )


def test_nothing_to_report() -> None:
    problems = RebuildProblems()
    assert not has_failures(problems, [_pkg("ok")])
    assert not needs_report(problems, [_pkg("ok")])
    assert render_summary("acme", problems, [_pkg("ok")]) == ""


def test_removed_files_alone_are_not_a_failure() -> None:
    problems = RebuildProblems(removed_files=["ok/ok-0.9.0.tar.gz"])
    assert not has_failures(problems, [_pkg("ok")])
    assert needs_report(problems, [_pkg("ok")])


def test_summary_distinguishes_carried_missing_unhashed_and_removed() -> None:
    problems = RebuildProblems(
        failed_repos=["carried", "gone"],
        carried_forward=["carried"],
        removed_files=["ok/ok-0.9.0.tar.gz"],
    )
    pkgs = [_pkg("flaky", ["v1.0.0/flaky-1.0.0.tar.gz"])]

    summary = render_summary("acme", problems, pkgs)

    assert "last published versions are being served" in summary
    assert "`acme/carried`" in summary
    assert "missing from the index" in summary
    assert "`acme/gone`" in summary
    assert "`acme/flaky` `v1.0.0/flaky-1.0.0.tar.gz`" in summary
    assert "`ok/ok-0.9.0.tar.gz`" in summary
    assert problems.missing_repos == ["gone"]


def test_report_writes_annotations_and_step_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    problems = RebuildProblems(
        failed_repos=["carried", "gone"],
        carried_forward=["carried"],
        removed_files=[f"p/f{i}.tar.gz" for i in range(12)],
    )

    report_problems("acme", problems, [_pkg("flaky", ["v1.0.0/f.tar.gz"])])

    out = capsys.readouterr().out
    assert "::error title=Repo scan failed::acme/carried" in out
    assert "::error title=Repo missing from index::acme/gone" in out
    assert "::error title=Asset indexed without sha256::acme/flaky v1.0.0/f.tar.gz" in out
    assert "::warning title=Files removed since last publish::12 file(s)" in out
    assert "(and 2 more)" in out
    assert "p/f11.tar.gz" in summary_file.read_text()


# --- CLI end to end -------------------------------------------------------------------


def _setup_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    scanned: dict[str, PackageReleases | Exception],
    published: list[PackageReleases] | Exception,
) -> Path:
    config = tmp_path / "config.toml"
    repos = "".join(f'[[packages]]\nrepo = "{r}"\n\n' for r in scanned)
    config.write_text(f'[index]\norg = "acme"\nbase_url = "https://x/simple"\n\n{repos}')
    out = tmp_path / "site"

    def fake_get_releases(org: str, repo: str, *args: object, **kwargs: object) -> PackageReleases:
        result = scanned[repo]
        if isinstance(result, Exception):
            raise result
        return result

    def fake_fetch(*args: object, **kwargs: object) -> list[PackageReleases]:
        if isinstance(published, Exception):
            raise published
        return published

    monkeypatch.setattr(cli, "make_client", lambda token: None)
    monkeypatch.setattr(cli, "make_pages_client", httpx.Client)
    monkeypatch.setattr(cli, "get_releases", fake_get_releases)
    monkeypatch.setattr(cli, "get_import_names", lambda *a, **k: [])
    monkeypatch.setattr(cli, "fetch_published_index", fake_fetch)
    monkeypatch.setattr(
        "sys.argv", ["gds-idea-pypi", "--config", str(config), "--output", str(out)]
    )
    return out


def test_hash_failure_writes_index_then_exits_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _setup_main(
        tmp_path,
        monkeypatch,
        scanned={"flaky": _pkg("flaky", ["v1.0.0/flaky-1.0.0.tar.gz"])},
        published=[],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == cli.PARTIAL_FAILURE_EXIT_CODE
    assert (out / "simple" / "flaky" / "index.html").exists()


def test_failed_repo_is_carried_forward_from_published_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _setup_main(
        tmp_path,
        monkeypatch,
        scanned={"ok": _pkg("ok"), "flaky": RuntimeError("boom")},
        published=[_pkg("ok"), _pkg("flaky")],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == cli.PARTIAL_FAILURE_EXIT_CODE
    # Both packages are in the deployed index, and the landing page lists the carried one
    assert "flaky-1.0.0.tar.gz" in (out / "simple" / "flaky" / "index.html").read_text()
    assert (out / "simple" / "ok" / "index.html").exists()
    assert "flaky" in (out / "index.html").read_text()
    stdout = capsys.readouterr().out
    assert "::error title=Repo scan failed::acme/flaky" in stdout
    assert "Repo missing from index" not in stdout


def test_failed_repo_is_missing_when_published_index_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _setup_main(
        tmp_path,
        monkeypatch,
        scanned={"ok": _pkg("ok"), "flaky": RuntimeError("boom")},
        published=httpx.ConnectError("down"),
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == cli.PARTIAL_FAILURE_EXIT_CODE
    assert not (out / "simple" / "flaky").exists()
    assert (out / "simple" / "index.html").exists()
    assert "::error title=Repo missing from index::acme/flaky" in capsys.readouterr().out


def test_removed_file_warns_but_does_not_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _setup_main(
        tmp_path,
        monkeypatch,
        scanned={"ok": _pkg("ok")},
        published=[_pkg("ok"), _pkg("ok", filename="ok-0.5.0.tar.gz")],
    )

    cli.main()  # no SystemExit

    assert (out / "simple" / "ok" / "index.html").exists()
    assert "::warning title=Files removed since last publish::1 file(s)" in capsys.readouterr().out


def test_clean_run_reports_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _setup_main(tmp_path, monkeypatch, scanned={"ok": _pkg("ok")}, published=[_pkg("ok")])

    cli.main()

    assert "::" not in capsys.readouterr().out
