import pytest
import yaml
from conftest import GROUP, obj

from crossplane_compass.safety import CompassError


def test_v2_trace_namespaced_xr_cluster_mr(compass, api):
    root = api.objects[f"/apis/{GROUP}/v1/namespaces/team-a/databases/db"]
    root["spec"]["crossplane"] = {
        "resourceRefs": [{"apiVersion": f"{GROUP}/v1", "kind": "Policy", "name": "policy"}]
    }
    r = compass.resource_trace("test", f"{GROUP}/v1", "Database", "db", "team-a")
    assert len(r["nodes"]) == 2
    assert not r["errors"]
    assert r["nodes"][1]["namespace"] == ""


def test_v1_claim_xr_cycle_and_limit(compass, api):
    root = api.objects[f"/apis/{GROUP}/v1/namespaces/team-a/databases/db"]
    root["spec"]["resourceRef"] = {"apiVersion": f"{GROUP}/v1", "kind": "Policy", "name": "policy"}
    policy = api.objects[f"/apis/{GROUP}/v1/policies/policy"]
    policy["spec"]["resourceRefs"] = [
        {"apiVersion": f"{GROUP}/v1", "kind": "Database", "name": "db", "namespace": "team-a"}
    ]
    r = compass.resource_trace("test", f"{GROUP}/v1", "Database", "db", "team-a")
    assert len(r["nodes"]) == 2 and not r["truncated"]
    assert compass.resource_trace("test", f"{GROUP}/v1", "Database", "db", "team-a", max_nodes=1)[
        "truncated"
    ]


def test_partial_errors_preserved(compass, api):
    api.objects[f"/apis/{GROUP}/v1/namespaces/team-a/databases/db"]["spec"]["resourceRefs"] = [
        {"apiVersion": f"{GROUP}/v1", "kind": "Policy", "name": "absent"}
    ]
    r = compass.diagnose("test", f"{GROUP}/v1", "Database", "db", "team-a")
    assert "404" in r["trace"]["errors"][0]["error"]


def test_plan_no_writes(compass, api):
    o = obj()
    o.pop("status")
    o["spec"]["size"] = 4
    r = compass.manifest_plan("test", yaml.safe_dump(o))
    assert r["operation"] == "update"
    assert "+  size: 4" in r["diff"]
    assert all(method == "GET" for _, method, _ in api.calls)


def test_plan_new_and_invalid(compass):
    o = obj(name="new")
    o.pop("status")
    assert compass.manifest_plan("test", yaml.safe_dump(o))["operation"] == "create"
    o["spec"]["size"] = "bad"
    assert not compass.manifest_plan("test", yaml.safe_dump(o))["validation"]["valid"]


def test_plan_forbidden_is_not_create(compass, api):
    api.denied.add(f"/apis/{GROUP}/v1/namespaces/team-a/databases/db")
    o = obj()
    o.pop("status")
    with pytest.raises(CompassError, match="403"):
        compass.manifest_plan("test", yaml.safe_dump(o))


def test_scaffold_missing_inputs(compass):
    result = compass.manifest_scaffold("test", f"{GROUP}/v1", "Database", "new", "team-a")
    assert "/spec/size" in result["needsInput"]
    assert result["manifest"]["spec"]["size"] is None


def test_lookup_and_inventory(compass, api):
    api.objects[f"/apis/{GROUP}/v1/namespaces/team-a/databases/db"]["metadata"]["annotations"] = {
        "crossplane.io/external-name": "/azure/account/id"
    }
    api.continue_token = "next-page"
    r = compass.external_lookup("test", f"{GROUP}/v1", "Database", "/azure/account/id", "team-a")
    assert len(r["matches"]) == 1 and r["continueToken"] == "next-page"
    assert (
        compass.inventory_summary("test", f"{GROUP}/v1", "Database", "team-a")["counts"]["ready"]
        == 1
    )


def test_owner_uid_verification(compass, api):
    api.objects[f"/apis/{GROUP}/v1/namespaces/team-a/databases/db"]["metadata"][
        "ownerReferences"
    ] = [{"apiVersion": f"{GROUP}/v1", "kind": "Policy", "name": "policy", "uid": "wrong"}]
    r = compass.resource_owners("test", f"{GROUP}/v1", "Database", "db", "team-a")
    assert not r["owners"] and "UID" in r["errors"][0]["error"]


def test_migration_deletion_do_not_claim_safety(compass):
    args = ("test", f"{GROUP}/v1", "Database", "db", "team-a")
    assert not compass.migration_assess(*args)["executed"]
    assert compass.deletion_assess(*args)["safeToDelete"] == "undetermined"
    assert compass.incident_bundle(*args)["events"]["events"]


def test_unknown_cluster(compass):
    with pytest.raises(CompassError):
        compass.discover("production")


def test_composition_and_packages(compass, api):
    for kind, name in [
        ("Composition", "comp"),
        ("CompositionRevision", "r1"),
        ("CompositionRevision", "r2"),
    ]:
        api.put(
            {
                "apiVersion": "apiextensions.crossplane.io/v1",
                "kind": kind,
                "metadata": {"name": name},
                "spec": {
                    "mode": "Pipeline",
                    "pipeline": [{"step": "render", "functionRef": {"name": "go-templating"}}],
                },
            }
        )
    assert compass.composition_explain("test", "comp")["steps"][0]["function"] == "go-templating"
    assert compass.composition_compare("test", "r1", "r2")["first"]["name"] == "r1"
    api.put(
        {
            "apiVersion": "pkg.crossplane.io/v1",
            "kind": "Provider",
            "metadata": {"name": "azure"},
            "spec": {"package": "xpkg.upbound.io/upbound/provider-family-azure:v2.6.0"},
            "status": {"conditions": [{"type": "Healthy", "status": "False"}]},
        }
    )
    assert compass.packages_health("test")["packages"][0]["findings"]


def test_catalog(compass, api):
    api.put(
        {
            "apiVersion": "apiextensions.crossplane.io/v2",
            "kind": "CompositeResourceDefinition",
            "metadata": {"name": "databases.platform.example.org"},
            "spec": {
                "group": GROUP,
                "names": {"kind": "Database"},
                "scope": "Namespaced",
                "versions": [{"name": "v1", "served": True}],
            },
        }
    )
    assert compass.catalog_search("test", "Database")["items"][0]["scope"] == "Namespaced"
    assert not compass.catalog_search("test", "missing")["items"]


def test_provider_config_does_not_read_secrets(compass, api):
    api.put(
        obj(
            "ProviderConfig",
            "default",
            spec={"credentials": {"source": "Secret", "secretRef": {"name": "creds"}}},
        )
    )
    r = compass.provider_config_check(
        "test", f"{GROUP}/v1", "Database", "db", f"{GROUP}/v1", "team-a"
    )
    assert r["credentialSource"] == "Secret" and not r["credentialsVerified"]
    assert not any("/secrets" in path for path, _, _ in api.calls)


def test_impact_and_summaries(compass, api):
    api.objects[f"/apis/{GROUP}/v1/namespaces/team-a/databases/db"]["spec"]["crossplane"] = {
        "compositionRef": {"name": "comp"},
        "compositionUpdatePolicy": "Manual",
    }
    assert (
        compass.composition_impact("test", "comp", f"{GROUP}/v1", "Database", "team-a")[
            "consumers"
        ][0]["updatePolicy"]
        == "Manual"
    )
    assert compass.resource_schema("test", f"{GROUP}/v1", "Database")["scope"] == "Namespaced"
    assert compass.resources_list("test", f"{GROUP}/v1", "Database", "team-a")["items"]
    assert compass.resource_get("test", f"{GROUP}/v1", "Database", "db", "team-a", True)["manifest"]
    assert compass.clusters_list()["clusters"][0]["alias"] == "test"
    assert compass.discover("test")["resources"]
