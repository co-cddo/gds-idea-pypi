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

    <h2>Using packages in a project</h2>
    <p>
      When adding an internal package you must tell uv which index to use, so it records the
      source in your <code>pyproject.toml</code>. Without this, the package will still install
      (uv finds it on the index automatically) but <code>pyproject.toml</code> won't show where
      it came from — making your project harder to understand and less reproducible.
    </p>
    <p>You have two options:</p>

    <h3>Option 1 — Always pass the full index URL</h3>
    <pre><code>uv add cognito-auth --index gds-idea={INDEX_URL}
uv add llmbo-bedrock --index gds-idea={INDEX_URL}</code></pre>
    <p>
      uv writes a source pin for each package and won't duplicate the index entry if it's already
      in your <code>pyproject.toml</code>. Note: <code>--index gds-idea</code> (without the URL)
      looks like it works but treats <code>gds-idea</code> as a file path — don't use it.
    </p>
    <p>After adding, your <code>pyproject.toml</code> will contain:</p>
    <pre><code>[tool.uv.sources]
cognito-auth = {{ index = "gds-idea" }}   # pinned to this index; PyPI not used for this package
llmbo-bedrock = {{ index = "gds-idea" }}

[[tool.uv.index]]
name = "gds-idea"
url = "{INDEX_URL}"</code></pre>

    <h3>Option 2 — Use <code>idea-tools add</code> (recommended)</h3>
    <p>
      If you have set up the <code>idea-tools</code> shell function (see below), it bakes in the
      URL for you — same result, less typing:
    </p>
    <pre><code>idea-tools add cognito-auth
idea-tools add llmbo-bedrock
idea-tools add "gds-idea-app-kit&gt;=0.2.0"</code></pre>

    <h3>Version constraints</h3>
    <pre><code>idea-tools add "gds-idea-app-kit&gt;=0.2.0"   # any version from 0.2.0 onwards
idea-tools add "gds-idea-app-kit~=0.2.0"   # compatible: &gt;=0.2.0, &lt;0.3.0
idea-tools add "gds-idea-app-kit&gt;=0.2,&lt;1"  # explicit range</code></pre>

    <h2>Using CLI tools</h2>
    <p>
      Some packages provide a CLI and can be installed as global tools with
      <code>uv tool install</code> — equivalent to <code>pipx</code>.
    </p>
    <p>
      <strong>You must always pass the full index URL when installing tools.</strong> Unlike
      project installs, <code>uv tool install</code> has no <code>pyproject.toml</code> in scope,
      so uv cannot read a stored index definition. This is a uv design constraint — use the
      <code>idea-tools</code> shell function below to avoid typing the URL every time.
    </p>

    <h3>One-time shell setup</h3>
    <p>
      If you use <strong>zsh (the default shell on a Mac)</strong>, run this command to add
      <code>idea-tools</code> automatically — no file editing needed. Then open a new terminal
      window and it will be available:
    </p>
    <pre><code>cat >> ~/.zshrc << 'EOF'
idea-tools() {{
  local cmd="$1"; shift
  case "$cmd" in
    add)     uv add "$@" --index "gds-idea={INDEX_URL}" ;;
    install) uv tool install "$@" --index "gds-idea={INDEX_URL}" ;;
    upgrade) [ $# -eq 0 ] && uv tool upgrade --all || uv tool upgrade "$@" ;;
    *)       echo "Usage:"
             echo "  idea-tools add &lt;package&gt;       add internal package to current project"
             echo "  idea-tools install &lt;package&gt;   install internal tool globally"
             echo "  idea-tools upgrade [package]   upgrade tool (omit package to upgrade all)" ;;
  esac
}}
EOF</code></pre>
    <p>
      If you use bash, or prefer to edit your config manually, add the function block above
      (without the <code>cat</code>/<code>EOF</code> wrapper) to your
      <code>~/.zshrc</code> or <code>~/.bashrc</code>.
    </p>

    <h3>Adding packages and installing tools</h3>
    <pre><code># Add an internal package to the current project
idea-tools add cognito-auth
idea-tools add "gds-idea-app-kit&gt;=0.2.7"

# Install an internal tool globally
idea-tools install gds-idea-app-kit
idea-tools install "gds-idea-app-kit&gt;=0.2.7"

# Upgrade a specific tool
idea-tools upgrade gds-idea-app-kit

# Upgrade all installed idea tools at once
idea-tools upgrade</code></pre>

    <h3>Migrating from git URL installs</h3>
    <p>
      If you previously installed a tool from a git URL, reinstall from the index to switch the
      tracked source. After this, <code>idea-tools upgrade</code> will resolve from the index
      correctly going forward.
    </p>
    <pre><code># Previously installed via git URL:
uv tool install "gds-idea-app-kit @ git+https://github.com/{ORG}/gds-idea-app-kit"

# Switch to the index:
idea-tools install gds-idea-app-kit --reinstall</code></pre>

    <hr>
    <p>
      Maintaining this index or adding a new package?
      See the <a href="https://github.com/{ORG}/gds-idea-pypi">project README on GitHub</a>.
    </p>
  </body>
</html>
"""

    landing = output_dir / "index.html"
    landing.write_text(html)
    logger.info("Wrote %s", landing)
