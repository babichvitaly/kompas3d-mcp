# Capability coverage and evidence

Revision 13 adds runtime diagnostics, document batching, dependency copying,
native sketch frames, explicit collision fixtures, connected-body diagnostics,
existing-view rebinding and PDF/DXF export. See [workflows-13.md](workflows-13.md)
for scope, failure behavior and opt-in synthetic acceptance scripts. The current
server registers 60 tools; historical counts below describe their dated runs.
Tool count is not engineering or manufacturing coverage.

The bounded audit/resource work is documented in [model-audit.md](model-audit.md).
`validate_audit.py` live-verifies a known collision volume, separation, a rotated
nested occurrence, temporary diagnostic cleanup, and 20 lifecycle cycles. It does
not establish BRep tolerance accuracy or invariant nested collision selection.

This inventory distinguishes automation reach from demonstrated reliability.

`place_components` validates rigid row-vector matrices, stale expected poses,
copy isolation, source paths, fixed flags and all unselected immediate placements.
The local v25 route changes the owned API5 placement with `InitByMatrix3D`;
`UpdatePlacement` returned false in the observed run. That raw return is preserved,
not represented as native success. Exact matrix readback, independent native
save/reopen, transformed solid bounds and scoped collision checks confirmed the
tested copied assemblies. The tool itself does not save and returns
`persistence_verified=false`. This is not arbitrary mate solving or proof of
clearance through a moving latch/tool/cable sweep. Production evidence stays
outside this public repository.

### Copy-scoped sketch work, 2026-10-21

`scripts/validate_sketches.py` live-verified a four-circle grid, a rounded profile,
a bent profile, and horizontal/vertical semicircular slots on v25 Home. Every
original line/circle/arc was compared after native save/reopen. A diameter edit
10→12→10 mm produced the analytic 33π mm³ volume delta. A slot width edit
12→14→12 mm produced 3(16+13π) mm³ and restored the original geometry.
Cached feature flags and native sketch state were checked separately;
full solver acceptance was true in the final run.
Orthogonal semicircular caps use center alignment to a distinct incident primitive;
an independent radius dimension at the minimum chord radius was rejected by the
native solver and is not used.
`inspect_sketches` reads exported native FRW snapshots, keeping the original
sketch state unchanged. Entering/exiting source edit mode, including read-only
BeginEditEx, had reset state 1→2 and is deliberately not the inspection route.

`constrain_sketch` implements a coordinate-based plan for initially unconstrained
lines/circles/arcs. It does not infer tangency or manufacturing design intent.
Non-orthogonal profiles can require an explicit alternative: an irrational
hexagon offset drifted by about 0.000004 mm and was correctly rejected by the
0.000001 mm primitive comparison. This is not full arbitrary-sketch solver coverage.
`rebind_component_sources` implements copy-scoped immediate path rebinding and
checks all immediate matrices. A local multi-file assembly acceptance compared
329 occurrence matrices; source files and private geometry remain outside this
public repository. This does not establish replacement by a geometrically different
assembly: nested loaded geometry, persistent occurrence identity and own
specification-row UUIDs are not checked, and the current helper ignores the
component Update return value. Mates and mechanism edits remain unverified.
See [assembly-component-replacement.md](assembly-component-replacement.md) for
the documented setter/update candidate and the separate native acceptance gate.
The later [synthetic model-SP investigation](native-specification-reference.md)
verified persisted UUID/singleton membership and actual properties after direct
replacement, with explicit subassembly writeback and a hidden-position change.
Same-singleton Geometry reassignment added parent membership and was rejected.
This does not establish general production stale-text refresh or full payload preservation.
A separate [API5 existing-row text-authoring milestone](api5-existing-specification-text.md)
was executed by the CAD owner and its retained receipt reviewed offline: explicit
GetSpecification/description context, numeric object mapping, Edit/Set/End, and two
SavedRO checks preserved UUIDs, exact links, positions and non-target payload.
This is a scoped native text-editing result, not a shipped adapter or general properties resync.
The subsequent [synthetic literal-text controls](native-specification-text.md)
were rejected before Save: editing a hidden duplicate changed its print flags;
editing a unique row changed occurrence properties and FromSource. An opt-in
single-row helper and 23 offline guard tests preserve these failures; no native
text-only acceptance or installed MCP integration is claimed for that helper.
A later [saved stale-name fixture and property-source refresh](native-stale-specification-refresh.md)
passed: source properties4/5 were independently current with FromSource=True,
SP name remained old through two baseline reopenings, and a single property5
VT_EMPTY reset refreshed it while preserving UUID/membership/positions/grouping/
inheritance through two result reopenings. Native A/B summary quantities remained
2 and 1. The display Name cache was explicitly corrected; sources stayed unchanged
during refresh. This is one plain name cell/style1 case, not a general resync tool.
There is no defensible percentage for "almost all KOMPAS" without a defined
workflow set and edition-specific acceptance tests. Tool count is not coverage:
a general SDK tool can reach many operations, but reach alone does not validate
their geometry, usability or recovery behavior.

## Evidence levels

- **Live verified:** executed against installed KOMPAS with saved/reopened native
  output and meaningful geometry checks. Existing acceptance evidence is under
  `artifacts/acceptance-2c586cfd`; read the acceptance script for actual assertions.
  Expanded suite evidence is listed below. Each claim is scoped to its tested case.
- **Implemented:** a dedicated tool or general execution mechanism exists. Unit
  tests establish transport/validation behavior, not CAD correctness.
- **SDK documented:** installed v25 SDK exposes a plausible Automation interface;
  member names/routes have been inspected. No successful live execution implied.
- **Unestablished:** no verified route or acceptance evidence currently recorded.

## Workflow inventory

| Area | Current evidence | SDK entry points / next acceptance case |
|---|---|---|
| Native part, basic sketch, add/cut extrusion, revolution | Live verified in original acceptance suite | Reopen editable M3D; verify feature tree, dimensions, material volume |
| Measurements, preview, save and export | Live verified for original acceptance outputs | Do not extrapolate to all file formats or document types |
| Fillet/chamfer, topology discovery and feature editing | Live verified: solid-only edge discovery, four-edge fillet/chamfer, radius edit, suppress/restore, native persistence | `validate_advanced.py`; complex edge networks remain case-dependent |
| Holes and threads | SDK documented | `IModelContainer.Holes3D`, `IHole3D`, `IHoleDisposal`; distinguish thread annotation from helical solid |
| Shell, ribs and draft | Open inward shell live verified; ribs/draft SDK documented | `validate_advanced.py`; ribs and draft still need live cases |
| Loft and sweep | Two-section conical loft and straight sweep live verified, saved/reopened | Complex guide curves and cut variants remain unverified |
| Rectangular/circular patterns and mirrors | Linear seed pattern plus feature mirror live verified, six holes and persistence | `validate_patterns.py`; circular/curve patterns SDK documented only |
| Multibody Boolean and body transforms | SDK documented at container level | `IModelContainer.Booleans`, `BodyRepositions`; validate operand identity, body count and material volume |
| Direct face manipulation | SDK documented | `ISurfaceContainer.FaceMovers`, `FaceRemovers`, `FaceResizers`, `FaceReplacers`; typed SAFEARRAY arguments and healed topology |
| Surface modeling | SDK documented at container level | `ISurfaceContainer` loft/sweep/NURBS/trim/sew/offset/patch collections; boundary and closure checks |
| Sheet metal and unfolding | Native sheet plate thickness 2→3 mm and persistence live verified; bends/unfolding unverified | `validate_sheet_metal.py`; formed/flat states, relief and bend rules need further cases |
| Sketch constraints and driving variables | Horizontal/fixed-length constraints and parameter-driven extrusion edits live verified, persisted | `validate_constraints.py`, `validate_parameters.py`; full solver constraint set unverified |
| Assembly documents, insertion and placements | Native A3D lifecycle, linked insertion and source-part update after reopen live verified for one synthetic plate; placement unverified | `validate_linked_assembly.py` verifies the actual external source, volume, mass and original-file preservation; `validate_documents.py` attempted UpdatePlacement unsuccessfully |
| Assembly mates and mechanisms | SDK documented | `IKompasDocument3D1.MateConstraints`, `IMateConstraint3D`; verify intended degrees of freedom |
| Native drawings/fragments and geometric primitives | Six native document kinds, line/circle/text and measured linear dimension live verified and persisted | `validate_documents.py`; broader annotation styles remain SDK routes |
| Associative model views and annotations | Exact front/top/left projection and thickness 8→12→16→12 mm live verified with a revision-source rebind, geometry checks and save/reopen; repeated edits at the same source path can leave stale views | `validate_associative_drawing.py`; generic dimensions use explicit coordinates. The acceptance case adds an explicit native constraint to the projected edge |
| Specifications/BOM, variants | SDK entry points identified, workflows unverified | `ISpecification3D`, `SpecificationDescriptions`, `IEmbodimentsManager`; document linkage and variant isolation |
| Material and density | SetMaterial plus mass readback live checked on a cylinder | High-level set_material; not material-library certification |
| Libraries, routing, welding, simulation and third-party add-ins | Unestablished as complete workflows | Need installed subsystem, license and Automation evidence |
| Arbitrary existing/imported models | General API route only | Missing history, topology changes and unsupported imported surfaces need per-file validation |

The installed SDK routes and exact topic filenames are maintained in
`skills/kompas-api/references/modeling-operations.md` and
`skills/kompas-api/references/parametrics-documents.md`. These are actionable
starting points, not claims that the corresponding operations were executed.

## Recorded local acceptance evidence

These paths identify the maintainer's local validation runs; generated reports
and CAD files are excluded from the public repository. Run the corresponding
`scripts/validate_*.py` scripts to generate your own evidence under `artifacts/`.

Tested on KOMPAS-3D v25 Home, Python 3.12, installed v25 SDK:

| Evidence folder/file | Result |
|---|---|
| `artifacts/advanced-04e3d35b/report.json` | Fillet/chamfer, edit/suppression, shell, loft, native reopen, API7 cast and checked batch failure |
| `artifacts/documents-3c91ffd6/report.json` | Six document kinds, assembly insertion, views and native drawing objects/dimension persistence |
| `artifacts/parameters-8093a086/report.json` | Extrusion depth 8→20→30, then 40 after reopen via user variable |
| `artifacts/sheet-metal-f46392be/report.json` | Sheet thickness 2→3, volume 4800→7200, reopen |
| `artifacts/patterns-b04f14e7/report.json` | Linear pattern and mirror: three/six holes, one body, reopen |
| `artifacts/constraints-fd844bff/report.json` | Native horizontal/fixed-length constraints persisted, length 30 |
| `artifacts/sweep-cf3b108b.m3d` | Straight 30 mm sweep, radius 2, analytic volume checked before/after reopen |

API discovery exposes 1,119 installed API5/API7 interface wrappers. This count is
an inventory, not 1,119 verified workflows. The 41 MCP tools include general
definition configuration, interface casting and typed dependent batches so SDK
operations can be attempted without adding one wrapper per button.

## Fork validation on 2026-10-09–10

The following results are from KOMPAS-3D 25.0.0.2735 in Windows 11 ARM under
Parallels Desktop, using Python 3.12 x64 and the installed v25 SDK. They establish
behavior for synthetic plate examples, not arbitrary existing assemblies or
drawings. Local artifact paths below are relative to the Windows repository.

### Exact projection and the empty-view failure

On this installation `AddStandartViews` inherited
`IAssociationView.UseOcclusion=True`, which the SDK calls draft projection.
Creation and rebuild returned success, and the views reported `Valid=True`,
but each view contained zero objects. A successful BOOL and three collection
entries therefore did not establish a usable drawing.

`create_standard_views` now defaults to `draft_projection=False`. It identifies
only newly created views by native `Reference`, sets their projection mode,
then calls `Update()` and `Rebuild()` in collection order. It requires the
requested number of new views, the requested mode, valid views and a nonzero
`ObjectCount`. Errors include partial-view diagnostics and leave those views
available for inspection. Existing views are not reconfigured. The returned
handles and object counts enable subsequent geometry checks; a nonzero count
alone still does not prove the intended projection.

The real stdio MCP check discovered 41 tools and created three exact views,
each with four projected edges. Source-edit validation additionally checked the
actual `SourceFileName`, line endpoints and extents, rather than only view count:
the 80×50 mm front view remained fixed, the top view changed from 80×8 to 80×12 mm,
and the left view from 8×50 to 12×50 mm. Model volume changed from 32,000 to
48,000 mm³. These states were verified after native save/reopen. The test's
explicitly constrained thickness dimension followed 8→12 mm and persisted.

The full 8→12→16→12 mm acceptance passed in
`artifacts/associative-drawing-ccbfb52e/report.json`, produced by
`scripts/validate_associative_drawing.py`. After the first edit to 12 mm, each
subsequent edit starts by copying the current saved M3D byte-for-byte to a new
revision path **before changing its parameter**. The new revision is edited,
saved/reopened and measured; the preceding file stays unchanged. The test then
sets `SourceFileName` on all three existing views and calls `Update()` on each,
followed by rebuilding all views and the drawing. The same views and explicitly
associated dimension followed 16 mm and then 12 mm, including save/reopen at both
steps. The final dimension had valid endpoint constraints referring to actual
projected edges after reopen. Model geometry, view geometry and source links were
rechecked. SHA-256 checks confirmed that the original plate, the saved 12 mm
baseline and both completed revisions were not changed by subsequent operations.
The resulting CDW depends on the final revision M3D; keep that source with the
drawing and retain preceding revisions as history.

This verifies the revision-source workflow on the synthetic plate. Repeated
in-place source updates remain a known limitation on this installation: the
third edit in the 8→12→16→12 mm sequence left the existing projections at 16 mm
despite the saved source measuring 12 mm and successful rebuild returns.
The same failure occurred without a dimension, excluding the test's dimension
constraint as its cause. Do not infer that the revision workaround fixes native
same-path refresh, or that it safely redirects dependencies in arbitrary user
assemblies and drawings.

`TreeNeedRebuild` and `IPart7.NeedRebuild` are automatic-update policy properties,
not dirty/error indicators. Do not use their Boolean values as rebuild success
criteria; inspect the resulting native geometry and references.

### Linked assembly update

`artifacts/linked-assembly-b4aad7b0/report.json` passed
`scripts/validate_linked_assembly.py`. A one-component A3D referenced a copied
80×50×8 mm plate. Changing that source to 12 mm and rebuilding the open assembly
updated its volume from 32,000 to 48,000 mm³ and mass from 0.2512 to 0.3768 kg
at the test density of 7.85 g/cm³. After save/reopen the component remained valid
and externally linked to the intended working copy, with the updated measurements.
The source variable persisted and the original plate's SHA-256 was unchanged.
This case does not validate placements, mates or dependency copying for a
pre-existing multi-file assembly.

The 26 unit tests passed on Windows and macOS, including 10 new wrapper-contract
cases for empty/invalid views, partial mutations, projection mode, collection
reordering and MCP argument forwarding. These tests complement the live results;
they do not establish CAD geometry.

## Acceptance rules for promoting coverage

For each operation family, exercise creation plus one representative edit. Check
the native result using appropriate invariants (solid volume/body count, surface
boundaries, sheet-metal thickness, assembly placement, or drawing association).
Save and reopen when persistence matters. Record the KOMPAS version/edition and
output artifacts. Test a meaningful failure or invalid selection where it guards
against corrupted or unintended results. A mocked COM response does not promote
a workflow to live verified.

Do not silently use mesh approximations for native parametric deliverables, report
an annotated thread as physical helical geometry, or count unsupported library
commands as available merely because unrestricted COM invocation exists.
# Runtime 14 development additions

`inspect_drawing_view_state`, `compare_drawing_view_state` and
`find_visible_view_anchor` have typed validation and synthetic regression checks.
Their presence in an installed MCP schema is checked without starting CAD.
New live view geometry/visibility acceptance is not claimed. Existing native
runtime-13 evidence below keeps its original scope.

The dev4 candidate checks `IViews.ActiveView` identity before state/geometry
inspection, after each inspection and after association enumeration. A pending
`Current=True` flag is insufficient and can expose a zero scale getter. Its new
synthetic regression cases and installed-candidate native checks must be run
before this guard is accepted; presence in source is not a passing test result.

Persistent job results, CLI terminal verification and offline project staging
are covered by unit/filesystem tests. Windows metadata regression compares
`stat` and `fstat` within separate channels, retaining device/inode binding and
SHA verification. `files_staged_not_rebound` is not native-link isolation.
Package installation/schema smoke does not certify portable project relocation.

## Offline existing-leader anchor contract (2026-11-23)

`leader_anchors` and `native_returns` add synthetic/stateful regression coverage
for exact semantic ownership before nearest-curve selection, special-root query
exclusion, bounded/deduplicated inserted-occurrence traversal, typed existing
leader mutation, method-specific Automation returns and protected view/print
state. Saved evidence requires two fresh RO cycles with exact current owner and
base, allowing regenerated projection references and an empty constraint Partner.
No installed adapter, native dynamics, PDF, performance or additional live CAD
coverage is claimed. See [contract and native acceptance plan](existing-leader-anchors.md).

The separate `root_projection` offline evaluator checks whole-product view scope,
complete bounded typed inventories, current source/root/view provenance and
explicit material classification. It retains arc sweeps and makes no component
membership or speed claim. No native fast path is installed or enabled; see
[applicability and native comparison plan](whole-root-projection.md).

Signed DrawingObjectParamType contracts now use the documented -1/-2/-7 enums.
The pure `leader_motion` diagnostics reject valid-base/type12 counterexamples
where real material motion is not followed, account for view recentering, and
resolve a canonical typed position field through direct native lookup rather
than first-field order. These are reported-evidence checks, not native following
acceptance. See [dynamics research](leader-anchor-dynamics-research.md).

Subsequent external native receipts are negative for view Rebuild, complete
document rebuild and ordinary 2D document rebuild with polling. A separate
PointOnCurve attempt failed at Create before displacement; its unfinished
receipt does not establish cleanup or restoration. This records a scoped native
limitation, not passing SDK integration or a universal diagnosis.

After explicit CAD handover, a separate native v25 synthetic plate/assembly/one
PositionLeader experiment compared same-filename updates against source bytecopy
to a unique revision before editing. Both produced real projected-material motion
without tip following, immediately and through two saved RO cycles. Exact valid
base/type12 persisted. Sheet/view coordinate witnesses agreed; untouched part and
prior unique source revisions were hash-checked. Independent final discovery
confirmed the five protected RO documents unchanged and no synthetic documents
left open. This closes the unique-revision candidate negatively for this fixture;
it does not establish a general cause, SP-field integration or passing dynamics.
See [native evidence and restoration limits](native-leader-source-revisions.md).
