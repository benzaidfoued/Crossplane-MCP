# Validation evidence — v0.1.0

Executed on 2026-09-23 in a Linux/Python 3.12.14 environment. This is a record of observed checks, not a production certification or zero-defect guarantee.

| Check | Observed result |
|---|---|
| Unit, service, HTTP protocol and stdio subprocess tests | **57 passed** |
| Aggregate source line coverage | **86.21%**, above the 85% CI gate |
| Ruff lint and formatting | Passed |
| MCP stdio subprocess with official client | Initialize, list 24 tools, get object, denied namespace, resource/prompt discovery, server-side dry-run request passed |
| Kubernetes client integration | Real official client → mock HTTP API; discovery, deserialization and dry-run wire encoding exercised |
| Streamable HTTP MCP | Initialize, list/call tools, bearer rejection, token rotation, Host rejection, health/metrics passed |
| Helm 3.19.0 lint | Passed; only informational recommendation to add a chart icon |
| Helm variants | 6 valid configurations and 4 expected-invalid configurations checked |
| Kubernetes manifest schema validation | kubeconform 0.7.0: 6 valid resources, 0 invalid/errors/skipped |
| GitHub Actions workflow syntax | actionlint 1.7.7 passed |
| Runtime dependency audit | pip-audit: no known vulnerabilities in the locked runtime dependencies at audit time |
| Python wheel/source distribution and Helm chart packaging | Built successfully |
| Application, Python, chart and changelog versions | All agree on 0.1.0; release tag checked by CI |

One upstream test-only Starlette warning reports its httpx TestClient integration is deprecated in favor of httpx2. It does not fail the protocol tests. The runtime MCP client/server uses its supported locked httpx dependency.

## Not executed in this environment

- No Docker daemon or live Kubernetes cluster was available. Container builds, Helm installation, CNI enforcement, real admission/defaulting and Crossplane controller behavior were **not tested locally**.
- The repository includes a required CI job that installs Crossplane 1.20.0 and 2.0.0 into disposable kind clusters, creates a real XRD/XR, exercises discovery/validation/planning, builds the image, deploys Helm and connects an HTTP MCP client. This job must pass in your GitHub repository before publication.
- No cloud provider credentials or Azure/AWS/GCP APIs were used. Provider-specific import formats, cloud drift, replacement behavior and production migrations were not validated.
- No public GitHub repository, OCI image/chart, attestations or release page was created here. Release automation creates them only after the tag is pushed and its gates pass.
- Python 3.13 is configured in CI, but this local validation used Python 3.12.

## Reproduce

```bash
uv sync --frozen
make check
uv build
helm lint charts/crossplane-compass --strict
uv run python scripts/check_chart.py
helm template compass charts/crossplane-compass > /tmp/compass.yaml
kubeconform -strict -summary /tmp/compass.yaml
actionlint
uv export --frozen --no-dev --no-emit-project > /tmp/compass-requirements.txt
uv run pip-audit -r /tmp/compass-requirements.txt --require-hashes --disable-pip
```

The subprocess regression test specifically catches Kubernetes response-type mapping errors that pure fake-client tests would miss. Dry-run tests inspect the HTTP method, media type, request body and `dryRun=All` query; they do not substitute for real API-server admission tests.
