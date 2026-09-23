# Security model and reporting

## Trust boundary

Compass is a bridge from an MCP client to Kubernetes. Anyone who holds its HTTP bearer token can use the permissions of its configured Kubernetes identity within the application allowlists. There is no per-user impersonation, OAuth authorization server, or separate authorization policy for each tool. Use one instance/service account per trust boundary; terminate remote traffic with TLS.

The stdio transport inherits trust from the local client process and kubeconfig. Kubeconfig exec authentication plugins can execute local programs. Load trusted kubeconfigs only.

## Defaults

- No persistent Kubernetes mutation tools, shell execution, function execution or cloud calls.
- Read-only Helm RBAC for explicit custom API groups, CRDs and events. No Secret, pod log, exec or cluster-wide wildcard API-group access.
- HTTP refuses startup without a token file of at least 32 characters. Use cryptographically random tokens; length alone is not entropy.
- HTTP bearer verification uses constant-time comparison; unreadable/short tokens fail closed. Mounted token rotation is supported.
- Host checking is enabled; body, result, pagination, graph and concurrency bounds reduce accidental overload.
- Pod runs as non-root, without extra capabilities, with read-only root filesystem and RuntimeDefault seccomp.
- Tool audit logs contain operation name, status and duration. They omit arguments and upstream response bodies.

## Data exposure

Kubernetes object specs, provider errors, event messages, labels and schema descriptions can contain sensitive information or malicious instructions. All such content is **untrusted data**. The MCP host must not execute instructions embedded in it.

Key-based redaction covers common password/token/secret/credential/private-key fields. Managed fields and most annotations are removed; external-name and pause annotations are intentionally retained. Free-form strings, custom keys, external IDs and condition messages may still disclose information. Redaction is defense in depth, not a DLP guarantee. Use summary tools by default and review exports before sharing. Secrets must not be embedded in XR fields in the first place.

API group allowlists do not replace Kubernetes RBAC. Application namespace restrictions do not reduce a ClusterRoleBinding's native access. Configure dedicated Roles/RoleBindings for tenant isolation. CRD schemas expose API definitions cluster-wide even when object namespaces are restricted.

## Dry-run exception

Optional server-side validation requires patch authorization on specified custom resources. The server always sends dryRun=All, but Kubernetes RBAC cannot distinguish dry-run from persistent PATCH. A compromised process using that service account could issue a real write. Keep disabled unless this tradeoff is accepted; grant only specific group/resources.

## Dependency and release integrity

`uv.lock` records the dependency set. CI runs pip-audit, lint, tests, chart checks and kind smoke tests. Releases are gated on CI, publish multi-architecture OCI images with SBOM/provenance, attest distributables, and attach SHA256SUMS. Python/Helm/application versions must agree with the pushed tag.

Container base images and GitHub Actions use maintained version tags rather than immutable source hashes in this initial release. For stricter supply-chain policy, pin reviewed digests/SHAs and maintain them with Dependabot. The released Helm chart itself references the image digest emitted by its build.

## Reporting

Do not post credentials or exploitable details in a public issue. Once this repository is published, use GitHub **Security → Report a vulnerability** (maintainers must enable private vulnerability reporting before launch). If it is not enabled, ask the maintainer for a private channel without disclosing the vulnerability publicly. No response SLA is promised for this new community project.

Only the latest release is actively supported initially. Security fixes should be prioritized and announced with clear affected versions and upgrade guidance.
