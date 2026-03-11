# gds-idea-pypi

An internal PyPI index for GDS IDEA packages, hosted on GitHub Pages.

- **[Latest versions, install instructions & developer setup](https://co-cddo.github.io/gds-idea-pypi/)** — start here
- **Index URL:** `https://co-cddo.github.io/gds-idea-pypi/simple/`
- **[Rebuild PyPI Index workflow](https://github.com/co-cddo/gds-idea-pypi/actions/workflows/publish.yml)** — trigger a manual rebuild

## Adding a new package

### 1. Add the repo to `config.toml`

Open [`config.toml`](config.toml) in this repo and add an entry:

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
