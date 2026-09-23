# Releases and publication

## Initial delivery status

The delivery archive contains the complete source tree, distributable wheel/sdist/chart, SHA256SUMS and a Git bundle with an annotated `v0.1.0` tag. These are **local artifacts**, not evidence of a public GitHub release or published registry packages. No remote owner/repository was supplied during preparation.

## Publish the first release

1. Create an **empty repository** in your chosen GitHub account/organization named `crossplane-compass` (or adjust the image name examples).
2. Unpack the delivery archive. Restore the git history and tag from the bundle:

```bash
git clone crossplane-compass-v0.1.0.bundle crossplane-compass
cd crossplane-compass
git remote remove origin
git remote add origin https://github.com/YOUR_OWNER/crossplane-compass.git
git push -u origin main
```

3. Enable GitHub Actions and private vulnerability reporting. Configure `main` branch protection, required CI checks and maintainer reviews. Confirm GHCR package permissions. Use a public repository/package visibility if public installation is intended; the workflow does not change visibility for you.
4. Wait for **all CI jobs**, including both kind/Crossplane versions, to pass. Inspect any failures and fix them before pushing the tag. If the initial tag needs correction before it is published, create a corrected local release commit/tag; do not overwrite a public tag.
5. Publish the prepared tag:

```bash
git push origin v0.1.0
```

This reruns the full reusable CI gate, builds and publishes linux/amd64 and linux/arm64 images, produces SBOM/provenance, packages a digest-pinned Helm chart, pushes it to `ghcr.io/YOUR_OWNER/charts`, attests release files and creates a GitHub release with checksums.

No PyPI publication is configured. Install from the release wheel, source or container. Add trusted PyPI publishing later after reserving an appropriate package name.

## Version policy

Use `vMAJOR.MINOR.PATCH` git tags. Application/Python/chart versions omit the `v` prefix. During 0.x, additive or breaking contract changes belong in a minor release with explicit migration notes; backward-compatible fixes use a patch release. Never move a public release tag or reuse a published chart version.

For each release, update together:

- `pyproject.toml` and `src/crossplane_compass/__init__.py`
- `charts/crossplane-compass/Chart.yaml` version and appVersion
- `CHANGELOG.md`, `docs/releases/vX.Y.Z.md`, README/examples where version-specific
- `uv.lock` using `uv lock`
- CI's locally built image version and protocol tests when they intentionally assert the released version

Run `make check`, `make build`, Helm checks and live integration. Commit, merge and tag the reviewed commit with `git tag -a vX.Y.Z -m 'Crossplane Compass vX.Y.Z'`. Tag protection should restrict maintainers with release authority.

## Verify and rollback

Download artifacts and run `sha256sum -c SHA256SUMS` on Linux (`shasum -a 256` for individual verification on macOS). Verify GitHub artifact attestations with your organization's policy and the GitHub CLI. Image provenance is attached to the OCI image; the packaged chart defaults to the release digest.

Roll back the **MCP server deployment** by selecting a previously released chart/image digest through GitOps or Helm history. This does not roll back cloud infrastructure or Crossplane compositions. The MCP server does not persist resource changes.

If a workflow fails after publishing one artifact, do not blindly move tags or overwrite charts. Inspect which artifacts exist, repair the release process, and publish a new patch version when immutable artifacts conflict. No `latest` tag is published intentionally.
