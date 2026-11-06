# Offline SDK guard checkpoint

These changes have unit/synthetic coverage only. Native acceptance is **pending**;
no KOMPAS/COM session was used, and no installed SDK or client configuration was
changed. Helpers below are Python worker APIs; STEP import and color reporting
are not registered as new MCP tools in this checkpoint.

## Measured plane frames

`plane_geometry.offset_for_displacement(points, displacement)` consumes three
`GetPoint3D` points: origin, local (1,0), local (0,1). It checks a rigid frame,
computes its normal and derives signed native offset/direction. In-plane
components are rejected. No plane-name lookup decides the sign.

`SketchSpec.offset` retains its existing meaning: signed distance along the native
support normal, not a world-axis coordinate. For a desired world displacement,
measure the unoffset support frame and use the helper to calculate `offset`.
`SketchSpec.expected_world_points` optionally specifies the expected **final**
three world points. Sketch creation always measures and validates its frame before
`BeginEdit`; supplying expectations also blocks a mismatched support/offset.
An empty sketch/offset plane may remain on failure; discard/reconcile the owned
copy rather than blindly retrying. This is not an atomic model transaction.

Synthetic tests cover both signs for XY (+Z), YZ (-X), XZ (+Y), an unnamed rotated
frame, degenerate/nonfinite frames and a wrong final frame. These are fixtures,
not evidence of the frame returned by a particular live installation.

## Driving variables

`constrain_sketch` refreshes native part variables, selects a free namespace and
returns it as `variable_prefix`. Repeated requested prefixes select numbered
namespaces; comparisons are case-insensitive. Each driving variable is checked
again against a refreshed inventory immediately before constraint creation.
Existing variables are never intentionally reused. Serial STA ownership remains
required. This is not a cross-process lock; partial solver failure still requires
reconciliation of the unsaved copy. Native variable enumeration and consecutive
hole operations, including save/reopen, must be accepted with CAD ownership.

## Tracked STEP import

`tracked_import.import_step(k, source, owned_root, target)` requires a new native
output path inside an explicit owned directory. It snapshots open document
references/paths/types, rejects already-open conversion paths, and accepts exactly
one new reference returned by Open with all previous documents unchanged.
Converted `.m3d`/`.a3d` path and native document kind must agree; target extension
must agree too. It then performs an explicit SaveAs and checks native path,
Changed, a nonempty file and source preservation. Ownership is granted only after
those checks. Any uncertainty raises without adopting or closing documents.

The implementation intentionally covers single-document STEP conversion only;
an import producing more documents must be reconciled manually. Caller must own
the CAD session and output directory exclusively. This does not establish body
count, geometry validity, external dependency isolation or save/reopen geometry
acceptance; those remain separate requirements.

## Color state

`color_state.color_state(IColorParam7, scope, expected_color)` preserves Color and
raw UseColor. Root undefined values (-1/None) are reported without rejecting a
valid Color; occurrence 0 is a defined state. Unknown occurrence flags are marked
unknown. Color matching is separate from effective inherited/rendered appearance;
`appearance_verified` remains false. The helper is read-only.

## Native acceptance gate

After explicit CAD handover, run only on new synthetic owned copies:

1. All six signed base-plane cases and a mismatched expected frame before editing.
2. Two consecutive hole sketches with identical requested prefix and pre-existing
   user variables; verify distinct driving variables and preserved geometry after
   save/reopen. Refresh behavior inside sketch edit remains a native check.
3. Single-body STEP to part and multi-body STEP to assembly; verify inventory,
   native kind/path, explicit SaveAs and reopen. Test reused/ambiguous documents.
4. Root undefined UseColor and occurrence 0, with saved/reopened raw state and a
   separate visual check of effective appearance.

No production models, local engineering receipts or machine-specific paths are
part of this repository checkpoint.
