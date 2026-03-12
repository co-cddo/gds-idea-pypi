# AGENTS.md — Coding agent guidance for gds-idea-pypi

## What this project is

A static PEP 503-compliant PyPI index generator backed by GitHub Releases. It reads a
`config.toml` listing repos in a GitHub org, queries the GitHub API for release assets
(wheels, sdists), and generates HTML pages deployed to GitHub Pages. Run as
`python -m gds_idea_pypi`.

---

## Environment

- **Python:** `>=3.11` (stdlib `tomllib` used; `match` statements and `X | Y` union syntax expected)
- **Package manager:** `uv` — use `uv sync` to install, `uv build` to produce a wheel/sdist
- **Only runtime dependency:** `httpx>=0.27`
- **Build backend:** `hatchling` with a `src/` layout

```bash
uv sync                                          # install dependencies into .venv
python -m gds_idea_pypi --help                   # confirm the install works
python -m gds_idea_pypi --output site/ --dry-run # run without writing files or fetching hashes
python -m gds_idea_pypi --output site/ --verbose # verbose output
uv build                                         # produce dist/*.whl and dist/*.tar.gz
```

---

## Tests

There is currently no test suite. When tests are added, the expected framework is `pytest`.

```bash
# Run all tests (once a tests/ directory exists)
pytest

# Run a single test file
pytest tests/test_github.py

# Run a single test by name
pytest tests/test_github.py::test_parse_version_from_tag

# Run with verbose output
pytest -v
```

When writing tests, place them in `tests/` at the project root. Mirror the module structure:
`tests/test_github.py`, `tests/test_config.py`, etc. Use plain `assert` statements — no
`unittest.TestCase`.

---

## Linting and formatting

No linting or formatting tooling is configured yet. The expected tools when added are:

- **`ruff`** for linting and formatting (replaces flake8, isort, pyupgrade)
- **`mypy`** for static type checking

Until configured, follow the style conventions below manually.

---

## Code style

### Every module must start with

```python
"""One-line module docstring."""

from __future__ import annotations
```

`from __future__ import annotations` is required in every file — it enables PEP 563 postponed
annotation evaluation, which makes forward references and `X | Y` union syntax safe on Python 3.11.

### Import order (PEP 8)

1. Standard library
2. Third-party packages
3. Local relative imports

```python
# stdlib
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

# third-party
import httpx

# local — always relative, never absolute package imports
from .config import load_config
from .github import get_releases, make_client
```

### Type annotations

- **All** function parameters and return types must be annotated, including `-> None`.
- Use `X | Y` union syntax — never `Optional[X]` or `Union[X, Y]`.
- Use lowercase generics: `list[str]`, `dict[str, int]` — never `List`, `Dict`.
- No `TypeVar`, `Protocol`, or `Generic` unless strictly necessary.

```python
def parse_version_from_tag(tag: str) -> str | None: ...
def load_config(path: Path | None = None) -> IndexConfig: ...
def get_releases(org: str, repo: str, client: httpx.Client) -> PackageReleases: ...
```

### Dataclasses

Prefer `@dataclass` for data-holding types. Use `field(default_factory=list)` for mutable
defaults. Annotate all fields.

```python
@dataclass
class Release:
    tag: str
    version: str
    assets: list[Asset] = field(default_factory=list)
```

### Formatting conventions

- 4-space indentation, no tabs.
- Maximum line length: 99 characters (follow existing code).
- Trailing commas in multi-line structures.
- Use `f-strings` for string interpolation; use `%`-style only in `logging` calls (avoids
  eager formatting when the log level is suppressed).

```python
logger.warning("%s/%s: skipping tag %r", org, repo, tag)   # correct
logger.warning(f"{org}/{repo}: skipping tag {tag!r}")       # avoid in logging calls
```

---

## Naming conventions

| Entity | Convention | Examples |
|---|---|---|
| Files | `snake_case.py` | `config.py`, `github.py`, `index.py` |
| Classes / dataclasses | `PascalCase` | `PackageConfig`, `IndexConfig`, `Release` |
| Public functions | `snake_case` | `load_config`, `get_releases`, `generate_index` |
| Module-private functions | `_snake_case` | `_normalise_name`, `_compute_sha256` |
| Public module constants | `UPPER_SNAKE_CASE` | `INDEX_URL` |
| Private module constants | `_UPPER_SNAKE_CASE` | `_WHEEL_RE`, `_TAG_VERSION_RE` |
| Variables / parameters | `snake_case` | `output_dir`, `compute_hashes` |
| Module-level logger | `logger` | `logger = logging.getLogger(__name__)` |

**Note:** The existing function `_normalise_name` uses British spelling — preserve that spelling
when modifying or calling that function. Use standard American spelling everywhere else.

**Keyword-only arguments:** use `*` to enforce keyword-only for boolean flags and optional
configuration parameters:

```python
def get_releases(org: str, repo: str, client: httpx.Client, *, compute_hashes: bool = True): ...
```

---

## Docstrings

Every module, public class, and public function must have a docstring. Use imperative mood.

```python
def generate_index(packages: list[PackageReleases], output_dir: Path) -> None:
    """Generate the full static PEP 503 index to output_dir/simple/."""
```

Multi-line docstrings: one-line summary, blank line, then detail.

Private helper functions should have a docstring if their behaviour is non-obvious.

---

## Error handling

- **Library functions** (`config.py`, `github.py`, `index.py`): raise specific, typed exceptions
  with descriptive messages. Do not catch broad exceptions internally.
  ```python
  raise FileNotFoundError(f"Config file not found: {path}")
  raise ValueError("config.toml: [index].org is required")
  ```
- **HTTP responses:** call `resp.raise_for_status()` immediately after every response; let
  `httpx.HTTPStatusError` propagate from library functions.
- **CLI entry point** (`__main__.py`): catch broad `Exception` with `logger.exception(...)` for
  per-item failures and `continue` — one failing repo should not abort the whole run.
- **Unrecoverable startup errors:** use `sys.exit(1)` after logging the error.
- **Soft/skippable issues:** use `logger.warning()` and continue — never silently swallow.
- Do not define custom exception classes unless there is a clear, repeated need.

---

## Module responsibilities

| Module | Responsibility |
|---|---|
| `config.py` | Load and validate `config.toml` via `tomllib`; return typed dataclasses |
| `github.py` | GitHub API client; discover releases, categorise assets, compute SHA-256 hashes |
| `index.py` | Render PEP 503 HTML index pages and the human-friendly landing page |
| `__main__.py` | CLI wiring (argparse), logging setup, orchestration; no business logic |

Keep this separation clean. `index.py` should not call GitHub. `github.py` should not write
files. `__main__.py` should not contain logic that belongs in a library function.

---

## Configuration (`config.toml`)

```toml
[index]
org = "co-cddo"
base_url = "https://co-cddo.github.io/gds-idea-pypi/simple/"

[[packages]]
repo = "gds-idea-app-kit"

[[packages]]
repo = "another-repo"
```

Loaded via `config.load_config(path)`. Raises `FileNotFoundError` or `ValueError` on invalid
input — do not add silent fallbacks.

---

## CI/CD

Two workflows in `.github/workflows/`:

- **`publish.yml`** — rebuilds the index and deploys to GitHub Pages. Triggers: push to `main`
  when `config.toml` changes, schedule every 6 hours, manual `workflow_dispatch`, and
  `repository_dispatch` with type `rebuild-index`. Uses Python 3.12 and `pip install .`.
- **`pypi-release.yml`** — reusable workflow (`workflow_call`) for downstream package repos.
  Runs `uv build` and uploads `dist/*.whl` and `dist/*.tar.gz` to the GitHub Release.

When modifying `publish.yml`, do not change the concurrency group (`pages`) or set
`cancel-in-progress: true` — queued deploys must not be skipped.
