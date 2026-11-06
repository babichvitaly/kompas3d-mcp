# Development toolkit 0.2.0.dev2 / runtime 14

This is an installable development candidate, not a claim of general CAD or
manufacturing coverage. It builds on the preserved runtime-13 implementation.
Keep MIT LICENSE and original project authorship. No production model or SDK
binary belongs in the toolkit distribution.

## Command line

```text
kompas-cad --version
kompas-cad capabilities
kompas-cad verify-result /absolute/job/result.json --launcher-returncode 0
kompas-cad run-recipe --terminal-result /absolute/new/result.json -- python recipe.py
kompas-cad package-preflight --plan /absolute/plan.json --destination /absolute/new-copy
kompas-cad package-stage --plan /absolute/plan.json --destination /absolute/new-copy
```

Use host-native absolute paths (Windows paths on Windows). `run-recipe` runs an
explicit command once without a shell, refuses a pre-existing terminal file and
exclusively reserves its canonical path with a retained sibling lease before
launch. The result directory must already exist. Cooperating runners cannot use
the same path concurrently; a lease is not permission to retry a failed job.
It then uses the same result classifier as the worker. A child
exit code of zero with `failed_left_open` produces wrapper exit code 1. A missing,
unknown or uncertain result returns 2. There is no automatic mutation retry or
forced termination of a native call. Child output is inherited; the final JSON
assessment is printed after child completion.

`capabilities` inventories actual registered MCP schemas and code fingerprints
without connecting to CAD. Run it in the candidate environment before deciding
to switch a client. Installation of the wheel does not register an MCP client or
replace another environment.

## Persistent jobs and phase timings

Set `KOMPAS_MCP_JOB_DIR` to an owned result folder when starting the candidate MCP
server, or pass `result_directory` to `ComWorker`. The default remains in-memory
history without persistent writes. Each job gets a new directory, atomic
`result.json` and append-only events. Record input SHA and application identity
as explicit caller metadata; absent evidence is never manufactured.

One STA and the existing bounded queue remain authoritative. A pending native
operation may outlive client cancellation. Completion of a Python wrapper,
declared execution, verified artifacts and physical acceptance are different
fields. A generic tool reply remains `wrapper_completed` and unreported for
execution verification. Inspect both terminal result and document ownership
before another mutation. A disk-publication error must also fail the awaiting
caller; it must not turn into an apparent successful result.

`phase(...)` and `timed_phase(...)` instrument existing code without changing
operation arguments. Native document lifecycle, drawing inventory, SHA checks,
dependency traversal and export have phase spans. Selected Update/Rebuild/SaveAs
calls have explicit `native_calls`; function-level spans have `function_calls`.
These are counts of instrumented calls, not a count of every COM call. Child
inclusive time overlaps its parent: use exclusive time or union wall time,
never sum all elapsed spans. Phase instrumentation alone proves no speedup.

## Views

Three read-only tools expose state inspection, state comparison and a visible
anchor resolved through actual projection geometry. They do not repair a
camera, activate Current, modify Unfold, rebuild a view or save a document.
Configure/local-cut mutations still require dedicated native acceptance.
Re-resolve view/curve handles after model updates or reopening. See the
supported-curve and identity constraints in [view-state](view-state.md).

## Project staging

The offline preflight checks all declared sources, SHA, destination collisions,
Windows filename rules, optional multi-root graph and explicit runtime-resource
policy before creating a folder. Staging writes only a new owned directory and
rechecks both source bytes and copied bytes. Failures preserve an inspectable
manifest; output names are not reused automatically.

A successful `files_staged_not_rebound` manifest has `portable=false`.
Native reference rewriting, complete external-link scan, source-history/BOM/pose
checks, Save + independent reopen and a second-location test remain separate
gates. The existing `project_copy` native implementation is retained; staging
does not silently replace it or convert source models to unlinked bodies.

## Acceptance boundaries

Pure unit tests cover protocol/lifecycle/filesystem cases without installed CAD.
An installed-wheel capability inventory proves import, entrypoint and schema
registration, not geometry. Live read-only view checks and full project
relocation must be recorded separately before using those claims.
