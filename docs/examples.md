# Operational examples

These prompts use your real configured cluster alias and actual installed API kinds. The assistant should discover them first. No examples require write access.

## Diagnose a stuck XR

> In nonprod, inspect the Database `orders` in namespace `team-a`. Trace its composed resources, identify the deepest failing conditions, and include events for the XR. Separate evidence from hypotheses and propose a GitOps change.

Workflow: `discover` → `resource_trace` / `diagnose` → `resource_events` → `packages_health`. If a child cannot be accessed, report that instead of assuming it is absent. Graphs are bounded; inspect `truncated` and `errors`.

## Map Crossplane to an Azure Cosmos DB account

1. Discover the installed `Account` kind and version in the actual provider API group.
2. Call `resources_list` or `external_lookup` for that kind, using the exact external-name value; follow `continueToken` until empty.
3. Read the matching MR summary and `resource_owners` to find its controlling XR.
4. Compare the reported external identifier to Azure's authoritative account/resource ID yourself. `external_lookup` does not authenticate to Azure and cannot prove the ID is correct.

Do not confuse the account resource with SQLDatabase or SQLContainer. External-name formats depend on the provider; they are not always Azure ARM IDs.

## Investigate a RoleAssignment import

> Inspect this RoleAssignment MR. Explain the external-name, provider config, management policies and controller owner. Why could a manually changed principalId revert?

Use `adoption_check`, `resource_owners`, `resource_get(detail=true)`, and the owning XR's trace. If the composition controls the field, change the composition/XR through GitOps. Standalone imported MRs do not automatically become children of a newly created XR. Compass does not fabricate RoleAssignment IDs or principal IDs, and does not attach an MR to an XR.

## Generate a request from the installed contract

> Find the PostgreSQL service in the catalog. Inspect the installed schema and scaffold an XR named orders-db. Ask me for any required fields you cannot determine. Validate the completed YAML and prepare a review diff.

Use `catalog_search` → `resource_schema` → `manifest_scaffold` → fill `needsInput` → `manifest_validate` → `manifest_plan`. Required fields without safe defaults stay `null` and must be supplied. Review the original manifest, because returned diffs redact sensitive keys and nonessential annotations.

## Review composition revision changes

Use `composition_compare(first=oldRevision, second=newRevision)` to compare pipeline metadata and spec. Use `composition_impact` for each affected XR kind and paginate to find consumers and `Automatic` / `Manual` update policies. This is not a function-render simulation or guaranteed full-cluster impact analysis.

## Migration between control planes

Run `migration_assess` on the source MR, inspect target schemas using the target cluster alias, and validate a target Observe manifest. Verify cloud IDs independently. Do not give two reconcilers write authority over one cloud object. Rollback is an operational plan, not an automatic Compass action.
