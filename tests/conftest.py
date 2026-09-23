import copy

import pytest
from kubernetes.client.exceptions import ApiException

from crossplane_compass.kube import Kubernetes
from crossplane_compass.service import Compass

GROUP = "platform.example.org"
SCHEMA = {
    "type": "object",
    "required": ["apiVersion", "kind", "metadata", "spec"],
    "properties": {
        "apiVersion": {"type": "string"},
        "kind": {"type": "string"},
        "metadata": {"type": "object"},
        "spec": {
            "type": "object",
            "required": ["size"],
            "properties": {
                "size": {"type": "integer", "minimum": 1},
                "region": {"type": "string", "enum": ["canadacentral"]},
                "enabled": {"type": "boolean"},
            },
        },
    },
}


def crd(kind, plural, scope="Namespaced", group=GROUP, version="v1"):
    return {
        "metadata": {"name": f"{plural}.{group}"},
        "spec": {
            "group": group,
            "scope": scope,
            "names": {"kind": kind, "plural": plural, "categories": ["crossplane"]},
            "versions": [
                {
                    "name": version,
                    "served": True,
                    "storage": True,
                    "schema": {"openAPIV3Schema": copy.deepcopy(SCHEMA)},
                }
            ],
        },
    }


def obj(kind="Database", name="db", namespace="team-a", **extra):
    result = {
        "apiVersion": f"{GROUP}/v1",
        "kind": kind,
        "metadata": {"name": name, "uid": name + "-uid", "generation": 2, "resourceVersion": "42"},
        "spec": {"size": 2},
        "status": {"conditions": [{"type": "Ready", "status": "True", "observedGeneration": 2}]},
    }
    if namespace:
        result["metadata"]["namespace"] = namespace
    result.update(extra)
    return result


class FakeAPI:
    def __init__(self):
        self.crds = [
            crd("Database", "databases"),
            crd("Policy", "policies", "Cluster"),
            crd("ProviderConfig", "providerconfigs"),
            crd("Composition", "compositions", "Cluster", "apiextensions.crossplane.io"),
            crd(
                "CompositionRevision",
                "compositionrevisions",
                "Cluster",
                "apiextensions.crossplane.io",
            ),
            crd(
                "CompositeResourceDefinition",
                "compositeresourcedefinitions",
                "Cluster",
                "apiextensions.crossplane.io",
                "v2",
            ),
            crd("Provider", "providers", "Cluster", "pkg.crossplane.io"),
        ]
        self.objects = {}
        self.calls = []
        self.denied = set()
        self.continue_token = ""
        self.put(obj())
        self.put(obj("Policy", "policy", ""))

    def put(self, value):
        s = next(c["spec"] for c in self.crds if c["spec"]["names"]["kind"] == value["kind"])
        path = f"/apis/{value['apiVersion']}"
        if s["scope"] == "Namespaced":
            path += "/namespaces/" + value["metadata"]["namespace"]
        path += "/" + s["names"]["plural"] + "/" + value["metadata"]["name"]
        self.objects[path] = value
        return value

    def call_api(self, path, method, **kw):
        self.calls.append((path, method, kw))
        if path in self.denied:
            raise ApiException(status=403, reason="private token=DO_NOT_LEAK")
        if path == "/version":
            return {"gitVersion": "v1.33.0"}
        if path.endswith("/customresourcedefinitions"):
            return {"items": copy.deepcopy(self.crds)}
        parts = path.split("/")
        if len(parts) == 4 and path.startswith("/apis/"):
            return {
                "resources": [
                    {
                        "name": c["spec"]["names"]["plural"],
                        "kind": c["spec"]["names"]["kind"],
                        "namespaced": c["spec"]["scope"] == "Namespaced",
                    }
                    for c in self.crds
                    if c["spec"]["group"] == parts[2]
                ]
            }
        if path.endswith("/events"):
            return {"items": [{"reason": "ReconcileError", "message": "dependency not ready"}]}
        if method == "PATCH":
            assert dict(kw["query_params"])["dryRun"] == "All"
            return copy.deepcopy(kw["body"])
        if path in self.objects:
            return copy.deepcopy(self.objects[path])
        if parts[-1] in {c["spec"]["names"]["plural"] for c in self.crds}:
            items = [
                copy.deepcopy(v) for p, v in self.objects.items() if p.rsplit("/", 1)[0] == path
            ]
            return {"items": items, "metadata": {"continue": self.continue_token}}
        raise ApiException(status=404)


@pytest.fixture
def api():
    return FakeAPI()


@pytest.fixture
def kube(api):
    return Kubernetes(api=api, groups={GROUP}, namespaces={"team-a"})


@pytest.fixture
def compass(kube):
    return Compass({"test": kube})
