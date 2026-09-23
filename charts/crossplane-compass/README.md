# Crossplane Compass Helm chart

See the repository's [installation guide](../../docs/installation.md) for full instructions and security tradeoffs.

```bash
helm lint . --strict
helm upgrade --install compass . -n compass --create-namespace   --set image.repository=ghcr.io/YOUR_OWNER/crossplane-compass   --set image.tag=v0.1.0   --set auth.existingSecret=crossplane-compass-auth
```

The existing Secret must contain a `token` key with 32+ random characters. The source chart defaults to a local development image; a chart produced by the release workflow embeds its published image digest.

| Values | Purpose |
|---|---|
| `access.groups` | Exact extra custom API groups; also used in read RBAC |
| `access.namespaces` | Application namespace allowlist; does not narrow ClusterRole permissions |
| `access.clusterScoped` | Permit cluster-scoped object reads |
| `auth.existingSecret`, `auth.key` | Existing bearer-token Secret/key |
| `image.repository/tag/digest` | Image source; digest takes precedence |
| `server.additionalAllowedHosts` | Gateway/service Host names, optionally with `:*` |
| `server.enableServerDryRun` | Opt-in nonpersistent API validation |
| `rbac.dryRunRules` | Explicit custom group/resources allowed patch when dry-run enabled |
| `rbac.create`, `serviceAccount.*` | Bring dedicated tenant RBAC/identity if needed |
| `networkPolicy.*` | Same-namespace client labels, DNS and API egress ports |
| `replicaCount`, `resources` | Stateless replicas and pod resource sizing |

Service type is deliberately restricted to ClusterIP. Default API groups are read-only; no core Secret or wildcard API-group rules are generated. Unknown tenant/provider groups must be added explicitly. Probes use `/healthz` and `/readyz`; `/metrics` needs bearer auth.
