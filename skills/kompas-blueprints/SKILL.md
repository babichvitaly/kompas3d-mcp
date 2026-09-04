---
name: kompas-blueprints
description: Reconstruct editable КОМПАС-3D engineering models from dimensioned blueprints, scanned drawings, PDF sheets, orthographic views, or reference photos. Use for drawing-to-solid interpretation and checking a KOMPAS model against its source, including Russian technical drawings.
---

# Blueprint to native KOMPAS model

Use the `kompas3d` MCP tools to view source pages and construct native geometry.
The server renders images; you read the dimensions and reason across views.
Do not present it as automatic OCR, an image-to-CAD neural model, or a guarantee
that an underdefined drawing uniquely determines a solid.

## Read the source before building

Call `blueprint_view` for the whole image or each relevant PDF page (1-based).
Crop crowded dimension labels with normalized `[left,top,right,bottom]` rectangles.
Read the title block, units, scale, projection symbol, revisions, sections, details,
and manufacturing notes. A PDF may contain multiple different parts.

Use [drawing interpretation](references/drawing-interpretation.md) for sections,
Russian notation, ambiguous dimensions, and photographic references.
Record a compact dimension ledger as a sidecar Markdown or JSON file alongside
the eventual model. Each entry should identify the feature, value and unit,
source page/view, and whether it is explicit, derived, estimated, or unresolved.
Do not silently promote an estimated pixel measurement into an explicit dimension.

Infer the minimum solid that satisfies all views. Establish datum surfaces and
axes, reconstruct the external envelope, then identify cavities, holes, recesses,
and repeated features. Account for hidden lines and section hatching. Resolve
conflicting dimensions or a missing critical depth with the user; continue any
independent interpretation work while waiting.

## Construct and cross-check

Use `connect`, `create_part`, `create_sketch`, `extrude` / `revolve` with explicit
document IDs. Use `$kompas-modeling` when available for native feature recipes and
advanced SDK operations. These tools take mm/degrees, not drawing pixels.

Choose a feature sequence that follows the part's geometry: turned axial section,
extruded silhouette, then pockets/holes and edge treatments. For mixed shapes,
use several native features rather than tracing every line as a single contour.
Native sketches are editable but not automatically dimension-constrained.

Verify against every independent view. `inspect_model` returns bounds, volume,
body count and entity handles. `model_preview` supplies the current model view;
use documented API view controls to inspect other orientations when needed.
Compare hole centers, diameters, depths, shoulder positions, wall thickness, and
symmetry to the ledger. Verify subtractive volume for simple cuts. A matching
bounding box alone cannot prove a correct reconstruction.

Save M3D and requested exchange formats. Deliver the model path, ledger path,
source identifier, key checks, and any remaining ambiguity. If a dimension was
not available, say what you assumed and which feature it affects.
