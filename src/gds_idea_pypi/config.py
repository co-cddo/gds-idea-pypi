"""Load and validate config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PackageConfig:
    repo: str


@dataclass
class IndexConfig:
    org: str
    base_url: str
    packages: list[PackageConfig] = field(default_factory=list)


def load_config(path: Path | None = None) -> IndexConfig:
    """Load configuration from a TOML file.

    Searches for config.toml in the current directory if no path is given.
    """
    if path is None:
        path = Path("config.toml")

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    index = raw.get("index", {})
    org = index.get("org")
    base_url = index.get("base_url", "")

    if not org:
        raise ValueError("config.toml: [index].org is required")

    packages = [
        PackageConfig(repo=p["repo"]) for p in raw.get("packages", [])
    ]

    if not packages:
        raise ValueError("config.toml: at least one [[packages]] entry is required")

    return IndexConfig(org=org, base_url=base_url, packages=packages)
