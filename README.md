# gds-idea-pypi

An internal PyPI index for GDS IDEA packages, hosted on GitHub Pages.

**Installing or using packages?** See the [GDS IDEA Package Index](https://co-cddo.github.io/gds-idea-pypi/) for install instructions and package listings.

- **Index URL:** `https://co-cddo.github.io/gds-idea-pypi/simple/`
- **[Rebuild PyPI Index workflow](https://github.com/co-cddo/gds-idea-pypi/actions/workflows/publish.yml)** — trigger a manual rebuild

## Maintaining this index

### Adding a new package

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

### When something fails

One flaky request should not remove a package from the index, so failures are contained and reported rather than aborting the run:

- **SHA-256 hashes:** each file is downloaded once to compute its hash. Transient failures (5xx, 429, network errors) are retried 3 times with backoff. If a file still fails, it stays in the index **without a hash** (still installable) and the failure is reported. The next rebuild normally restores the hash.
- **Whole-repo failures** (for example the releases listing call fails): that repo is left out of the index for this build and the failure is reported.
- **Either way the index is still deployed**, so one problem does not block updates to other packages. The run then **fails** (red) and lists what went wrong as annotations on the run page and in the job summary.

A red run on its own does not mean the index is broken, but check the summary: a repo listed as missing means that package is absent from the live index until the next successful rebuild.

The CLI exits with code `3` when the index was written but there were errors, `1` for startup errors (nothing written), and `0` otherwise.

## Development

```bash
uv sync                                # install dependencies, including pytest
uv run pytest                          # run the tests
python -m gds_idea_pypi --output site/ --dry-run   # scan without writing or hashing
```

### Keeping the schedule alive

GitHub automatically disables scheduled workflows in public repos after 60 days without repository activity. To prevent this, scheduled runs also commit a date stamp (`keepalive.txt`) to an orphan `keepalive` branch, at most once a week. The branch shares no history with `main` and is never deployed.

If the schedule is ever disabled anyway, re-enable it with `gh workflow enable publish.yml` and check whether the keepalive branch is still being updated.
