"""Stamp distribution chart with the image digest produced by this release."""

import os
from pathlib import Path

import yaml

p = Path("charts/crossplane-compass/values.yaml")
values = yaml.safe_load(p.read_text())
values["image"].update(
    repository=os.environ["IMAGE_NAME"],
    tag=os.environ["GITHUB_REF_NAME"],
    digest=os.environ["IMAGE_DIGEST"],
)
p.write_text(yaml.safe_dump(values, sort_keys=False))
