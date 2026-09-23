# Reference project review and differentiation

Reviewed source: [shilucloud/crossplane-mcp-server](https://github.com/shilucloud/crossplane-mcp-server), commit **2c9220282f059f1c9e174fb65707561fc2afcb9c**, retrieved 2026-09-23. Findings describe that snapshot, not all future releases. Compass is an independent Python implementation, not a copied Go fork.

The reference already has useful provider, XR, composition, condition, dependency, validation and reconcile tools (21 registered tools), plus Helm packaging, metrics and tests. It is not simply a generic Kubernetes wrapper. Compass focuses on deeper contracts and operational safety rather than claiming each feature is novel.

| Observed source behavior | Why it matters | Compass behavior |
|---|---|---|
| `charts/.../templates/rbac.yaml` grants get/list/watch and patch on all API groups/resources; also lists Secrets | Broad credentials/write blast radius | Explicit custom API groups, no Secret access or persistent write tools; optional dry-run patch permissions are narrow and documented |
| `cmd/server/main.go` serves `/mcp` without in-process auth | Needs a trusted boundary/proxy | Mandatory bearer token for HTTP, host checks, token-file rotation; TLS remains a gateway responsibility |
| `tools/get_xr_tree.go` uses `kindToPlural` and reuses parent namespace for children | Irregular plurals and mixed child scopes can fail | Installed CRD plural/scope plus API discovery, independent scope per child |
| Same tree code reads `spec.crossplane.resourceRefs` and compositionRef | That path alone does not cover legacy spec layouts and claims | Supports legacy/v1 spec and v2 spec.crossplane, claim resourceRef, bounded recursive tracing |
| `tools/validate_xr.go` converts parameter values to strings and infers types | Boolean/integer/string distinctions can be lost | Original JSON/YAML types checked against the installed schema |
| Same validation iterates served schema versions rather than selecting only the requested manifest version | Contracts may differ between versions | Exact manifest API version's schema |
| Same validation applies a static AWS region allowlist to fields containing “region” | Other clouds and new regions can be misclassified | Provider-neutral schema constraints, no invented region list |
| Tree fetch errors are mapped to NotFound readiness | Permission or transport errors may look like absence | Explicit safe error categories, partial-error arrays and unavailable assessments |
| `cmd/server/main.go` hard-codes server version 0.1.0 while Helm artifacts include 0.1.3 | Release components may disagree | CI checks Python, chart, appVersion, changelog and git tag consistency |

Additional workflows in Compass include external-name lookup, adoption/ownership and migration assessments, scaffold → validate → review diff, revision consumer inspection, incident bundles, and explicit cluster/namespace policy. The reference also has capabilities Compass intentionally does not include, such as a reconcile-annotation mutation tool. This is a design tradeoff, not a claim of universal superiority.

## Upstream technical references

- [MCP Python SDK, v1.x](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)
- [Kubernetes Python client](https://github.com/kubernetes-client/python)
- [Crossplane v1.20 concepts](https://docs.crossplane.io/v1.20/concepts/)
- [Crossplane v2.0 composite resources](https://docs.crossplane.io/v2.0/composition/composite-resources/)
- [Kubernetes API concepts: dry-run](https://kubernetes.io/docs/reference/using-api/api-concepts/#dry-run)

Runtime contracts were checked against the installed locked SDK/client source and exercised with protocol tests. See validation.md for the distinction between mock-API integration and a real Kubernetes control plane.
