# gds-idea-pypi — Plan

## Overview

A lightweight Python tool that generates a static PEP 503 PyPI index hosted on GitHub Pages. It reads a list of GitHub repos from `config.toml`, discovers their releases and assets via the GitHub API, and produces HTML pages that link directly to wheel/sdist files on GitHub Releases. No wheel building — just index generation.

## Architecture

```
gds-idea-pypi/
├── pyproject.toml
├── config.toml
├── src/
│   └── gds_idea_pypi/
│       ├── __init__.py
│       ├── __main__.py        # entry point with argparse
│       ├── config.py          # load config.toml
│       ├── github.py          # GitHub API: releases + assets
│       └── index.py           # PEP 503 HTML generation
├── .github/
│   └── workflows/
│       └── publish.yml        # deploy to GitHub Pages
└── .gitignore
```

## Deliverable 1: Index Generator (this repo)

### config.toml

```toml
[index]
org = "co-cddo"
base_url = "https://co-cddo.github.io/gds-idea-pypi/simple"

[[packages]]
repo = "gds-idea-app-auth"

[[packages]]
repo = "gds-idea-app-kit"

[[packages]]
repo = "gds-idea-llmbo"

[[packages]]
repo = "gds-idea-box2.0"
```

### github.py

- `get_releases(org, repo)` — fetches all releases via GitHub API
- For each release, categorizes assets:
  - `.whl` file → record URL (ideal)
  - Built `.tar.gz` (not auto-generated) → record URL
  - No built assets → use the auto-generated source tarball URL as fallback
- Computes sha256 of each asset by streaming the download
- Parses tag names to extract version: strips `v` prefix, handles quirks
- Returns structured data per release

### index.py

Generates:
- `simple/index.html` — root listing all packages
- `simple/{normalized-name}/index.html` — per-package page with download links

All links are absolute URLs pointing to GitHub Releases. No files stored locally — just HTML.

### __main__.py

```
python -m gds_idea_pypi rebuild                    # full rebuild → site/
python -m gds_idea_pypi rebuild --output _site/     # custom output dir
python -m gds_idea_pypi rebuild --dry-run           # show what would be indexed
```

### publish.yml (GitHub Actions)

```yaml
on:
  workflow_dispatch: {}
  repository_dispatch:
    types: [rebuild-index]
```

Installs deps, runs rebuild, deploys via `actions/upload-pages-artifact` + `actions/deploy-pages`.

### Dependencies

- `httpx` — HTTP client for GitHub API + asset hashing

## Deliverable 2: Reusable Release Workflow for Package Repos

A reusable workflow that each package repo calls to:
1. Build the wheel + sdist (`python -m build`)
2. Attach them to the GitHub Release (`gh release upload`)
3. Trigger the index rebuild (`gh api repos/.../dispatches`)

## Asset Strategy

For each release in each repo:
- `.whl` file in assets → link to it (preferred)
- Built `.tar.gz` in assets → link to it
- No built assets → link to auto-generated source tarball (fallback — pip/uv can install from source if pyproject.toml exists)

## Consumer Usage

```toml
# pyproject.toml in a consuming project
[[tool.uv.index]]
name = "cddo"
url = "https://co-cddo.github.io/gds-idea-pypi/simple/"

[project]
dependencies = [
    "cognito-auth>=0.3.0",
    "llmbo-bedrock>=0.2.0",
]
```

Or with pip:
```bash
pip install --extra-index-url https://co-cddo.github.io/gds-idea-pypi/simple/ cognito-auth>=0.3.0
```

## Implementation Order

1. Scaffold project (pyproject.toml, package structure, .gitignore)
2. config.py — config loading
3. github.py — release + asset discovery
4. index.py — PEP 503 HTML generation
5. __main__.py — wire up with argparse
6. Test locally with --dry-run against the 4 repos
7. publish.yml — GitHub Actions workflow
8. Reusable release workflow for package repos
