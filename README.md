# gds-idea-pypi

An internal PyPI index for GDS IDEA packages, hosted on GitHub Pages.

**Index URL:** `https://co-cddo.github.io/gds-idea-pypi/simple/`

**Latest versions and full install docs:** `https://co-cddo.github.io/gds-idea-pypi/`

## One-time developer setup

Add the index to your global uv config so `--index gds-idea` works in any project without looking up the URL each time. Add this to `~/.config/uv/uv.toml` (macOS/Linux) or `%APPDATA%\uv\uv.toml` (Windows):

```toml
[[index]]
name = "gds-idea"
url = "https://co-cddo.github.io/gds-idea-pypi/simple/"
explicit = true
```

Once done, adding any internal package to any project is just:

```bash
uv add gds-idea-app-kit --index gds-idea
```

uv will still write the full `[[tool.uv.index]]` entry into the project's `pyproject.toml` so the project is self-contained for CI and other team members.

## Installing packages

The key benefit of this index over pinning to git tags is **version constraints** — you can now use `>=`, `~=`, and ranges instead of locking to a specific commit or tag:

```bash
# Before: locked to an exact git tag
uv add "gds-idea-app-kit @ git+https://github.com/co-cddo/gds-idea-app-kit@v0.2.6"

# Now: version constraints, resolved from the index
uv add gds-idea-app-kit --index gds-idea=https://co-cddo.github.io/gds-idea-pypi/simple/
```

This adds the package to your `pyproject.toml` and automatically sets up the index and source pin:

```toml
[project]
dependencies = [
    "gds-idea-app-kit>=0.2.7",
]

[tool.uv.sources]
gds-idea-app-kit = { index = "gds-idea" }

[[tool.uv.index]]
name = "gds-idea"
url = "https://co-cddo.github.io/gds-idea-pypi/simple/"
explicit = true  # only used for packages explicitly pinned above; PyPI is unchanged
```

Once the index is in your `pyproject.toml`, adding more internal packages is just:

```bash
uv add cognito-auth --index gds-idea
uv add llmbo-bedrock --index gds-idea
```

You can adjust the version constraint to whatever you need:

```toml
"gds-idea-app-kit>=0.2.0"   # any version from 0.2.0 onwards
"gds-idea-app-kit~=0.2.0"   # compatible release: >=0.2.0, <0.3.0
"gds-idea-app-kit>=0.2,<1"  # range
```

## Packages available

| Package | Repo |
|---|---|
| `gds-idea-app-kit` | [co-cddo/gds-idea-app-kit](https://github.com/co-cddo/gds-idea-app-kit) |
| `cognito-auth` | [co-cddo/gds-idea-app-auth](https://github.com/co-cddo/gds-idea-app-auth) |
| `llmbo-bedrock` | [co-cddo/gds-idea-llmbo](https://github.com/co-cddo/gds-idea-llmbo) |
| `gds-idea-box2-0` | [co-cddo/gds-idea-box2.0](https://github.com/co-cddo/gds-idea-box2.0) |

## Adding a new package

### 1. Add the repo to `config.toml`

Open `config.toml` in this repo and add an entry:

```toml
[[packages]]
repo = "your-new-repo-name"
```

Merge the change to `main` — the index will pick it up on the next scheduled rebuild.

### 2. Set up wheel builds in the package repo

The index links directly to release assets, so the package repo needs to attach a wheel to each GitHub Release. Add these steps to the repo's release workflow (`.github/workflows/release.yml`):

```yaml
      - uses: astral-sh/setup-uv@v7

      - name: Build wheel and sdist
        run: uv build

      - name: Upload artifacts to release
        run: gh release upload "${{ github.ref_name }}" dist/*.whl dist/*.tar.gz
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      # Automatic index rebuild — uncomment once PYPI_INDEX_TOKEN is configured
      # - name: Trigger PyPI index rebuild
      #   run: |
      #     gh api repos/co-cddo/gds-idea-pypi/dispatches \
      #       -f event_type=rebuild-index
      #   env:
      #     GH_TOKEN: ${{ secrets.PYPI_INDEX_TOKEN }}
```

### 3. Trigger a rebuild

The index rebuilds automatically every 6 hours. To get a new package or release into the index immediately, trigger a manual rebuild:

**[Actions → Rebuild PyPI Index → Run workflow](https://github.com/co-cddo/gds-idea-pypi/actions/workflows/publish.yml)**

> **Automatic rebuild on release is coming.** Once a `PYPI_INDEX_TOKEN` (a PAT with `repo` scope on this repo) is configured as an org-level secret, the commented-out step above can be enabled in each package repo. Releases will then trigger an instant index rebuild without any manual steps.

## How it works

The [publish workflow](.github/workflows/publish.yml) runs on a schedule, on manual trigger, and on `repository_dispatch` events. It:

1. Reads `config.toml` for the list of repos to scan
2. Queries the GitHub API for all releases on each repo
3. For releases with `.whl` assets — links directly to the GitHub Release download URL
4. For releases without built assets — links to the auto-generated source tarball as a fallback (note: uv cannot install from these — see step 2 above)
5. Generates PEP 503-compliant HTML and deploys to GitHub Pages
