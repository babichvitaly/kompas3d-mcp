# Associative view state and visible anchors

The reusable A37 read-only contract extracts established view inspection and
comparison primitives from a production authoring recipe. It contains no product
paths, dimensions, geometry IDs or product truth tables.

- `inspect_drawing_view_state(handle, view_number)` captures a typed `ViewState`:
  source path and SHA256, right-handed orthonormal camera matrix, positive scale,
  X/Y/angle, paper bounds, object count, Unfold and a digest of actual line/circle/
  arc geometry with native visibility. It does not activate, update, rebuild or save.
- `compare_drawing_view_state(..., expected)` reinspects and reports `matches` and
  named differences. Run it after each separately performed read-only reopen.
  Geometry digest is exact; bounds/pose comparisons have small explicit tolerances.
  Native view references are outside the comparison and are never persistent IDs.
- `find_visible_view_anchor(...)` uses the explicit component's
  `IAssociationView.AssociationObjects`. It accepts only valid, non-temporary,
  visible line/circle projections whose owner is this view. The component handle
  must be scoped to an explicit clean source document matching the view's source.
  The view must already be committed Current: the caller sets Current=True and
  calls IDrawingObject.Update under its owned-copy lifecycle. Native
  IViews.ActiveView must be valid and match the view's Number and Reference;
  a pending Current=True alone is insufficient. This function does not switch it.
  The committed context is checked before state/geometry inspection, immediately
  after each state inspection, and after enumerating association candidates.
  A pending zero-scale getter is not read in place of the early context refusal.
  Capture the state after committing Current and restore/check the caller's original
  positive pose under its existing owned-copy lifecycle. Supply this current state
  fingerprint; stale plans fail. `near_point` is optional view-space XY.
  Before accepting the anchor, document identities, source `Changed`, component
  scope and Current view are checked again. Hidden/temporary/other-view or
  unsupported curve candidates are counted explicitly; native disconnection or
  invalid coordinate failures are not converted into a successful partial result.

`GetProjectionPoint` is not used as visibility proof. A hidden component fails even
when it has a mathematically valid projection coordinate. An empty supported curve
set fails, rather than accepting a positive object count or bounds alone.

Disk SHA provides provenance, not evidence that a view is regenerated from these
bytes. This API does not verify material, all 2D geometry families, local-cut
lineage, saved persistence, manufacturing correctness or physical acceptance.
Asymmetric matrix/Unfold/geometry/staleness tests are synthetic acceptance only;
a Windows native CAD acceptance case remains required before new mutation or
reduced rebuild recipes are promoted. Existing authoring recipes stay unchanged.
