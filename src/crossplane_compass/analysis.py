"""Pure evidence-based analysis, schema checks and reviewable GitOps diffs."""

import copy
import difflib
import json

import yaml
from jsonschema import Draft7Validator

from .safety import CompassError, identity, redact, summarize


def findings(obj: dict) -> list[dict]:
    result = []
    s = summarize(obj)

    def add(code, severity, evidence, action):
        result.append(
            {"code": code, "severity": severity, "evidence": evidence, "nextStep": action}
        )

    if s["paused"]:
        add(
            "PAUSED",
            "warning",
            "crossplane.io/paused=true",
            "Review the GitOps annotation before resuming reconciliation.",
        )
    if s["deleting"]:
        add(
            "DELETING",
            "warning",
            {"since": s["deleting"], "finalizers": s["finalizers"]},
            "Inspect provider conditions, Usage protection and external deletion status; do not remove finalizers blindly.",
        )
    for c in s["conditions"]:
        if c.get("status") != "True":
            add(
                "CONDITION_" + c.get("type", "UNKNOWN").upper(),
                "error",
                c,
                "Inspect the referenced child, provider revision and UID-scoped events.",
            )
        if c.get("observedGeneration", s["generation"] or 0) < (s["generation"] or 0):
            add(
                "STALE_CONDITION",
                "warning",
                c,
                "Wait for reconciliation of the current generation.",
            )
    if not s["conditions"]:
        add(
            "NO_CONDITIONS",
            "info",
            "No reported conditions",
            "Check controller ownership and package health; absence is not proof of readiness.",
        )
    policies = s["managementPolicies"]
    if policies == [] or policies == ["Observe"]:
        add(
            "OBSERVE_OR_DISABLED",
            "info",
            policies,
            "Cloud changes may intentionally not be reconciled; verify adoption policy.",
        )
    return result


def schema_errors(schema: dict, manifest: dict) -> list[dict]:
    """OpenAPI subset only. Never resolves remote $ref or executes CEL."""

    def normalize(node):
        if isinstance(node, list):
            return [normalize(x) for x in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            raise CompassError("Schemas containing $ref require server-side validation")
        n = {k: normalize(v) for k, v in node.items()}
        if n.get("x-kubernetes-int-or-string"):
            n.pop("type", None)
            n["anyOf"] = [{"type": "integer"}, {"type": "string"}]
        if n.get("nullable") and isinstance(n.get("type"), str):
            n["type"] = [n["type"], "null"]
        return n

    if not schema:
        raise CompassError("No schema available; local validation cannot be completed")
    validator = Draft7Validator(normalize(schema))
    # Do not echo values: validation messages can contain credentials.
    return [
        {
            "path": "/" + "/".join(str(x) for x in e.absolute_path),
            "rule": e.validator,
            "message": f"Failed {e.validator} constraint",
        }
        for e in sorted(validator.iter_errors(manifest), key=lambda e: str(list(e.path)))
    ][:100]


def parse_manifest(text: str) -> dict:
    if len(text.encode()) > 262144:
        raise CompassError("Manifest exceeds 256 KiB")
    try:
        obj = yaml.safe_load(text)

        # Reject cycles/alias expansion and excessive nested structures before processing.
        def walk(x, depth=0, seen=None):
            if depth > 40:
                raise CompassError("Manifest nesting exceeds 40 levels")
            if isinstance(x, (dict, list)):
                seen = set() if seen is None else seen
                if id(x) in seen:
                    raise CompassError("YAML aliases are unsupported")
                seen.add(id(x))
                if isinstance(x, dict) and not all(isinstance(key, str) for key in x):
                    raise CompassError("YAML mapping keys must be strings")
                for child in x.values() if isinstance(x, dict) else x:
                    walk(child, depth + 1, seen)

        walk(obj)
        if not isinstance(obj, dict) or not isinstance(obj.get("metadata"), dict):
            raise CompassError("Expected one Kubernetes manifest with metadata")
        if not all(isinstance(obj.get(k), str) for k in ("apiVersion", "kind")):
            raise CompassError("apiVersion and kind are required strings")
        if not isinstance(obj["metadata"].get("name"), str):
            raise CompassError("metadata.name is required")
        if "status" in obj:
            raise CompassError("Remove status from desired manifests")
        json.dumps(obj)  # reject non-JSON YAML dates and keys
        return obj
    except (yaml.YAMLError, ValueError, TypeError, RecursionError):
        raise CompassError("Invalid single-document JSON-compatible YAML") from None


def desired(obj: dict) -> dict:
    value = copy.deepcopy(obj)
    value.pop("status", None)
    m = value.get("metadata", {})
    for k in (
        "uid",
        "resourceVersion",
        "generation",
        "creationTimestamp",
        "managedFields",
        "deletionTimestamp",
        "deletionGracePeriodSeconds",
        "selfLink",
    ):
        m.pop(k, None)
    return value


def proposal(live: dict | None, manifest: dict) -> dict:
    before = yaml.safe_dump(redact(desired(live)), sort_keys=True) if live else ""
    after = yaml.safe_dump(redact(desired(manifest)), sort_keys=True)
    return {
        "identity": identity(manifest),
        "operation": "update" if live else "create",
        "diff": "".join(
            difflib.unified_diff(
                before.splitlines(True),
                after.splitlines(True),
                fromfile="live (redacted)",
                tofile="desired (redacted)",
            )
        ),
        "manifest": after,
        "applied": False,
        "warnings": [
            "Redacted review output is not an apply-ready artifact. Keep the original manifest in your GitOps PR.",
            "This is a spec diff, not a prediction of cloud replacements or cost.",
            "Review admission policies, provider semantics and composition revisions before merging.",
        ],
    }


def adoption_report(obj: dict) -> dict:
    s = summarize(obj)
    warnings = []
    if not s["externalName"]:
        warnings.append(
            "Missing crossplane.io/external-name; derive the provider-specific import ID from authoritative cloud state."
        )
    if s["managementPolicies"] != ["Observe"]:
        warnings.append(
            "Use managementPolicies: [Observe] for the initial import where supported by the provider."
        )
    if s["deletionPolicy"] != "Orphan":
        warnings.append(
            "Consider deletionPolicy: Orphan during migration; verify interaction with managementPolicies."
        )
    if not s["providerConfigRef"]:
        warnings.append(
            "No explicit providerConfigRef; verify which credentials the default configuration uses."
        )
    if any(o.get("controller") for o in s["owners"]):
        warnings.append(
            "A controller owns this resource. Manual edits may be reverted; change the owning XR/composition."
        )
    else:
        warnings.append(
            "No controller owner: importing a standalone MR does not automatically attach it to an XR."
        )
    return {
        "resource": s,
        "warnings": warnings,
        "cloudIdentityVerified": False,
        "note": "External-name formats and Observe support are provider-specific; no cloud API was queried.",
    }


def composition_report(obj: dict) -> dict:
    spec = obj.get("spec", {})
    pipeline = spec.get("pipeline", [])
    return {
        "name": obj.get("metadata", {}).get("name"),
        "mode": spec.get("mode", "Resources"),
        "compositeTypeRef": spec.get("compositeTypeRef"),
        "steps": [
            {
                "step": x.get("step"),
                "function": x.get("functionRef", {}).get("name"),
                "inputKind": (x.get("input") or {}).get("kind"),
            }
            for x in pipeline
        ],
        "legacyResourceCount": len(spec.get("resources", [])),
        "warnings": (
            []
            if pipeline
            else [
                "No function pipeline; inspect whether legacy Resources mode is supported by your Crossplane version."
            ]
        ),
        "note": "Static inspection only; arbitrary function output cannot be inferred without running functions.",
    }
