# Runtime and copy-scoped workflows, revision 13

These tools extend the existing single COM STA. They do not turn a successful
COM return into a geometry certificate. Use a fresh server process after source
changes; `runtime_health` exposes loaded/disk code and schema fingerprints.
Production models and private reports remain outside this repository.

## Runtime and documents

- `runtime_health`: code directory/revision, schema fingerprint and tool names,
  queue snapshot and SDK schema cache statistics. No COM call. A responsive
  Python transport does not prove KOMPAS is responsive.
- `job_status`: bounded task history, IDs, operation names, queue/running times.
  Status remains accessible while the STA is busy.
- `cancel_job`: cancels only a queued job. A running native call continues and
  may mutate a document after a client timeout. Reconcile before retrying.
- `list_documents(details=false)`: lightweight identity/state/visibility list.
  `document_details` or `details=true` hydrates model/view handles explicitly.
- `close_documents`: dry run by default, explicit protected/candidate handles,
  rechecks dirty state. Never saves/discards user edits or quits KOMPAS. Omitted
  candidates cover only server-owned documents, not adopted user documents.

Legacy API5 and API7 lifecycle routes share document scopes. Saving checks the
actual native path, dirty state and file-write evidence, including overwrites.
SDK interface schemas use a bounded pure-Python cache; mutable returned schemas
are independent copies. COM remains sequential. Worker shutdown bounds only
the caller's wait; a blocked native call can still delay process termination.

## Drawings

- `inspect_drawing`: native views/sources, measured linear dimensions, editable
  texts, leaders, sheet/stamp and line/circle/arc inventories. Detailed output
  can be written to a new report path; the snapshot includes a stale-plan hash.
- `rebind_drawing_views`: operates on a saved owned copy and preserves existing
  view/dimension identities. Requires an expected snapshot and geometry checks
  for each affected view. Coordinate dimension edits and expected automatic
  placement changes are explicit. It does not silently reposition dimensions.
  An explicit list of views may authorize removal of newly generated scale-only
  captions. Existing/user texts remain protected; native markup, scale and
  `IViewDesignation.DrawingText` ownership must all match before deletion.
- `export_drawing`: saved owned CDW copies to new PDF/DXF paths. Uses native
  converters, validates structure/content, writes hashes and optional reports.
  No implicit save or overwriting. PDF visual layout needs a separate review.

The installed native PDF converter can close or replace its input CDW. After
each converter call the tool pumps STA messages and reconciles document scopes;
if needed it reopens only the exported owned copy with its prior read-only and
visibility flags. It verifies clean state, inventoried content and file hashes,
returns `document_after_export` and records `native_lifecycle`. Callers must use
the returned fresh document handle. Session identity is not promised to survive.

Dependencies must remain within the declared copy root, including linked
models, variable/geometry resources and layout libraries. Dirty linked models
are rejected. Copy the required layout resource and rebind its sheet reference
explicitly; do not alter the installed system library.

Projected geometry is quantitatively covered for lines, circles and arcs.
Other 2D entity types and complicated annotation associations need additional
acceptance. Source/view rebuild success alone does not establish actual geometry.
Native text objects must be read through their documented interfaces: e.g.
`IDimensionText.NominalText` is an `ITextLine`, not a string.

## Isolated copies, collision fixtures and sketch frames

- `create_isolated_copy`: dry-run dependency plan, one byte copy per source,
  bottom-up native rebind, original hashes, reopened links and occurrence
  matrices. Relative paths resolve against their owning source document.
  Missing files, unsaved sources, cyclic graphs and library pseudo paths are
  rejected before copying. This is a file-backed dependency DAG workflow,
  not a universal packager for cyclic specification/assembly links.
- `create_collision_fixture`: maps explicit nested occurrence paths to a new
  assembly's top-level instances using composed world matrices. Verifies sources
  and placements after reopen. Does not establish transfer of assembly-context
  cuts or native collision endpoint attribution. Check fixture scopes separately.
- `set_sketch_frame`: native API5 in-plane translation/angle, verified using
  API7 `GetPoint3D` origin and unit axes. Requires a fresh expected frame to apply.
  Changes world geometry intentionally; no primitive-coordinate approximation.
  It does not save or certify downstream features.
- `inspect_body_components`: read-only native `MultiBodyParts` and a bounded
  connected face graph of own solid bodies. Boundary shells are not interpreted
  as a volumetric piece count; a cavity can have disconnected boundaries.
  Incomplete adjacency/limits remain inconclusive. A cached history outline is
  reported separately. The historical `IModelObject1.MultiBodyParts` getter is
  deliberately not called: native acceptance found that it can dirty a
  read-only document. Body-level diagnosis does not prove which operation first
  introduced a split.

The cached audit now reports `ksFSComprisedOfParts` as a warning and checks
`IBody7.MultiBodyParts` independently of the body's count/IsSolid/ObjectError.

## Acceptance

Use an interactive Windows user session and a new absolute output directory.
Each new acceptance script communicates via real stdio with explicit source
selection, checks schemas before CAD work, and uses the same existing worker.

```powershell
python scripts/validate_runtime13.py --run-native --output C:/new/runtime-case --count 18
python scripts/validate_geometry13.py --run-native --output C:/new/geometry-case
python scripts/validate_drawings13.py --run-native --output C:/new/drawing-case
```

Runtime tests protect all pre-existing documents and close only synthetic
owned documents. Geometry tests include shared linked sources, a rotated nested
assembly, an isolated copy, a 35-degree frame change, save/reopen and known
collision/separation cases. Drawing tests use an independent native projection
oracle, an editable coordinate dimension, copied layout resources and unchanged
texts/stamp. Assertions preserve partial results on failure.

Unit tests validate contracts and failure handling. Native acceptance validates
only its measured cases. Neither establishes manufacturing readiness. For sheet
metal, validate formed/flat geometry, bend rules and the actual cutting workflow
before releasing a DXF for fabrication.
