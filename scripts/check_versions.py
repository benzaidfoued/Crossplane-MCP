"""Fail CI/release when Python, chart, changelog or tag versions disagree."""

import os
import tomllib
from pathlib import Path

import yaml

from crossplane_compass import __version__

root = Path(__file__).resolve().parents[1]
project = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
chart = yaml.safe_load((root / "charts/crossplane-compass/Chart.yaml").read_text())
assert project == __version__ == chart["version"] == chart["appVersion"]
assert f"## [{project}]" in (root / "CHANGELOG.md").read_text()
if os.getenv("GITHUB_REF_TYPE") == "tag":
    assert os.environ["GITHUB_REF_NAME"] == f"v{project}"
print(f"Versions consistent: v{project}")
