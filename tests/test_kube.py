import pytest
from conftest import GROUP, obj

from crossplane_compass.kube import Kubernetes
from crossplane_compass.safety import CompassError


def test_irregular_plural_and_cluster_scope(kube, api):
    assert kube.get(f"{GROUP}/v1", "Policy", "policy")["kind"] == "Policy"
    assert api.calls[-1][0] == f"/apis/{GROUP}/v1/policies/policy"


@pytest.mark.parametrize(
    "version,kind,name,ns",
    [
        ("v1", "Secret", "key", "team-a"),
        ("evil.io/v1", "Database", "db", "team-a"),
        (f"{GROUP}/v1", "Database", "../db", "team-a"),
        (f"{GROUP}/v1", "Database", "db", "team-b"),
        (f"{GROUP}/v1", "Database", "db", ""),
        (f"{GROUP}/v1", "Policy", "policy", "team-a"),
        (f"{GROUP}/v9", "Database", "db", "team-a"),
    ],
)
def test_access_boundaries(kube, version, kind, name, ns):
    with pytest.raises(CompassError):
        kube.get(version, kind, name, ns)


def test_cache(kube, api):
    kube.resolve(f"{GROUP}/v1", "Database")
    kube.resolve(f"{GROUP}/v1", "Database")
    assert sum(p.endswith("customresourcedefinitions") for p, _, _ in api.calls) == 1
    assert sum(p == f"/apis/{GROUP}/v1" for p, _, _ in api.calls) == 1


def test_pagination_forwarding(kube, api):
    kube.list(f"{GROUP}/v1", "Database", "team-a", 12, "cursor", "team=a")
    q = dict(api.calls[-1][2]["query_params"])
    assert q == {"limit": 12, "continue": "cursor", "labelSelector": "team=a"}


@pytest.mark.parametrize("limit", [0, 201])
def test_page_limit(kube, limit):
    with pytest.raises(CompassError):
        kube.list(f"{GROUP}/v1", "Database", "team-a", limit)


def test_cluster_denial(api):
    k = Kubernetes(api=api, groups={GROUP}, allow_cluster=False)
    with pytest.raises(CompassError, match="Cluster-scoped"):
        k.get(f"{GROUP}/v1", "Policy", "policy")


def test_dryrun_always_guarded(kube, api):
    with pytest.raises(CompassError, match="dry-run"):
        kube.dry_run(obj())
    kube.dry_run_enabled = True
    kube.dry_run(obj())
    assert dict(api.calls[-1][2]["query_params"])["dryRun"] == "All"
    with pytest.raises(CompassError):
        kube.request("/evil", query={}, body={})


def test_errors_do_not_echo_upstream(kube, api):
    api.denied.add(f"/apis/{GROUP}/v1/namespaces/team-a/databases/db")
    with pytest.raises(CompassError, match="RBAC denied") as e:
        kube.get(f"{GROUP}/v1", "Database", "db", "team-a")
    assert "DO_NOT_LEAK" not in str(e.value)


def test_events_use_uid(kube, api):
    kube.events(obj())
    assert dict(api.calls[-1][2]["query_params"])["fieldSelector"] == "involvedObject.uid=db-uid"


def test_namespace_policy_prevents_cluster_event_scan(kube):
    with pytest.raises(CompassError, match="event access"):
        kube.events(obj("Policy", "policy", ""))
