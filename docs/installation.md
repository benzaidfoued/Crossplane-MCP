# Installation and configuration

## Local Python / stdio

Run `uv sync --frozen` in the source tree, then configure your MCP host as shown in README. Alternatively install the release wheel into a virtual environment:

```bash
python -m venv .venv
.venv/bin/pip install ./crossplane_compass-0.1.0-py3-none-any.whl
.venv/bin/crossplane-compass --context staging=staging --groups platform.example.org
```

A wheel resolves dependencies using the package metadata. The source checkout with `uv.lock` provides the reproducible dependency set used by CI.

| Flag | Default | Meaning |
|---|---|---|
| `--transport` | `stdio` | `stdio` or `http` |
| `--context ALIAS=CONTEXT` | default context / in-cluster | Repeat for an explicit cluster allowlist |
| `--groups` | empty additional groups | Comma-separated exact XR/provider API groups |
| `--namespaces` | no namespace restriction | Comma-separated allowed namespaces |
| `--deny-cluster-scoped` | false | Block cluster-scoped object access; CRD discovery remains available |
| `--enable-server-dry-run` | false | Permit dry-run PATCH calls; requires matching RBAC |
| `--host`, `--port` | `127.0.0.1`, `8080` | HTTP listen address |
| `--allowed-hosts` | loopback names | Comma-separated Host values; include `:*` for any port |
| `--token-file` | none | Required for HTTP; at least 32 characters |

Base groups are `apiextensions.crossplane.io`, `pkg.crossplane.io`, `ops.crossplane.io`, `protection.crossplane.io`. `COMPASS_GROUPS`, `COMPASS_NAMESPACES`, `COMPASS_ALLOWED_HOSTS`, and `COMPASS_TOKEN_FILE` supply corresponding flag defaults. There is no implicit all-context scan.

Example multi-control-plane setup:

```bash
uv run crossplane-compass   --context nonprod=nonprod-context --context prod=prod-context   --groups platform.example.org,authorization.azure.upbound.io
```

Each cluster shares this process's group/namespace policy. Use separate instances when policies or trust boundaries differ. Only load kubeconfigs you trust: standard Kubernetes exec credential plugins execute locally as part of authentication.

## Helm

README gives a complete source-chart installation. The source chart's default image is a locally built `crossplane-compass:0.1.0`; it is not a promise that Docker Hub hosts that name. Override repository/tag when publishing manually. The release workflow stamps the packaged chart with its published GHCR image digest.

After a successful release:

```bash
helm upgrade --install compass oci://ghcr.io/YOUR_OWNER/charts/crossplane-compass   --version 0.1.0 --namespace compass --create-namespace   --set auth.existingSecret=crossplane-compass-auth   --set 'access.groups={platform.example.org,authorization.azure.upbound.io}'   --wait
```

The Secret must exist in the release namespace. Use an ExternalSecret, SealedSecret or your organization's GitOps secret mechanism. Never put a real token in Helm values, a Git repository or an LLM prompt. Mounted Secret rotation is honored without a restart after Kubernetes updates the volume.

### Namespace isolation

`access.namespaces` enforces object access in the server, including graph children. With a nonempty list, a namespace is mandatory for namespaced list/get calls; cross-namespace lists are rejected. Cluster-scoped data can still be accessed unless `access.clusterScoped=false`.

The default ClusterRole grants reads across namespaces for the configured custom API groups and events. **Application namespace policy does not narrow the service account's underlying permissions.** For strong tenant isolation, set `rbac.create=false`, supply a dedicated service account and your own Roles/RoleBindings, plus the required cluster-scoped CRD read permissions. Deployment service accounts should not carry unrelated privileges.

### Network and auth

The default NetworkPolicy permits ingress from same-namespace pods labeled `compass-client: "true"`, and outbound DNS plus TCP 443/6443 for the API server. It depends on CNI enforcement. It does not restrict API egress by destination IP; add environment-specific destination policies where required. Customize `networkPolicy.apiPorts` for nonstandard API endpoints. Some CNIs differ on service DNAT and API-server routing; verify in your cluster.

Port-forward is for local administration. To serve clients in another namespace, supply an appropriate NetworkPolicy and disable the packaged one if needed. For external access, put the service behind TLS, add the gateway host to `server.additionalAllowedHosts`, and preserve the Authorization header. Compass does not implement OAuth discovery; choose an MCP client/gateway that supports configured bearer headers.

### Optional server-side validation

Keep this off for a purely read-only service account. To enable validation through the API server:

```yaml
server:
  enableServerDryRun: true
access:
  groups: [platform.example.org]
rbac:
  dryRunRules:
    - apiGroups: [platform.example.org]
      resources: [databases]
```

The application sends `dryRun=All`, `fieldValidation=Strict`, `force=false`, with field manager `crossplane-compass`. The API-server path may invoke admission webhooks and requires their dry-run support. RBAC cannot limit patch permission to dry-run calls: compromise of this service account could bypass the application. Scope the grant narrowly and use a dedicated validation instance if necessary.

## Flux example

[`examples/flux/helmrelease.yaml`](../examples/flux/helmrelease.yaml) uses an OCIRepository plus HelmRelease. Replace `YOUR_OWNER`, API groups and the existing Secret name. Flux CRD/API support depends on your installed Flux release; this example targets OCIRepository `v1` and HelmRelease `v2`. Apply via your existing GitOps workflow. Creating a claim or XR remains a reviewed repository change.

## Troubleshooting

| Symptom | Check |
|---|---|
| HTTP 401 | Correct bearer header; 32+ character mounted token; secret file readable by group 10001 |
| HTTP 421 | Add the actual request Host (and port pattern) to allowed hosts |
| Pod pending / CreateContainerConfigError | Existing token Secret, image path, pull permissions |
| API group not allowed | Add the exact group to `access.groups` and reconcile Helm |
| Namespace required | Supply an explicitly allowed namespace; do not use an all-namespace list |
| RBAC denied | Verify service account RoleBindings; the server intentionally omits raw API error bodies |
| Kind/version not served | Inspect installed CRD; wait up to 60 seconds for discovery refresh |
| External lookup has no result | Continue all pages; confirm kind, namespace and exact provider import ID |
| Desktop auth fails | KUBECONFIG, PATH and installed cloud exec plugin; trusted context name |
