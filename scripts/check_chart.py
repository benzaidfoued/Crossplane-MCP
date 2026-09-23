"""Render meaningful Helm variants and assert deployment security invariants."""

import os
import subprocess

import yaml

helm = os.getenv("HELM", "helm")


def render(*args):
    output = subprocess.check_output(
        [helm, "template", "test", "charts/crossplane-compass", *args], text=True
    )
    return [x for x in yaml.safe_load_all(output) if x]


for options in [
    [],
    ["--set", "replicaCount=2", "--set", "access.groups[0]=platform.example.org"],
    ["--set", "access.clusterScoped=false", "--set", "access.namespaces[0]=team-a"],
    ["--set", "rbac.create=false", "--set", "serviceAccount.create=false"],
    ["--set", "image.digest=sha256:" + "a" * 64],
    ["--set", "server.additionalAllowedHosts[0]=mcp.example.com:*"],
]:
    docs = render(*options)
    d = next(x for x in docs if x["kind"] == "Deployment")
    c = d["spec"]["template"]["spec"]["containers"][0]
    assert c["securityContext"]["readOnlyRootFilesystem"]
    assert not c["securityContext"]["allowPrivilegeEscalation"]
    for role in [x for x in docs if x["kind"] == "ClusterRole"]:
        for rule in role["rules"]:
            assert set(rule["verbs"]) <= {"get", "list"}
            assert "secrets" not in rule["resources"]
            assert "*" not in rule["apiGroups"]
            assert not ("" in rule["apiGroups"] and "*" in rule["resources"])
    assert next(x for x in docs if x["kind"] == "Service")["spec"]["type"] == "ClusterIP"
for args in [
    ["--set", "server.enableServerDryRun=true"],
    ["--set", "access.groups[0]=*"],
    ["--set", "service.type=LoadBalancer"],
    ["--set", "auth.existingSecret="],
]:
    result = subprocess.run(
        [helm, "template", "test", "charts/crossplane-compass", *args], capture_output=True
    )
    assert result.returncode != 0, args
print("6 Helm variants and 4 invalid-configuration checks passed")
