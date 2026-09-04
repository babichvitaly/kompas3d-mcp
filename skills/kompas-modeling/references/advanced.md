# Advanced native operations

The server exposes installed API5 and API7 interfaces without running arbitrary
Python code. `api_invoke` is unrestricted local COM access and can change documents
or write files. It is not a sandbox and bypasses typed-tool save/ownership checks.
Use it only within the requested model work. No need for an extra approval for a
routine authorized model edit.

## Discovery cycle

1. Obtain `application`/`application7` from `connect`, or `document`/`part` and
   entity `object` handles from `inspect_model`.
2. Call `api_describe(handle=...)` to get installed signatures and readable /
   writable property names. Never invent a method from another CAD API.
3. `sdk_search(query="ksfilletdefinition")` finds local help topic filenames.
   `sdk_read(topic=...)` supplies the documentation and links. Read property,
   method, parameter, and enum topics relevant to the operation.
4. `api_constants(query="fillet")` resolves installed enum values. Header-only
   macros may not appear; consult the SDK header rather than inventing a value.
5. Invoke one coherent operation at a time and inspect the returned values.
   `false`, zero, or null can mean failure even when the MCP call itself succeeds.

COM references passed as arguments must be exactly `{"handle":"returned-id"}`.
Returned references include an interface name; use only the handle field in arguments.
Properties use `action="get"` or `action="set", value=...`. Methods use
`action="call", arguments=[...]`. Optional output parameters generally use their
generated defaults and return tuples, but some old Automation signatures expose
unsupported by-reference inputs. If a signature cannot be expressed reliably,
look for the equivalent API7 interface and document the limitation.

## Native feature pattern

API5 usually follows `part.NewEntity(enum)` -> entity `GetDefinition()` -> set
properties / references -> entity `Create()`. Existing definitions use `Update()`
or the documented rebuild method instead of creating a duplicate. Query the exact
interface before using either. Native constraints/variables require their own
sketch constraint and variable collections; drawing coordinate geometry alone
does not create them.

For fillets/chamfers, discover the edge collection and select by geometry:
curve type, radius, center, endpoints, adjacency, and location relative to datums.
Do not persist a bare edge index across rebuilds. Confirm the selected set, then
create the operation and verify removed volume / new surfaces and preview.

For patterns/mirrors, retain the seed feature reference and use explicit axis or
plane references. For lofts, make section planes and ordered closed contours;
confirm their winding and start alignment to avoid twists. For sweeps, distinguish
the path sketch from the section and verify the section-plane orientation.

For assemblies, operate on a native A3D document via API7, insert known part files,
then create documented mate constraints. Confirm component count and placements.
Use the available native assembly/document tools when present; `create_part`
creates a part. Do not represent a set of
disconnected solids as a constrained assembly.

## Recovery

After a failed mutation, inspect tree/volume and the operation's SDK status before
retrying. Remove only geometry created for that failed attempt if necessary.
Entity handles may become stale after a user deletion or document closure.
If `Open` fails because the file is already open, explicitly attach to that document
and verify its filename, rather than claiming it was imported successfully.

When an operation requires a user-facing prompt or modal selection, prefer the
noninteractive equivalent documented in the SDK. Never invoke interactive picker
methods and then assume a background server can answer them.

For specific SDK members and exact installed help topics, load `$kompas-api`
and its task-specific references. They cover modeling operations, sheet metal,
constraints, drawing annotation and mates, with verification limits stated.
