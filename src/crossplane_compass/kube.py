"""Bounded Kubernetes REST adapter using official kubeconfig/SA authentication.

Only CRD-backed, explicitly allowed API groups are addressable. Plurals and
scope come from CRDs; served versions are checked against API discovery.
"""

import os
import threading
import time
from dataclasses import dataclass
from typing import Any

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from urllib3.exceptions import HTTPError

from .safety import CompassError, api_parts, segment

BASE_GROUPS = {
    "apiextensions.crossplane.io",
    "pkg.crossplane.io",
    "ops.crossplane.io",
    "protection.crossplane.io",
}


@dataclass(frozen=True)
class Resource:
    api_version: str
    kind: str
    plural: str
    namespaced: bool
    schema: dict
    categories: tuple[str, ...] = ()


class Kubernetes:
    def __init__(
        self,
        context: str | None = None,
        *,
        groups: set[str] | None = None,
        namespaces: set[str] | None = None,
        allow_cluster: bool = True,
        dry_run: bool = False,
        api: Any = None,
        ttl: int = 60,
    ):
        self.groups = BASE_GROUPS | (groups or set())
        self.namespaces = namespaces or set()
        self.allow_cluster = allow_cluster
        self.dry_run_enabled = dry_run
        self.context = context or "in-cluster"
        self.ttl = ttl
        self._lock = threading.RLock()
        self._expires = 0.0
        self._resources: dict[tuple[str, str], Resource] = {}
        self._discovery: dict[str, dict] = {}
        if api is not None:
            self.api = api
        else:
            cfg = client.Configuration()
            if context is not None or not os.getenv("KUBERNETES_SERVICE_HOST"):
                config.load_kube_config(context=context, client_configuration=cfg)
            else:
                config.load_incluster_config(client_configuration=cfg)
            cfg.retries = 0
            self.api = client.ApiClient(cfg)

    def request(self, path: str, *, query: dict | None = None, body: dict | None = None) -> dict:
        method = "GET" if body is None else "PATCH"
        if body is not None and (not self.dry_run_enabled or (query or {}).get("dryRun") != "All"):
            raise CompassError("Only explicitly enabled server-side dry-run writes are supported")
        try:
            return self.api.call_api(
                path,
                method,
                query_params=list((query or {}).items()),
                header_params={
                    "Accept": "application/json",
                    "Content-Type": "application/apply-patch+yaml",
                },
                body=body,
                auth_settings=["BearerToken"],
                response_types_map={200: "object", 201: "object"},
                _return_http_data_only=True,
                _request_timeout=(5, 20),
            )
        except ApiException as e:
            meaning = {
                403: "RBAC denied",
                404: "Resource not found",
                409: "Field ownership conflict",
                410: "Pagination expired; restart listing",
                422: "API validation rejected",
                429: "API throttled; retry later",
            }.get(e.status, "Kubernetes API request failed")
            raise CompassError(f"{meaning} (HTTP {e.status})") from None
        except (HTTPError, OSError):
            raise CompassError("Kubernetes connection failed or timed out") from None

    def refresh(self) -> list[Resource]:
        with self._lock:
            if time.monotonic() < self._expires:
                return list(self._resources.values())
            resources = {}
            token = ""
            for _ in range(50):
                result = self.request(
                    "/apis/apiextensions.k8s.io/v1/customresourcedefinitions",
                    query={"limit": 200, "continue": token},
                )
                for crd in result.get("items", []):
                    s = crd["spec"]
                    if s["group"] not in self.groups:
                        continue
                    for v in s["versions"]:
                        if v.get("served"):
                            r = Resource(
                                f"{s['group']}/{v['name']}",
                                s["names"]["kind"],
                                s["names"]["plural"],
                                s["scope"] == "Namespaced",
                                v.get("schema", {}).get("openAPIV3Schema", {}),
                                tuple(s["names"].get("categories", [])),
                            )
                            resources[(r.api_version, r.kind)] = r
                token = result.get("metadata", {}).get("continue", "")
                if not token:
                    break
            else:
                raise CompassError("CRD discovery exceeded 10,000 definitions")
            self._resources = resources
            self._discovery = {}
            self._expires = time.monotonic() + self.ttl
            return list(resources.values())

    def resolve(self, api_version: str, kind: str) -> Resource:
        group, version = api_parts(api_version)
        segment(kind)
        if group not in self.groups:
            raise CompassError("API group is not in the server allowlist")
        self.refresh()
        with self._lock:
            r = self._resources.get((api_version, kind))
            if r is None:
                raise CompassError("Kind/version is not a served CRD in this cluster")
            if api_version not in self._discovery:
                self._discovery[api_version] = self.request(f"/apis/{group}/{version}")
            found = next(
                (
                    x
                    for x in self._discovery[api_version].get("resources", [])
                    if x["name"] == r.plural and x["kind"] == r.kind
                ),
                None,
            )
            if found is None or found.get("namespaced", False) != r.namespaced:
                raise CompassError(
                    "CRD and API discovery disagree; retry after discovery cache expires"
                )
            return r

    def path(self, r: Resource, namespace: str = "", name: str = "") -> str:
        group, version = api_parts(r.api_version)
        path = f"/apis/{group}/{version}"
        if r.namespaced:
            if namespace:
                segment(namespace)
                if self.namespaces and namespace not in self.namespaces:
                    raise CompassError("Namespace is not in the server allowlist")
                path += f"/namespaces/{namespace}"
            elif name or self.namespaces:
                raise CompassError("An explicitly allowed namespace is required")
        elif namespace:
            raise CompassError("Cluster-scoped resource must not specify a namespace")
        elif not self.allow_cluster:
            raise CompassError("Cluster-scoped resource access is disabled")
        path += "/" + segment(r.plural)
        return path + ("/" + segment(name) if name else "")

    def get(self, api_version: str, kind: str, name: str, namespace: str = "") -> dict:
        return self.request(self.path(self.resolve(api_version, kind), namespace, name))

    def list(
        self,
        api_version: str,
        kind: str,
        namespace: str = "",
        limit: int = 100,
        continue_token: str = "",
        label_selector: str = "",
    ) -> dict:
        if not 1 <= limit <= 200 or len(continue_token) > 8192 or len(label_selector) > 1024:
            raise CompassError("Invalid pagination or selector limits")
        r = self.resolve(api_version, kind)
        return self.request(
            self.path(r, namespace),
            query={"limit": limit, "continue": continue_token, "labelSelector": label_selector},
        )

    def events(self, obj: dict, limit: int = 100) -> dict:
        r = self.resolve(obj["apiVersion"], obj["kind"])
        ns = obj.get("metadata", {}).get("namespace", "")
        self.path(r, ns, obj["metadata"]["name"])
        if not ns and self.namespaces:
            raise CompassError("All-namespace event access is disabled by namespace policy")
        uid = segment(obj["metadata"]["uid"])
        path = f"/api/v1/namespaces/{segment(ns)}/events" if ns else "/api/v1/events"
        return self.request(
            path, query={"fieldSelector": f"involvedObject.uid={uid}", "limit": limit}
        )

    def dry_run(self, manifest: dict) -> dict:
        r = self.resolve(manifest["apiVersion"], manifest["kind"])
        m = manifest["metadata"]
        return self.request(
            self.path(r, m.get("namespace", ""), m["name"]),
            query={
                "dryRun": "All",
                "fieldManager": "crossplane-compass",
                "force": "false",
                "fieldValidation": "Strict",
            },
            body=manifest,
        )
