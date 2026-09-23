"""Disposable kind-only test. Installs one XRD/XR; never uses cloud credentials."""

import argparse
import subprocess
import time

import yaml

from crossplane_compass.kube import Kubernetes
from crossplane_compass.service import Compass

p = argparse.ArgumentParser()
p.add_argument("--crossplane", required=True)
a = p.parse_args()
v2 = a.crossplane.startswith("2.")
xrd = {
    "apiVersion": "apiextensions.crossplane.io/v2" if v2 else "apiextensions.crossplane.io/v1",
    "kind": "CompositeResourceDefinition",
    "metadata": {"name": "widgets.compass.example.org"},
    "spec": {
        "group": "compass.example.org",
        "names": {"kind": "Widget", "plural": "widgets"},
        "versions": [
            {
                "name": "v1alpha1",
                "served": True,
                "referenceable": True,
                "schema": {
                    "openAPIV3Schema": {
                        "type": "object",
                        "properties": {
                            "spec": {
                                "type": "object",
                                "properties": {"size": {"type": "integer", "minimum": 1}},
                                "required": ["size"],
                            }
                        },
                    }
                },
            }
        ],
    },
}
if v2:
    xrd["spec"]["scope"] = "Namespaced"
subprocess.run(["kubectl", "apply", "-f", "-"], input=yaml.safe_dump(xrd), text=True, check=True)
# XRD establishment is asynchronous; wait for CRD creation before waiting for Established.
for _ in range(60):
    result = subprocess.run(
        ["kubectl", "get", "crd", "widgets.compass.example.org"], capture_output=True
    )
    if result.returncode == 0:
        break
    time.sleep(2)
else:
    raise RuntimeError("XRD did not establish its CRD")
subprocess.run(
    [
        "kubectl",
        "wait",
        "crd/widgets.compass.example.org",
        "--for=condition=Established",
        "--timeout=120s",
    ],
    check=True,
)
xr = {
    "apiVersion": "compass.example.org/v1alpha1",
    "kind": "Widget",
    "metadata": {"name": "smoke"},
    "spec": {"size": 2},
}
if v2:
    xr["metadata"]["namespace"] = "default"
subprocess.run(["kubectl", "apply", "-f", "-"], input=yaml.safe_dump(xr), text=True, check=True)
s = Compass({"test": Kubernetes(groups={"compass.example.org"})})
ns = "default" if v2 else ""
assert s.resource_get("test", xr["apiVersion"], "Widget", "smoke", ns)["summary"]["name"] == "smoke"
assert s.manifest_validate("test", yaml.safe_dump(xr))["valid"]
assert s.resource_trace("test", xr["apiVersion"], "Widget", "smoke", ns)["nodes"]
assert s.catalog_search("test", "Widget")["items"]
assert not s.manifest_plan("test", yaml.safe_dump(xr))["applied"]
print("Live XRD discovery, scope, validation, trace and GitOps plan passed")
