---
name: kompas-api
description: Extend or troubleshoot КОМПАС-3D automation using installed API5/API7 COM type libraries and SDK documentation. Use for advanced native operations, constraints, assemblies, topology inspection, or missing high-level kompas3d MCP tools.
---

# KOMPAS SDK automation

Prefer installed evidence over remembered COM names. Use the `kompas3d` server's
`sdk_search`, `sdk_read`, `api_constants`, `api_describe`, and `api_invoke` tools.
The installed v25 SDK is authoritative for this machine; do not copy unrelated
CAD APIs or rely on an older online sample's numeric constants.

## Discover, then act

`connect` returns API5 `application` and API7 `application7` handles.
`inspect_model` returns native document/part handles and entities created during
the server session. For existing documents, explicitly open or attach and verify
identity. Discover the full tree through the documented collection interfaces.

Use `list_entities` for existing feature/topology discovery. Solid edge/face queries
exclude auxiliary sketch/datum geometry by default. `api_catalog` and
`api_describe_interface` expose installed interfaces before an object exists;
`api_cast` accesses additional QueryInterface interfaces. `api_batch` supplies checked
dependent steps and typed arrays. Read [tool workflows](references/tool-workflows.md)
for exact request syntax and verified native feature recipes.

Describe a handle before invoking it. Search SDK filenames by interface/member,
then read the result and follow links to enums and related parameter interfaces.
Pass referenced COM objects as `{"handle":"id"}`; do not pass Python expressions.
Call a method with positional `arguments`, read a property with `action="get"`,
or set one with `action="set", value=...`.

Choose noninteractive operations. Interactive selection methods may block the
COM worker on an unanswered application dialog. Treat API return false/zero/null
according to its documentation; successful MCP transport is not successful CAD.

For native features, obtain an entity's definition, configure its documented
references and parameters, then create or update it. For topology, identify edges
and faces geometrically instead of retaining collection indices through rebuilds.
For API7-only interfaces, navigate from `application7` using its generated schema.

`api_invoke` is unrestricted local COM and can save, delete, close, or modify
files/documents. It bypasses the typed tools' overwrite and ownership checks.
Stay within the user's requested operation and check file paths before writes.
Do not invoke application Quit as routine cleanup; the user may have other work.

## Server development invariants

- Keep all COM object creation, use, and release on the existing single STA worker.
  Never return raw COM references to the asyncio/MCP thread; return opaque handles.
- Keep Python's stdout exclusively for MCP protocol. Use stderr for logs.
- Load generated wrappers from the installed type libraries. The root API5 object
  needs explicit QueryInterface to `KompasObject`; EnsureDispatch alone failed on
  the tested Home edition. Avoid requiring registry changes or administrator mode.
- API5 additive and cut extrusion direction conventions differ. Preserve the
  public tool contract where reverse=false follows the sketch normal for both.
- Preserve evidence of failed partial mutations. Do not retry on a timeout without
  reconciling the model. Python cancellation cannot abort a running COM call.
- Driving variable edits require document `RebuildDocument`, not only part rebuild.
  Use `set_variable` to commit and return measured geometry. Clearing an expression
  before setting a numeric value can delete a user variable; set the value directly.
- Use checked native outputs and quantitative geometry assertions for integration
  tests. A mocked Create=true response cannot establish that the solid is correct.

If a required feature has no reliable Automation signature, report the exact
limitation and investigate the documented API7 equivalent. Do not invent success
or replace native parametric geometry with a mesh without making that tradeoff clear.

## Task-specific SDK routes

Read only the relevant reference:

- [Advanced modeling operations](references/modeling-operations.md): shell, rib,
  draft, loft, sweep, holes, threads, patterns, mirrors, Booleans, direct face
  edits, surfaces and sheet metal.
- [Parametrics, drawings and assemblies](references/parametrics-documents.md):
  constraints and variables, associative views, annotation, components and mates.

These references distinguish documented SDK routes from live-tested workflows.
A discovered interface or successful dispatch is not evidence that its requested
geometry was built. Report unsupported signatures or edition restrictions
precisely and retain inspectable evidence of partial work.
