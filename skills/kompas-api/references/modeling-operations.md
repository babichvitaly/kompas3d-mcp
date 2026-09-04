# Advanced modeling SDK recipes

These routes were checked against the installed KOMPAS-3D v25 SDK HTML topics.
They establish documented interfaces and members, **not successful CAD execution**.
Read the exact topics with `sdk_read`, then confirm installed COM signatures before
mutating a document. Topic names below are local SDK archive names, not web URLs.

## Shared construction and selection

API5: `ksPart.NewEntity(type)` -> `ksEntity.GetDefinition()` -> configure ->
`ksEntity.Create()`. Resolve enum names with `api_constants`; never transplant
numeric operation constants from another release. API7: get `IPart7`, cast to
`IModelContainer`, select a collection, call its documented `Add`, configure the
returned feature, then call `IModelObject.Update`. Casting is QueryInterface, not
changing a handle's label. Some returned base interfaces need another cast.

Sources: `imodelcontainer.html`, `imodelcontainer_props.html`,
`ksentity_getdefinition.html`, `isheetmetalbodies_add.html`.

Before creating a topology-dependent operation, identify faces/edges by their
surface/curve type, location, size and adjacency, scoped to the intended body.
Confirm that the selection is unique or matches the required count. Rediscover
it after rebuild. Keep seed feature references for feature patterns. Do not use
UI selection state or an index from an earlier model state as identity.

## Shell, rib and draft

- **Shell:** `ksShellDefinition.thickness`, `thinType`, and `FaceArray()`.
  FaceArray is the collection of faces to remove, not all faces to offset.
  Fill it with selected native face entities; inspect its collection insertion
  signature. Check remaining wall thickness and that openings match the request.
  Sources: `ksshelldefinition_props.html`, `ksshelldefinition_facearray.html`.
- **Rib:** `ksRibDefinition.SetSketch(sketch)`, `ThinParam()` / `SetThinParam`,
  `side`, `angle`, `index`. Read individual property meanings before setting them.
  The sketch is the rib construction profile; verify it intersects the intended
  support and that thickness develops on the intended side. Sources:
  `ksribdefinition_setsketch.html`, `ksribdefinition_props.html`,
  `ksribdefinition_methods.html`.
- **Draft:** API7 `IModelContainer.Inclines` -> `IInclines.Add()` -> `IIncline`.
  Set `Faces`, `Plane`, `Angle`, `Direction`, then update. Plane is the draft base;
  do not substitute a visual screen plane. Check section sizes at both ends to
  verify sign. Sources: `iinclines_add.html`, `iincline_propers.html`.

## Loft and sweep

- **Loft:** `ksBaseLoftDefinition`, `ksBossLoftDefinition`, or
  `ksCutLoftDefinition` according to base/add/cut intent. Installed `Sketchs()` holds the
  ordered section sketches. `SetLoftParam` configures closed trajectory and
  automatic path; read its exact parameters. `SetDirectionalLine` is available on
  the boss definition. Avoid twisting by aligning section winding and start
  points. Check intermediate sections, not only overall bounds. Sources:
  `ksbossloftdefinition_methods.html`, `ksbossloftdefinition_getloftparam.html`.
- **Sweep:** SDK calls this evolution: `ksBaseEvolutionDefinition`,
  `ksBossEvolutionDefinition`, `ksCutEvolutionDefinition`. `SetSketch` sets the
  section; `PathPartArray()` contains path curves. `sketchShiftType` is 0 for
  parallel translation, 1 for preserving the initial angle, 2 for keeping the
  section normal to the guide. Confirm profile/path connectivity and the chosen
  orientation law, then check self-intersections and end orientation. Sources:
  `ksbossevolutiondefinition_methods.html`,
  `ksbossevolutiondefinition_sketchshifttype.html`.

## Patterns and mirrors

- API5 rectangular: `ksMeshCopyDefinition.OperationArray()`, `SetAxis1/2`,
  `count1/2`, `step1/2`, `factor1/2`, `insideFlag`, `geomArray`. `factor` means full
  step versus per-instance step; read its property topic before entering spacing.
  Sources: `ksmeshcopydefinition_methods.html`, `ksmeshcopydefinition_props.html`.
- API5 circular: `ksCircularCopyDefinition`, `SetAxis`, `GetOperationArray`,
  `SetCopyParamAlongDir`. Read `kscircularcopydefinition_methods.html`; do not
  assume the rectangular collection member name is shared.
- API5 mirror: `ksMirrorCopyDefinition.SetPlane` and installed `GetOperationArray()`.
  Source: `ksmirrorcopydefinition_methods.html`.
  Some help labels use `OperationArray` or `Sketches`; installed wrapper spellings
  are authoritative. `api_describe_interface` avoids these mismatches.
- API7 common route: `IModelContainer.FeaturePatterns.Add(type)` returns
  `IFeaturePattern`; `InitialObjects` contains seeds. Cast to the actual pattern
  interface. `IMirrorPattern.Plane` and `SaveInitialObjects` govern mirrors.
  Sources: `ifeaturepatterns_add.html`, `ifeaturepattern_props.html`,
  `imirrorpattern_props.html`.

Distinguish copying operations from copying geometry or bodies. Confirm how the
API counts the seed, then check generated instance count, omitted instances,
spacing and body connectivity. Patterning a hole feature should preserve its
intent; redrawing unrelated circles loses that relationship.

## Holes, threads and Boolean operations

`IModelContainer.Holes3D` creates `IHole3D`; its extra `IHoleDisposal` interface
controls placement, and `ILocalCSObject` provides a subordinate coordinate system.
Set hole type, `Diameter`, `DepthType`, `Depth` and end-face form as documented;
`HoleParameters` supplies type-specific countersink/counterbore parameters.
`Thread` is a thread annotation interface. A thread symbol is not a modeled
helical solid. Confirm which result the user needs. Sources: `ihole3d.html`,
`ihole3d_propers.html`, `iholes3d_add.html`.

`IModelContainer.Booleans` creates `IBoolean`: choose `BooleanType`, `BaseObject`,
`ModifyObjects`, and whether copies of each operand are preserved using
`SaveCopyBaseObject` / `SaveCopyModifyObjects`. Read `Bodies` documentation before
using it as a substitute for operands. Check intersection existence and body
count/volume after union, difference or intersection. Source:
`iboolean_propers.html`.

## Direct face edits and surfaces

Cast `IPart7` to `ISurfaceContainer` (source: `isurfacecontainer.html`).

- `FaceMovers` -> `IFaceMover`: `SetFaces(Faces, TangentFaces)`, `Direction`,
  `Offset`. SetFaces requires SAFEARRAY DISPATCH, not a JSON array string.
  Source: `ifacemover_setfaces.html`.
- `FaceRemovers` -> `IFaceRemover`: `Faces`, `SaveBody`. SaveBody means preserving
  body integrity; removing a face without healing may deliberately make a surface.
  Source: `ifaceremover_props.html`.
- `FaceResizers` -> `IFaceResizer`: `Faces`, `FaceResizerType`, `CylinderDiameter`,
  `ConeAngle`, `SphereDiameter`. Choose parameters matching actual analytic face
  geometry. Source: `ifaceresizer_propers.html`.
- Surface collections include `ExtrusionSurfaces`, `RotatedSurfaces`,
  `EvolutionSurfaces`, `LoftSurfaces`, `NurbsSurfaces`, `RuledSurfaces`,
  `TrimmedSurfaces`, `SurfacePatches`, `SurfaceSewers`, `ExtensionSurfaces`,
  `EquidistantSurfaces`, `FaceReplacers`. Source: `isurfacecontainer_props.html`.

Read the collection's Add signature and result's properties for the selected
operation. A generic collection existing is not proof every geometry is valid.
Check open boundaries before sewing, and verify closed solid status before
reporting a watertight result. Surface bodies can have zero material volume.

## Sheet metal

Cast `IPart7` to `ISheetMetalContainer`. `SheetMetalBodies.Add()` produces
`ISheetMetalBody`; configure and call `IModelObject.Update`. Relevant body fields
include `Sketch`, `Profile`, `Thickness`, `ThicknessDirection`, `Radius`,
`UnfoldType`, `BendCoefficient`, `BendReduction`, `BendTablePath`, and `Straighten`.
Choose the unfolding rule from actual material/manufacturing requirements.
Do not infer a bend coefficient from thickness alone.

The container exposes bends, line bends, sketch bends, plates, cuts, holes,
flangings, closed corners, undercuts, forming, ribs, and bend/straighten operations.
Use `ConvertsToSheetMetals` for supported conversion of existing solids.
Sources: `isheetmetalcontainer.html`, `isheetmetalcontainer_props.html`,
`isheetmetalbodies_add.html`, `isheetmetalbody_props.html`.

Validate both formed and flat states, bend radius/relief, thickness continuity,
flat outline and absence of self-overlap. A collection entry called Add is not a
completed manufacturing-ready sheet-metal result.
