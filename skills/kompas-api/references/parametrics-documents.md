# Parametric edits, drawings and assemblies

These are installed v25 SDK routes; specific live-verified cases are called out below. Discover
signatures and enums before calling. Preserve native document identity and user
intent; topology selections need rediscovery after a rebuild.

## Driving geometry

To constrain a sketch, retain its native drawing object references. Obtain the
additional `IDrawingObject1` interface, then call `NewConstraint()`. It returns
`IParametriticConstraint` (this exact spelling is in the SDK). Configure
`ConstraintType`, object point `Index`, `Partner`, `PartnerIndex`, and relevant
`Value`, `Variable` or `Expression`, then call `Create()`. It does not take effect
merely because NewConstraint returned a COM object.

Live verified: transfer an API5 line reference using
`KompasObject.TransferReference(reference, drawing.reference)`, cast to
`ILineSegment`, then `IDrawingObject1`. `NewConstraint()` takes no arguments.
Set ConstraintType=ksCHorizontal then Create; endpoints align. Set line.Length=30,
Update, then create ksCFixedLenght (installed spelling), which locks the current
length. Both constraints persisted on native save/reopen. Fixed-length constraints
do not use Value as a driving length. Value is for ksCDimWithVariable with the
required dimension relation; other constraint families need their own SDK semantics.

Point indices are zero-based; for arcs and circles, index 0 is the center. A
segment index is separate from a point index. Do not guess endpoint numbering.
Read `ksconstrainttypeenum.html` and the geometry-specific reference rules.
Sources: `idrawingobject1_newconstraint.html`,
`iparametriticconstraint_props.html`.

Build a minimal independent constraint set: locate a datum, constrain intended
coincidence/orientation/symmetry, then add driving dimensions. Do not fix every
primitive and call the sketch parametric. Detect conflicting or redundant
constraints and inspect solver state after creation. Verify by changing one
representative driving value and observing the intended dependent geometry,
then restore the requested value.

For model variables, inspect the existing feature/part variable collection.
API5 `ksVariableCollection.AddNewVariable(name, value, note)` is documented as
adding an external variable only for `ksFeature`/`IFeature`; do not assume all
collections support new variables. API7 `IVariable7.Expression` holds an
expression. Creating an unattached variable does not drive an operation. Trace
its link to the intended dimension/feature parameter, rebuild, and verify the
geometry. Sources: `ksvariablecollection_addnewvariable.html`,
`ksfeature_variablecollection.html`, `ivariable7_expression.html`.

Live variable edits require `document.RebuildDocument()` to evaluate the variable
table. Part.RebuildModelEx alone does not commit dependent geometry. The
`set_variable` tool handles refresh, commit and measurement. A user variable drove
extrusion depth 8→20→30, then40 after native reopen in the acceptance test.
Use returned parameter_note/display_name to identify feature parameters; numeric
values or generated vNN names alone are not reliable semantic selectors.

## Drawings and annotation

Use a native drawing document for CDW output and native fragment for FRW.
Never disguise a screenshot as an associative technical drawing. Work through
`IViewsAndLayersManager.Views` to an `IView`. Additional interfaces obtained from
that view are `IDrawingContainer` for geometry and `ISymbols2DContainer` for
linear/angular/diametral/radial dimensions, axes, leaders, tolerances and tables.
Sources: `iviewsandlayersmanager_props.html`, `idrawingcontainer.html`,
`isymbols2dcontainer.html`, `isymbols2dcontainer_props.html`.

`IViews.AddStandartViews(FileName, ProjectionName, ProjectionsTypes, X, Y, Scale,
DX, DY)` creates a standard associative view group. The unusual spelling
Standart is correct. ProjectionsTypes requires a SAFEARRAY of VT_I4 projection
enums, not an arbitrary variant array. Use a saved source model and a verified
orientation name. Source: `iviews_addstandartviews.html`.

`IView` / `IAssociationView` expose view placement and model association.
Discover documented section/detail creation rather than manually approximating
hidden geometry. Determine first/third-angle projection from source conventions.
Set sheet format, scale and title block with actual project data. Add dimensions
from feature intent, preserving diameter/radius distinction and avoiding duplicate
or contradictory annotations. Symbols are not automatically driving dimensions.

Verify native view-model association, sheet extents, section direction, line
visibility, dimension values, text legibility and title block. Rebuild after a
source-model edit if associativity is part of the deliverable. PDF output requires
visual inspection; successful file creation does not establish usable drawing
layout. Specifications have separate native interfaces: inspect
`IKompasDocument.SpecificationDescriptions`, `ISpecification3D`, and related SDK
collections rather than treating a plain text table as an associative BOM.

## Assemblies

Create or open a native A3D assembly and identify its API7 document and `IPart7`
root. Insert known saved component files using the installed insertion signature;
inspect the returned components and their placement. Do not simulate an assembly
by placing disconnected solids inside a part document.

`IKompasDocument3D1.MateConstraints` exposes `IMateConstraints3D`.
`Add(MateConstraintType)` returns `IMateConstraint3D`. Configure `BaseObject1`,
`BaseObject2`, `Alignment`, `ParamValue` and related type-specific parameters;
inspect inherited update and solve behavior before using it. `Fixed` has its own
SDK meaning and is not a substitute for a correctly chosen grounded component.
Sources: `ikompasdocument3d1_mateconstraints.html`,
`imateconstraints3d_add.html`, `imateconstraint3d_propers.html`.

Identify mating topology within the intended component occurrence, not just its
source file. Multiple occurrences share source geometry but have different
assembly transforms. Prefer functional planes/axes to transient edges. Check
remaining degrees of freedom against intended mechanism motion. A movable hinge
should not be fully locked merely to make a solver happy.

Verify occurrence count, source links, transforms, mate validity, clearance and
interference where relevant. Save source parts and assembly consistently so it
reopens without unresolved references. For variants, discover
`IEmbodimentsManager` and inspect the active embodiment before editing; never
assume a change applies only to the visible variant.

