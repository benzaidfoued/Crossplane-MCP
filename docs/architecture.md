# Architecture and operational semantics

## Components

| Module | Responsibility |
|---|---|
| `server.py` | Official MCP Python SDK, typed tool registration, stdio/HTTP, auth middleware, metrics, concurrency |
| `kube.py` | Official Kubernetes client authentication, safe paths, CRD/API discovery, pagination and dry-run guard |
| `service.py` | Crossplane catalog, resource graph, inspection and GitOps workflows |
| `analysis.py` | Pure schema checks, findings, import checks, composition inspection and diffs |
| `safety.py` | Identifier validation, output minimization and v1/v2 control-field handling |

## Discovery and compatibility

Compass lists CRDs, retains only explicitly allowed API groups, indexes each served version by `(apiVersion, kind)`, and checks the corresponding `/apis/GROUP/VERSION` resource discovery. Namespaces and plurals come from the actual CRD. Discovery is cached for 60 seconds per cluster. A failed discovery does not replace a previously complete cache with a partial success.

Legacy claims use `spec.resourceRef`; v1/LegacyCluster XRs use `spec.resourceRefs`. v2 namespaced XRs use `spec.crossplane.resourceRefs`. Each child is resolved independently. A cluster-scoped MR below a namespaced XR is fetched without a namespace. Namespaced children inherit the parent namespace unless their reference explicitly supplies one. Owner lookups verify UID to avoid confusing a recreated object with its predecessor.

The compatibility target is Crossplane 1.20 and 2.0 API shapes. The CI matrix installs those versions. Later versions and provider releases use dynamic discovery but are not automatically certified. Earlier 1.x installations may work; they are not in the initial CI matrix. ManagedResourceDefinitions do not need special handling after their CRDs become established; inactive/unestablished definitions cannot be inspected as live resource kinds.

## Bounds and efficiency

- One shared Kubernetes client and discovery cache per configured cluster; no cloud calls.
- Eight concurrent tool workers. Blocking Kubernetes I/O runs off the asynchronous MCP event loop.
- Kubernetes connect/read timeouts: 5/20 seconds per request; no unbounded application retry loop.
- CRD discovery: 200/page, maximum 50 pages. Normal resource lists: at most 200/page.
- Resource trace: default 50 nodes / 8 levels; maxima 100 / 16; at most 100 outgoing references per node. A 45-second traversal budget is checked between API operations; in-flight requests may finish after that budget.
- YAML input: 256 KiB; HTTP body: 300,000 bytes; JSON-serialized tool output: 512 KiB.
- Schema/manifest nesting and YAML aliases are restricted. Local schema validation refuses `$ref` rather than fetching remote resources.

Budgets apply to the exposed results and traversal. A large Kubernetes response still must be decoded before output-size enforcement. Cluster CRDs and object schemas are trusted to remain within ordinary API-server limits. This release does not stream unbounded inventories or retain snapshots on disk.

## No hidden mutation

`Kubernetes.request` permits GET, or PATCH only when dry-run is enabled and the query includes `dryRun=All`. There is no general arbitrary-path MCP tool. Tool methods never execute kubectl, Helm or shell commands. GitOps plans are returned, not committed, pushed or applied. Chart and development scripts use CLI tools outside the server runtime.

Local plans compare normalized desired and live manifests; this can include API defaults and controller-managed spec fields. It is not a three-way server-side-apply preview. Redacted fields and most annotations are excluded, so review the original manifest separately. `crossplane.io/external-name` and `crossplane.io/paused` remain visible because they are operationally critical.

## Evidence rather than certainty

Ready=False, Synced=False, stale observed generation, pause state and finalizers are directly observable. Recommendations derived from them are hypotheses. Empty package lists do not prove health. Missing events may be retention or RBAC. An external-name match is not cloud identity verification. ProviderConfig existence does not validate its credentials. Revision comparison does not execute composition functions. Deletion safety remains undetermined.

## HTTP deployment

Stateless Streamable HTTP allows replicas without shared session storage. Bearer authentication protects `/mcp` and `/metrics`. `/healthz` checks the process; `/readyz` checks Kubernetes API reachability for configured clusters, not provider readiness or every permission. Token files are re-read for rotation. Host validation remains enabled. Browser Origins are not allowlisted; remote browser use requires a separately reviewed gateway setup.

Metrics expose per-tool success/error counts and accumulated duration. JSON audit records contain tool name, status and duration, never arguments or manifests. Kubernetes API-server audit logs remain the authoritative record of resource access. The shared bearer token does not give per-person attribution.
