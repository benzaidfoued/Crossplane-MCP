import pytest
from conftest import SCHEMA, obj

from crossplane_compass.analysis import (
    adoption_report,
    findings,
    parse_manifest,
    proposal,
    schema_errors,
)
from crossplane_compass.safety import CompassError, redact


@pytest.mark.parametrize(
    "size,valid", [(2, True), ("2", False), (True, False), (0, False), (-1, False)]
)
def test_typed_schema(size, valid):
    o = obj()
    o["spec"]["size"] = size
    assert (not schema_errors(SCHEMA, o)) == valid


def test_azure_region_not_aws_assumption():
    o = obj()
    o["spec"]["region"] = "canadacentral"
    assert schema_errors(SCHEMA, o) == []


def test_nullable_int_or_string():
    assert schema_errors({"type": "string", "nullable": True}, None) == []
    assert schema_errors({"x-kubernetes-int-or-string": True}, 12) == []


def test_no_remote_schema_refs():
    with pytest.raises(CompassError, match="ref"):
        schema_errors({"$ref": "https://attacker.invalid"}, {})


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        "a: 1",
        "a: &x [*x]",
        "---\na: 1\n---\nb: 2",
        "x" * 262145,
        "!!python/object/apply:os.system ['id']",
        "apiVersion: g/v1\nkind: A\nmetadata: {name: x}\nstatus: {}",
    ],
)
def test_manifest_rejection(text):
    with pytest.raises(CompassError):
        parse_manifest(text)


def test_adoption_explains_ownership():
    o = obj()
    o["metadata"]["ownerReferences"] = [{"controller": True, "name": "xr"}]
    r = adoption_report(o)
    assert not r["cloudIdentityVerified"]
    assert any("reverted" in x for x in r["warnings"])


def test_redaction_and_diff():
    live = obj()
    live["spec"]["password"] = "TOPSECRET"
    live["metadata"]["annotations"] = {
        "kubectl.kubernetes.io/last-applied-configuration": "TOPSECRET"
    }
    manifest = obj()
    manifest["spec"]["password"] = "NEWSECRET"
    manifest["spec"]["size"] = 3
    result = proposal(live, manifest)
    assert "TOPSECRET" not in str(result) and "NEWSECRET" not in str(result)
    assert "+  size: 3" in result["diff"]
    assert not result["applied"]
    assert "resourceVersion" not in result["manifest"]


def test_findings_distinguish_absence_and_stale():
    o = obj()
    o["metadata"]["annotations"] = {"crossplane.io/paused": "true"}
    o["status"]["conditions"][0]["observedGeneration"] = 1
    assert {x["code"] for x in findings(o)} == {"PAUSED", "STALE_CONDITION"}
    o["status"] = {}
    assert "NO_CONDITIONS" in {x["code"] for x in findings(o)}


def test_operational_annotations_visible_without_last_applied():
    value = {
        "metadata": {
            "annotations": {
                "crossplane.io/external-name": "/subscriptions/example/resource",
                "crossplane.io/paused": "true",
                "kubectl.kubernetes.io/last-applied-configuration": "PRIVATE",
            }
        }
    }
    safe = redact(value)
    assert "PRIVATE" not in str(safe)
    assert safe["metadata"]["annotations"]["crossplane.io/paused"] == "true"


def test_schema_view_preserves_sensitive_field_types():
    from crossplane_compass.safety import schema_view

    schema = {"properties": {"password": {"type": "string", "default": "PRIVATE"}}}
    assert schema_view(schema) == {"properties": {"password": {"type": "string"}}}


def test_nonstring_yaml_keys_rejected():
    with pytest.raises(CompassError, match="keys must be strings"):
        parse_manifest(
            "apiVersion: example.org/v1\nkind: Test\nmetadata: {name: test}\nspec: {1: bad}"
        )
