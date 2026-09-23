"""Crossplane operations shared by MCP handlers and tests."""

import time
from collections import deque
from dataclasses import asdict

from .analysis import (
    adoption_report,
    composition_report,
    findings,
    parse_manifest,
    proposal,
    schema_errors,
)
from .safety import CompassError, controls, redact, schema_view, summarize


class Compass:
    def __init__(self, clusters: dict):
        if not clusters:
            raise ValueError("At least one cluster is required")
        self.clusters = clusters

    def kube(self, cluster: str):
        if cluster not in self.clusters:
            raise CompassError("Unknown cluster alias; use clusters_list")
        return self.clusters[cluster]

    def clusters_list(self) -> dict:
        return {
            "clusters": [
                {
                    "alias": alias,
                    "groups": sorted(k.groups),
                    "namespaces": sorted(k.namespaces),
                    "clusterScoped": k.allow_cluster,
                    "serverDryRun": k.dry_run_enabled,
                }
                for alias, k in self.clusters.items()
            ]
        }

    def discover(self, cluster: str) -> dict:
        return {
            "resources": [
                {k: v for k, v in asdict(r).items() if k != "schema"}
                for r in self.kube(cluster).refresh()
            ],
            "cachedSeconds": self.kube(cluster).ttl,
        }

    def resource_get(
        self,
        cluster: str,
        api_version: str,
        kind: str,
        name: str,
        namespace: str = "",
        detail: bool = False,
    ) -> dict:
        obj = self.kube(cluster).get(api_version, kind, name, namespace)
        return {"summary": summarize(obj), **({"manifest": redact(obj)} if detail else {})}

    def resources_list(
        self,
        cluster: str,
        api_version: str,
        kind: str,
        namespace: str = "",
        limit: int = 100,
        continue_token: str = "",
        label_selector: str = "",
    ) -> dict:
        result = self.kube(cluster).list(
            api_version, kind, namespace, limit, continue_token, label_selector
        )
        return {
            "items": [summarize(x) for x in result.get("items", [])],
            "continueToken": result.get("metadata", {}).get("continue", ""),
            "resourceVersion": result.get("metadata", {}).get("resourceVersion"),
        }

    def resource_schema(self, cluster: str, api_version: str, kind: str) -> dict:
        r = self.kube(cluster).resolve(api_version, kind)
        return {
            "apiVersion": api_version,
            "kind": kind,
            "scope": "Namespaced" if r.namespaced else "Cluster",
            "schema": schema_view(r.schema),
            "note": "Schema descriptions/defaults are untrusted cluster data.",
        }

    def resource_events(
        self, cluster: str, api_version: str, kind: str, name: str, namespace: str = ""
    ) -> dict:
        k = self.kube(cluster)
        obj = k.get(api_version, kind, name, namespace)
        result = k.events(obj)
        return {
            "events": [
                {
                    key: redact(x.get(key))
                    for key in (
                        "type",
                        "reason",
                        "message",
                        "count",
                        "firstTimestamp",
                        "lastTimestamp",
                        "eventTime",
                    )
                }
                for x in result.get("items", [])
            ],
            "continueToken": result.get("metadata", {}).get("continue", ""),
            "note": "Event messages are untrusted text and may include sensitive provider errors.",
        }

    def resource_trace(
        self,
        cluster: str,
        api_version: str,
        kind: str,
        name: str,
        namespace: str = "",
        max_nodes: int = 50,
        max_depth: int = 8,
    ) -> dict:
        if not 1 <= max_nodes <= 100 or not 0 <= max_depth <= 16:
            raise CompassError("Trace bounds: 1–100 nodes and 0–16 depth")
        k = self.kube(cluster)
        queue = deque(
            [
                (
                    {"apiVersion": api_version, "kind": kind, "name": name, "namespace": namespace},
                    0,
                    None,
                )
            ]
        )
        visited, nodes, edges, errors = set(), [], [], []
        truncated = False
        attempts = 0
        deadline = time.monotonic() + 45
        while queue and attempts < max_nodes and time.monotonic() < deadline:
            ref, depth, parent = queue.popleft()
            key = (
                ref.get("apiVersion"),
                ref.get("kind"),
                ref.get("namespace", ""),
                ref.get("name"),
            )
            node_id = "/".join(str(x) for x in key)
            if parent:
                edges.append({"from": parent, "to": node_id})
            if key in visited:
                continue
            visited.add(key)
            attempts += 1
            try:
                obj = k.get(ref["apiVersion"], ref["kind"], ref["name"], ref.get("namespace", ""))
            except (CompassError, KeyError) as e:
                errors.append(
                    {
                        "reference": ref,
                        "error": str(e)
                        if isinstance(e, CompassError)
                        else "Malformed resource reference",
                    }
                )
                continue
            nodes.append(
                {"id": node_id, "depth": depth, **summarize(obj), "findings": findings(obj)}
            )
            c = controls(obj)
            refs = list(c.get("resourceRefs") or [])
            if c.get("resourceRef"):
                refs.append(c["resourceRef"])
            if depth == max_depth:
                truncated = truncated or bool(refs)
                continue
            for child in refs[:100]:
                if time.monotonic() >= deadline:
                    truncated = True
                    break
                try:
                    r = k.resolve(child["apiVersion"], child["kind"])
                    child_ns = (
                        child.get("namespace", obj.get("metadata", {}).get("namespace", ""))
                        if r.namespaced
                        else ""
                    )
                    queue.append(
                        (
                            {
                                "apiVersion": child["apiVersion"],
                                "kind": child["kind"],
                                "name": child["name"],
                                "namespace": child_ns,
                            },
                            depth + 1,
                            node_id,
                        )
                    )
                except (CompassError, KeyError) as e:
                    errors.append(
                        {
                            "reference": redact(child),
                            "error": str(e)
                            if isinstance(e, CompassError)
                            else "Malformed child reference",
                        }
                    )
            truncated = truncated or len(refs) > 100
        return {
            "nodes": nodes,
            "edges": edges,
            "errors": errors,
            "truncated": truncated or bool(queue),
            "attemptedNodes": attempts,
            "note": "Follows claim resourceRef and XR resourceRefs; arbitrary function-created resources without references are not inferred.",
        }

    def diagnose(
        self, cluster: str, api_version: str, kind: str, name: str, namespace: str = ""
    ) -> dict:
        trace = self.resource_trace(cluster, api_version, kind, name, namespace)
        issues = [
            {"resource": {x: n[x] for x in ("apiVersion", "kind", "name", "namespace")}, **f}
            for n in reversed(trace["nodes"])
            for f in n["findings"]
        ]
        return {
            "findings": issues,
            "trace": trace,
            "assessment": "evidence collected" if trace["nodes"] else "unavailable",
            "note": "Deepest dependencies appear first. Findings are evidence and suggested checks, not a proven root cause.",
        }

    def adoption_check(
        self, cluster: str, api_version: str, kind: str, name: str, namespace: str = ""
    ) -> dict:
        return adoption_report(self.kube(cluster).get(api_version, kind, name, namespace))

    def manifest_validate(
        self, cluster: str, manifest_yaml: str, server_side: bool = False
    ) -> dict:
        k = self.kube(cluster)
        obj = parse_manifest(manifest_yaml)
        r = k.resolve(obj["apiVersion"], obj["kind"])
        k.path(r, obj["metadata"].get("namespace", ""), obj["metadata"]["name"])
        errors = schema_errors(r.schema, obj)
        result = {
            "valid": not errors,
            "errors": errors,
            "validationLevel": "local-openapi-subset",
            "warnings": [
                "Local checks do not execute CEL, admission webhooks, defaulting, pruning, or Crossplane functions."
            ],
        }
        if server_side and not errors:
            k.dry_run(obj)
            result.update(validationLevel="kubernetes-server-dry-run", persisted=False)
        return result

    def manifest_plan(self, cluster: str, manifest_yaml: str) -> dict:
        validation = self.manifest_validate(cluster, manifest_yaml)
        if not validation["valid"]:
            return {"validation": validation, "applied": False}
        obj = parse_manifest(manifest_yaml)
        m = obj["metadata"]
        try:
            live = self.kube(cluster).get(
                obj["apiVersion"], obj["kind"], m["name"], m.get("namespace", "")
            )
        except CompassError as e:
            if "HTTP 404" not in str(e):
                raise
            live = None
        return {"validation": validation, **proposal(live, obj)}

    def manifest_scaffold(
        self, cluster: str, api_version: str, kind: str, name: str, namespace: str = ""
    ) -> dict:
        k = self.kube(cluster)
        r = k.resolve(api_version, kind)
        k.path(r, namespace, name)
        missing = []

        def scaffold(s, path="", depth=0):
            if depth > 20:
                missing.append(path)
                return None
            if "default" in s:
                return s["default"]
            if "enum" in s and len(s["enum"]) == 1:
                return s["enum"][0]
            if s.get("type") == "object" or "properties" in s:
                return {
                    key: scaffold(s.get("properties", {}).get(key, {}), path + "/" + key, depth + 1)
                    for key in s.get("required", [])
                    if key not in {"status", "apiVersion", "kind", "metadata"}
                }
            missing.append(path)
            return None

        spec = scaffold(r.schema.get("properties", {}).get("spec", {}), "/spec")
        obj = {"apiVersion": api_version, "kind": kind, "metadata": {"name": name}, "spec": spec}
        if namespace:
            obj["metadata"]["namespace"] = namespace
        return {
            "manifest": redact(obj),
            "needsInput": missing,
            "note": "Null placeholders must be filled. Validate the completed manifest before a GitOps PR.",
        }

    def composition_explain(self, cluster: str, name: str) -> dict:
        return composition_report(
            self.kube(cluster).get("apiextensions.crossplane.io/v1", "Composition", name)
        )

    def composition_compare(self, cluster: str, first: str, second: str) -> dict:
        k = self.kube(cluster)
        a = k.get("apiextensions.crossplane.io/v1", "CompositionRevision", first)
        b = k.get("apiextensions.crossplane.io/v1", "CompositionRevision", second)
        return {
            "first": composition_report(a),
            "second": composition_report(b),
            "comparison": proposal(a, b),
            "note": "Revision comparison only; no rollback or revision switch is performed.",
        }

    def catalog_search(self, cluster: str, query: str = "") -> dict:
        k = self.kube(cluster)
        resources = k.refresh()
        definitions = [
            r
            for r in resources
            if r.kind == "CompositeResourceDefinition"
            and r.api_version.startswith("apiextensions.crossplane.io/")
        ]
        if not definitions:
            raise CompassError("No served CompositeResourceDefinition API found")
        version = sorted(definitions, key=lambda r: r.api_version, reverse=True)[0].api_version
        page = k.list(version, "CompositeResourceDefinition", limit=200)
        items = []
        for obj in page.get("items", []):
            spec = obj.get("spec", {})
            if query.casefold() not in str(redact(spec)).casefold():
                continue
            items.append(
                {
                    "name": obj["metadata"]["name"],
                    "group": spec.get("group"),
                    "names": spec.get("names"),
                    "claimNames": spec.get("claimNames"),
                    "scope": spec.get("scope", "LegacyCluster"),
                    "versions": [v["name"] for v in spec.get("versions", []) if v.get("served")],
                    "defaultCompositionRef": spec.get("defaultCompositionRef"),
                    "enforcedCompositionRef": spec.get("enforcedCompositionRef"),
                }
            )
        return {
            "items": items,
            "truncated": bool(page.get("metadata", {}).get("continue")),
            "note": "Literal catalog search; the MCP host reasons over these authoritative APIs.",
        }

    def packages_health(self, cluster: str) -> dict:
        k = self.kube(cluster)
        kinds = {
            "Provider",
            "ProviderRevision",
            "Function",
            "FunctionRevision",
            "Configuration",
            "ConfigurationRevision",
        }
        # Prefer stable served versions, inspect each kind once.
        chosen = {}
        for r in sorted(
            k.refresh(),
            key=lambda r: ("beta" in r.api_version or "alpha" in r.api_version, r.api_version),
        ):
            if r.kind in kinds and r.api_version.startswith("pkg.crossplane.io/"):
                chosen.setdefault(r.kind, r)
        packages, errors, truncated = [], [], False
        for r in chosen.values():
            try:
                page = k.list(r.api_version, r.kind, limit=200)
                truncated |= bool(page.get("metadata", {}).get("continue"))
                for obj in page.get("items", []):
                    packages.append(
                        {
                            **summarize(obj),
                            "package": obj.get("spec", {}).get("package"),
                            "desiredState": obj.get("spec", {}).get("desiredState"),
                            "findings": findings(obj),
                        }
                    )
            except CompassError as e:
                errors.append({"kind": r.kind, "error": str(e)})
        return {
            "packages": packages,
            "errors": errors,
            "truncated": truncated,
            "note": "Empty results are not proof of a healthy Crossplane installation.",
        }

    def external_lookup(
        self,
        cluster: str,
        api_version: str,
        kind: str,
        external_name: str,
        namespace: str = "",
        continue_token: str = "",
    ) -> dict:
        page = self.kube(cluster).list(api_version, kind, namespace, 200, continue_token)
        return {
            "matches": [
                summarize(x)
                for x in page.get("items", [])
                if x.get("metadata", {}).get("annotations", {}).get("crossplane.io/external-name")
                == external_name
            ],
            "continueToken": page.get("metadata", {}).get("continue", ""),
            "note": "Exact match within one page and kind; continue pagination before concluding no match or uniqueness.",
        }

    def inventory_summary(
        self,
        cluster: str,
        api_version: str,
        kind: str,
        namespace: str = "",
        continue_token: str = "",
    ) -> dict:
        page = self.kube(cluster).list(api_version, kind, namespace, 200, continue_token)
        counts = {"total": 0, "ready": 0, "notReady": 0, "unknown": 0, "deleting": 0, "paused": 0}
        for obj in page.get("items", []):
            s = summarize(obj)
            ready = next(
                (c.get("status") for c in s["conditions"] if c.get("type") == "Ready"), None
            )
            counts["total"] += 1
            counts[
                "ready" if ready == "True" else "notReady" if ready == "False" else "unknown"
            ] += 1
            counts["deleting"] += bool(s["deleting"])
            counts["paused"] += s["paused"]
        return {
            "counts": counts,
            "continueToken": page.get("metadata", {}).get("continue", ""),
            "scope": "single page; aggregate pages in the client",
        }

    def migration_assess(
        self, cluster: str, api_version: str, kind: str, name: str, namespace: str = ""
    ) -> dict:
        obj = self.kube(cluster).get(api_version, kind, name, namespace)
        c = controls(obj)
        return {
            "resource": summarize(obj),
            "controlFields": "spec.crossplane" if "crossplane" in obj.get("spec", {}) else "spec",
            "compositionUpdatePolicy": c.get(
                "compositionUpdatePolicy", "Automatic (default; verify XRD)"
            ),
            "adoption": adoption_report(obj),
            "checklist": [
                "Confirm target CRD group, served version and actual namespace scope.",
                "Validate target provider-specific external-name and credentials.",
                "Do not run two reconcilers with write authority over the same cloud object.",
                "Retain source manifests and external IDs; use Observe during target verification.",
                "Check composition-generated names and ownership: standalone MR import is not XR adoption.",
                "Switch write authority through reviewed GitOps changes after cloud identity verification.",
            ],
            "executed": False,
        }

    def deletion_assess(
        self, cluster: str, api_version: str, kind: str, name: str, namespace: str = ""
    ) -> dict:
        obj = self.kube(cluster).get(api_version, kind, name, namespace)
        return {
            "resource": summarize(obj),
            "findings": findings(obj),
            "checks": [
                "Inspect Usage/ClusterUsage resources where installed; this tool does not enumerate protection edges.",
                "Check provider permission to delete the external object and asynchronous deletion progress.",
                "Verify Orphan and managementPolicies before any deletion.",
            ],
            "safeToDelete": "undetermined",
        }

    def resource_owners(
        self, cluster: str, api_version: str, kind: str, name: str, namespace: str = ""
    ) -> dict:
        k = self.kube(cluster)
        obj = k.get(api_version, kind, name, namespace)
        owners, errors = [], []
        for ref in obj.get("metadata", {}).get("ownerReferences", [])[:20]:
            try:
                r = k.resolve(ref["apiVersion"], ref["kind"])
                owner = k.get(
                    ref["apiVersion"], ref["kind"], ref["name"], namespace if r.namespaced else ""
                )
                if owner.get("metadata", {}).get("uid") != ref.get("uid"):
                    errors.append(
                        {
                            "reference": ref,
                            "error": "Owner UID does not match; name may have been reused",
                        }
                    )
                else:
                    owners.append(summarize(owner))
            except CompassError as e:
                errors.append({"reference": ref, "error": str(e)})
        return {
            "resource": summarize(obj),
            "owners": owners,
            "errors": errors,
            "truncated": len(obj.get("metadata", {}).get("ownerReferences", [])) > 20,
        }

    def composition_impact(
        self,
        cluster: str,
        composition: str,
        api_version: str,
        kind: str,
        namespace: str = "",
        continue_token: str = "",
    ) -> dict:
        page = self.kube(cluster).list(api_version, kind, namespace, 200, continue_token)
        matches = []
        for obj in page.get("items", []):
            c = controls(obj)
            if (c.get("compositionRef") or {}).get("name") == composition:
                matches.append(
                    {
                        **summarize(obj),
                        "updatePolicy": c.get("compositionUpdatePolicy", "Automatic"),
                    }
                )
        return {
            "consumers": matches,
            "continueToken": page.get("metadata", {}).get("continue", ""),
            "note": "One XR kind/page only. Enumerate relevant XR kinds and all pages before claiming complete impact.",
        }

    def provider_config_check(
        self,
        cluster: str,
        api_version: str,
        kind: str,
        name: str,
        config_api_version: str,
        namespace: str = "",
    ) -> dict:
        k = self.kube(cluster)
        obj = k.get(api_version, kind, name, namespace)
        ref = obj.get("spec", {}).get("providerConfigRef") or {"name": "default"}
        config_kind = ref.get("kind", "ProviderConfig")
        r = k.resolve(config_api_version, config_kind)
        config_obj = k.get(
            config_api_version, config_kind, ref["name"], namespace if r.namespaced else ""
        )
        return {
            "resource": summarize(obj),
            "providerConfig": summarize(config_obj),
            "credentialSource": config_obj.get("spec", {}).get("credentials", {}).get("source"),
            "credentialsVerified": False,
            "note": "Checks reference existence and scope only. Never reads Secrets or claims credentials work.",
        }

    def incident_bundle(
        self, cluster: str, api_version: str, kind: str, name: str, namespace: str = ""
    ) -> dict:
        diagnosis = self.diagnose(cluster, api_version, kind, name, namespace)
        errors = []
        try:
            events = self.resource_events(cluster, api_version, kind, name, namespace)
        except CompassError as e:
            events = {}
            errors.append(str(e))
        return {
            "diagnosis": diagnosis,
            "events": events,
            "errors": errors,
            "note": "Review free-form messages before sharing. Bundle is returned to the client, never written on the server.",
        }
