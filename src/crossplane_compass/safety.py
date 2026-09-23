"""Output minimization and strict reference validation; no shell execution."""

import re
from typing import Any


class CompassError(Exception):
    """Safe, actionable error that contains no upstream response bodies."""


_SEGMENT = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,252}$")
_SENSITIVE = re.compile(
    r"password|passwd|secret|token|credential|private.?key|connection.?string|client.?key", re.I
)


def segment(value: str) -> str:
    if not _SEGMENT.fullmatch(value):
        raise CompassError("Invalid Kubernetes identifier")
    return value


def api_parts(api_version: str) -> tuple[str, str]:
    parts = api_version.split("/")
    if len(parts) != 2:
        raise CompassError("A custom-resource group/version is required")
    return segment(parts[0]), segment(parts[1])


def redact(value: Any) -> Any:
    """Defense in depth, not a guarantee for arbitrary free-form strings."""
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            if k == "managedFields":
                continue
            if k == "annotations":
                result[k] = {
                    key: val
                    for key, val in v.items()
                    if key in {"crossplane.io/external-name", "crossplane.io/paused"}
                }
            else:
                result[k] = "[REDACTED]" if _SENSITIVE.search(k) else redact(v)
        return result
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def controls(obj: dict) -> dict:
    spec = obj.get("spec", {})
    return spec.get("crossplane", spec)


def identity(obj: dict) -> dict:
    m = obj.get("metadata", {})
    return {
        "apiVersion": obj.get("apiVersion", ""),
        "kind": obj.get("kind", ""),
        "name": m.get("name", ""),
        "namespace": m.get("namespace", ""),
    }


def summarize(obj: dict) -> dict:
    m, spec = obj.get("metadata", {}), obj.get("spec", {})
    c = controls(obj)
    return {
        **identity(obj),
        "uid": m.get("uid"),
        "generation": m.get("generation"),
        "resourceVersion": m.get("resourceVersion"),
        "conditions": redact(obj.get("status", {}).get("conditions", [])),
        "externalName": m.get("annotations", {}).get("crossplane.io/external-name"),
        "paused": m.get("annotations", {}).get("crossplane.io/paused") == "true",
        "deleting": m.get("deletionTimestamp"),
        "finalizers": m.get("finalizers", []),
        "composition": c.get("compositionRef"),
        "compositionRevision": c.get("compositionRevisionRef"),
        "providerConfigRef": spec.get("providerConfigRef"),
        "managementPolicies": spec.get("managementPolicies"),
        "deletionPolicy": spec.get("deletionPolicy"),
        "owners": m.get("ownerReferences", []),
    }


def schema_view(value: Any) -> Any:
    """Keep property names/types, but omit literal defaults/examples from schemas."""
    if isinstance(value, dict):
        return {
            k: schema_view(v)
            for k, v in value.items()
            if k not in {"default", "example", "examples"}
        }
    if isinstance(value, list):
        return [schema_view(v) for v in value]
    return value
