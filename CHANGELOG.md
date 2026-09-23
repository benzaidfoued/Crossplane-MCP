# Changelog

All notable changes are documented here. Versions follow Semantic Versioning; during 0.x, minor versions may change public contracts with migration notes.

## [0.1.0] - 2026-09-23

### Added
- 24 MCP tools over stdio and authenticated stateless Streamable HTTP.
- CRD/API discovery, exact plural/scope resolution, explicit cluster/group/namespace access policy.
- Crossplane v1/v2 reference tracing, owner UID checks, conditions, events and package health.
- XRD catalog, schema scaffolding, typed local validation, opt-in API-server dry-run and GitOps review diffs.
- External-name matching, adoption and migration assessments, composition revision/consumer inspection.
- Helm chart with read-only RBAC, existing-secret auth, hardened pod defaults and NetworkPolicy.
- Protocol/unit tests, kind CI matrix, package builds, multi-architecture image/OCI chart release, attestations and checksums.
- Installation, architecture, security, contributor and release documentation.

### Known limits
- Initial release requires downstream live-cluster CI validation before publication; see docs/validation.md.
- No persistent mutation, direct cloud identity verification, composition rendering, per-user OAuth or core-resource traversal.
- Redaction does not guarantee removal of secrets in arbitrary strings. Local schema validation is a subset of Kubernetes admission.
