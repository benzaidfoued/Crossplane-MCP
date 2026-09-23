# Contributing to Crossplane Compass

Thanks for helping make Crossplane operations easier to understand. Small, tested improvements are preferred over large collections of shallow tools.

## 1. Set up

Requirements: Python 3.12+, uv 0.12.17+, Git. Helm 3.19+ for chart work; Docker/kind/kubectl for live-cluster integration.

```bash
git clone YOUR_REPOSITORY_URL
cd crossplane-compass
uv sync --frozen
git switch -c fix/short-description
make check
```

Unit and protocol tests require no Kubernetes cluster, credentials or cloud account. The subprocess test uses a mock Kubernetes HTTP endpoint and the real official client.

## 2. Find the right module

| Change | Files |
|---|---|
| Crossplane analysis | `src/crossplane_compass/analysis.py`, `service.py` |
| API discovery/auth/scope | `kube.py` |
| Tool contract / MCP transport | `server.py` |
| Output safety | `safety.py` |
| Deployment | `charts/crossplane-compass/`, `Dockerfile` |
| CI/release | `.github/workflows/`, `scripts/` |

See [architecture](docs/architecture.md) before adding behavior that affects access or writes.

## 3. Add or improve a tool

1. Open an issue describing the user problem and expected evidence. Confirm generic list/get or a composed workflow cannot solve it already.
2. Implement a typed method on `Compass`. Route every cluster operation through `self.kube(cluster)` and the Kubernetes adapter. Do not create arbitrary URL/path, subprocess or secret-reading escape hatches.
3. Register the method in `TOOLS` and `DESCRIPTIONS` in `server.py`. Set appropriate MCP annotations if its semantics differ from the standard read-only tools.
4. Add tests for success and at least one meaningful failure: access denial, malformed data, unsupported scope, pagination or partial errors.
5. Update `docs/tools.md`, examples and CHANGELOG. Tool names, parameter names and structured result fields are a public contract.
6. If adding a tool, update protocol tests and smoke-test counts. The explicit count prevents unnoticed tool exposure changes.

Do not turn all exceptions into empty results. Do not infer absence from RBAC denial. Do not claim cloud drift or safe deletion from incomplete Kubernetes evidence. Preserve truncation, continuation and partial-error fields.

## 4. Validate

```bash
make check
make build
helm lint charts/crossplane-compass --strict
uv run python scripts/check_chart.py
```

The test suite enforces 85% aggregate line coverage. Coverage is a guardrail, not a reason to write tests that merely repeat implementation. Add evidence-driven regression tests for every bug.

For integration, use a **disposable kind cluster** and follow the commands in `.github/workflows/ci.yml`. `scripts/cluster_smoke.py` creates an XRD and XR and is not a production-cluster diagnostic script. CI tests Crossplane 1.20.0 and 2.0.0, builds the container, installs the chart and connects a real HTTP MCP client.

For dependency updates: run `uv lock --upgrade-package PACKAGE`, review the lockfile diff, run tests/audit, and explain the upgrade. Do not casually regenerate every dependency in unrelated PRs.

## 5. Submit

Use a clear commit subject such as `fix: resolve cluster-scoped children without a namespace`. Open a PR with the problem, behavioral change, test evidence, compatibility impact and any new permissions. One maintainer review and green required checks are expected. Maintainers must configure branch protection after publication; workflow files cannot enable repository settings.

No CLA is required. By contributing, you agree your contribution is licensed under the repository's Apache-2.0 license. Do not include employer-owned code without permission or copy code from incompatible licenses.

## Review and maintenance

Treat users and contributors respectfully. Discuss concrete technical tradeoffs, accept corrections, and never publish private credentials, identifiers or harassment. See CODE_OF_CONDUCT.md. Security reports follow SECURITY.md. Maintainers own release decisions; new maintainers are appointed through a documented repository discussion.

Release instructions are in [docs/releases.md](docs/releases.md). Contributor PRs should not push release tags or publish packages.
