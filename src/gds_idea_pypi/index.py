"""Generate PEP 503 compliant static HTML index pages."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from .github import PackageReleases

logger = logging.getLogger(__name__)

INDEX_URL = "https://co-cddo.github.io/gds-idea-pypi/simple/"
ORG = "co-cddo"


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


def generate_landing_page(
    packages: list[PackageReleases],
    output_dir: Path,
) -> None:
    """Generate a human-friendly landing page at output_dir/index.html."""
    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build versions table rows
    table_rows = []
    for pkg in sorted(packages, key=lambda p: p.package_name):
        if not pkg.releases:
            continue
        latest = sorted(pkg.releases, key=lambda r: r.version, reverse=True)[0]
        has_wheel = any(a.is_wheel for a in latest.assets)
        wheel_badge = (
            '<span class="badge wheel">wheel</span>'
            if has_wheel
            else '<span class="badge source">source only</span>'
        )
        all_versions = ", ".join(
            f'<a href="simple/{escape(pkg.package_name)}/">{escape(r.version)}</a>'
            for r in sorted(pkg.releases, key=lambda r: r.version, reverse=True)
        )
        repo_url = f"https://github.com/{ORG}/{escape(pkg.repo)}"
        table_rows.append(f"""\
      <tr>
        <td><code>{escape(pkg.package_name)}</code></td>
        <td><strong>{escape(latest.version)}</strong> {wheel_badge}</td>
        <td class="versions">{all_versions}</td>
        <td><a href="{repo_url}">{escape(pkg.repo)}</a></td>
      </tr>""")

    table_body = "\n".join(table_rows)

    html = f"""\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>GDS IDEA Python Package Index</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #24292f; line-height: 1.6; }}
      h1 {{ border-bottom: 1px solid #d0d7de; padding-bottom: 10px; }}
      h2 {{ margin-top: 2em; }}
      table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
      th {{ background: #f6f8fa; text-align: left; padding: 8px 12px; border: 1px solid #d0d7de; }}
      td {{ padding: 8px 12px; border: 1px solid #d0d7de; vertical-align: top; }}
      td.versions {{ font-size: 0.85em; color: #57606a; }}
      code, pre {{ background: #f6f8fa; border-radius: 4px; font-family: "SFMono-Regular", Consolas, monospace; }}
      code {{ padding: 2px 5px; font-size: 0.9em; }}
      pre {{ padding: 14px; overflow-x: auto; font-size: 0.875em; border: 1px solid #d0d7de; }}
      .badge {{ font-size: 0.75em; padding: 1px 6px; border-radius: 10px; font-weight: 600; }}
      .badge.wheel {{ background: #dafbe1; color: #116329; }}
      .badge.source {{ background: #fff8c5; color: #7d4e00; }}
      .updated {{ font-size: 0.85em; color: #57606a; margin-top: -0.5em; }}
      blockquote {{ border-left: 4px solid #d0d7de; margin: 0; padding: 0 1em; color: #57606a; }}
      a {{ color: #0969da; }}
    </style>
  </head>
  <body>
    <h1>GDS IDEA Python Package Index</h1>
    <p>An internal PyPI index for GDS IDEA packages. <a href="https://github.com/{ORG}/gds-idea-pypi">View on GitHub</a></p>
    <p class="updated">Last rebuilt: {now}</p>

    <h2>Latest versions</h2>
    <table>
      <thead>
        <tr>
          <th>Package</th>
          <th>Latest</th>
          <th>All versions</th>
          <th>Repo</th>
        </tr>
      </thead>
      <tbody>
{table_body}
      </tbody>
    </table>

    <h2>Installing packages</h2>
    <p>
      The key benefit of this index over pinning to git tags is <strong>version constraints</strong>
      — you can now use <code>&gt;=</code>, <code>~=</code>, and ranges instead of locking to a
      specific commit or tag:
    </p>
    <pre><code># Before: locked to an exact git tag
uv add "gds-idea-app-kit @ git+https://github.com/{ORG}/gds-idea-app-kit@v0.2.6"

# Now: version constraints, resolved from the index
uv add gds-idea-app-kit --index gds-idea={INDEX_URL}</code></pre>
    <p>
      This adds the package to your <code>pyproject.toml</code> and automatically sets up the
      index and source pin:
    </p>
    <pre><code>[project]
dependencies = [
    "gds-idea-app-kit&gt;=0.2.7",
]

[tool.uv.sources]
gds-idea-app-kit = {{ index = "gds-idea" }}

[[tool.uv.index]]
name = "gds-idea"
url = "{INDEX_URL}"
explicit = true  # only used for packages explicitly pinned above; PyPI is unchanged</code></pre>
    <p>Once the index is in your <code>pyproject.toml</code>, adding more internal packages is just:</p>
    <pre><code>uv add cognito-auth --index gds-idea
uv add llmbo-bedrock --index gds-idea</code></pre>
    <p>You can adjust the version constraint to whatever you need:</p>
    <pre><code>"gds-idea-app-kit&gt;=0.2.0"   # any version from 0.2.0 onwards
"gds-idea-app-kit~=0.2.0"   # compatible release: &gt;=0.2.0, &lt;0.3.0
"gds-idea-app-kit&gt;=0.2,&lt;1"  # range</code></pre>

    <h2>Installing tools</h2>
    <p>
      For packages that provide a CLI (like <code>gds-idea-app-kit</code>), you can install them
      as global tools with <code>uv tool install</code> — equivalent to <code>pipx</code>:
    </p>
    <pre><code># First time — include the full index URL if you haven't done the one-time setup below
uv tool install gds-idea-app-kit --index gds-idea={INDEX_URL}

# After one-time setup, just:
uv tool install gds-idea-app-kit --index gds-idea

# Version constraints work here too
uv tool install "gds-idea-app-kit&gt;=0.2.7" --index gds-idea</code></pre>
    <p>To update an already-installed tool to the latest version:</p>
    <pre><code># Upgrade one tool
uv tool upgrade gds-idea-app-kit

# Or upgrade everything at once
uv tool upgrade --all</code></pre>
    <p>
      If you previously installed a tool from a git URL (e.g.
      <code>git+https://github.com/...</code>), reinstall it from the index with
      <code>--force-reinstall</code> to switch the source:
    </p>
    <pre><code>uv tool install gds-idea-app-kit --index gds-idea --force-reinstall</code></pre>
    <p>After that, <code>uv tool upgrade</code> will work correctly going forward.</p>

    <h2>One-time developer setup (optional)</h2>
    <p>
      Add the index to your global uv config so <code>--index gds-idea</code> works in any
      project without bootstrapping it first. Add this to
      <code>~/.config/uv/uv.toml</code> (macOS/Linux) or
      <code>%APPDATA%\\uv\\uv.toml</code> (Windows):
    </p>
    <pre><code>[[index]]
name = "gds-idea"
url = "{INDEX_URL}"
explicit = true</code></pre>
    <p>Once done, adding or installing any internal package is just:</p>
    <pre><code># Add to a project
uv add gds-idea-app-kit --index gds-idea

# Install as a global tool
uv tool install gds-idea-app-kit --index gds-idea</code></pre>

    <h2>Adding a new package to this index</h2>
    <h3>1. Add the repo to <code>config.toml</code></h3>
    <p>Open <a href="https://github.com/{ORG}/gds-idea-pypi/blob/main/config.toml"><code>config.toml</code></a> in this repo and add an entry:</p>
    <pre><code>[[packages]]
repo = "your-new-repo-name"</code></pre>
    <p>Merge the change to <code>main</code> — the index will pick it up on the next scheduled rebuild.</p>

    <h3>2. Set up wheel builds in the package repo</h3>
    <p>
      The index links directly to release assets, so the package repo needs to attach a wheel to
      each GitHub Release. Add these steps to the repo's release workflow
      (<code>.github/workflows/release.yml</code>):
    </p>
    <pre><code>      - uses: astral-sh/setup-uv@v7

      - name: Build wheel and sdist
        run: uv build

      - name: Upload artifacts to release
        run: gh release upload "${{{{ github.ref_name }}}}" dist/*.whl dist/*.tar.gz
        env:
          GH_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}

      # Automatic index rebuild — uncomment once PYPI_INDEX_TOKEN is configured
      # - name: Trigger PyPI index rebuild
      #   run: |
      #     gh api repos/{ORG}/gds-idea-pypi/dispatches \\
      #       -f event_type=rebuild-index
      #   env:
      #     GH_TOKEN: ${{{{ secrets.PYPI_INDEX_TOKEN }}}}</code></pre>

    <h3>3. Trigger a rebuild</h3>
    <p>
      The index rebuilds automatically every 6 hours. To get a new package or release into the
      index immediately, trigger a manual rebuild:
    </p>
    <p>
      <a href="https://github.com/{ORG}/gds-idea-pypi/actions/workflows/publish.yml">
        Actions → Rebuild PyPI Index → Run workflow
      </a>
    </p>
    <blockquote>
      <p>
        <strong>Automatic rebuild on release is coming.</strong> Once a
        <code>PYPI_INDEX_TOKEN</code> (a PAT with <code>repo</code> scope on this repo) is
        configured as an org-level secret, the commented-out step above can be enabled in each
        package repo. Releases will then trigger an instant index rebuild without any manual steps.
      </p>
    </blockquote>
  </body>
</html>
"""

    landing = output_dir / "index.html"
    landing.write_text(html)
    logger.info("Wrote %s", landing)
