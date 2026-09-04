# Broad tool workflows

The MCP has specialized tools for common tasks and two general native mechanisms:
`create_feature` / `update_feature` for API5 definitions, and `api_cast` / `api_batch`
for API7 interfaces. Generic access does not eliminate SDK-specific prerequisites.

## Native model features

`create_feature` arguments are document_id, entity_type (installed `o3d_` constant),
name and settings. References are `{"entity_id":"returned-id"}` within the same
document, `{"handle":"id"}` for COM objects, or `{"constant":"enum-name"}`.
Call `api_describe_interface` on the definition interface before configuring it.

An open shell (`entity_type="o3d_shellOperation"`) uses:

```json
{
  "properties": {"thickness": 2, "thinType": true},
  "calls": [{"via":["FaceArray"],"member":"Add","arguments":[{"entity_id":"top-face-id"}]}]
}
```

Select the removed face using `list_entities(kind="o3d_face")` geometric bounds
and area. Here `thinType=true` offsets inward. Live tested on an 80×50×8 plate:
remaining volume `32000 - 76*46*6`.

A loft (`o3d_bossLoft`) uses `SetLoftParam(false,false,true)` followed by
`via=["Sketchs"], member="Add"` for each ordered section entity. The installed
wrapper spells this **Sketchs**, despite the English help label. A two-circle
loft from radius10 to radius5 over30mm was verified as a conical frustum.

A sweep (`o3d_bossEvolution`) uses `properties={"sketchShiftType":1}`,
`SetSketch(section)`, and `via=["PathPartArray"], member="Add"` with the path sketch.
A straight30mm XY path along X and a radius2 section on YZ produced the expected
cylinder volume `pi*4*30`; saved/reopened successfully.

A linear pattern (`o3d_meshCopy`) uses `count1=3,count2=1,step1=20,step2=10,
factor1=false,factor2=false,angle1=0,angle2=90,insideFlag=true,geomArray=false`,
then `via=["OperationArray"],member="Add"` with its seed feature. Count includes
the seed. For a mirror (`o3d_mirrorOperation`), call `SetPlane(plane)` and add seed
operations via **GetOperationArray**. A three-hole pattern mirrored across XOZ
was verified as six holes with expected material removal and native persistence.

Use `update_feature` to change a definition, `set_entity_state` to suppress/restore,
and `delete_feature` only for a selected operation. The deletion tool rejects
face/edge/vertex deletion because API5 would delete the entire owning feature.
Do not reuse edge IDs after rebuilding; rediscover geometric selections.

## Checked API7 batches

Get top_part from `create_document`, `open_document`, or `list_documents`.
Cast it with `api_cast(interface="IModelContainer")`, then use the returned handle:

```json
{
  "steps": [
    {"id":"collection","target":{"handle":"container-id"},"member":"Fillets","action":"get","expect":"not_null"},
    {"id":"count","target":{"ref":"collection"},"member":"Count","action":"get"}
  ]
}
```

Each step has a unique id. `ref` refers only to a prior result. `expect="truthy"`
checks BOOL mutations; `not_null` checks object creation. Void-returning calls
need `expect="any"` plus subsequent readback. On failure the response includes
completed=false, failed_step and prior results; prior edits remain. Do not replay blindly.

Arrays with exact COM element types use:

```json
{"variant":{"type":"dispatch_array","values":[{"handle":"face-id"}]}}
```

Supported types: dispatch_array, int_array, double_array, variant_array. Direct
face methods may require dispatch arrays; standard view projection lists require
int arrays. API7 surfaces and sheet metal require casting IPart7 to
ISurfaceContainer or ISheetMetalContainer respectively.

## Parametrics and documents

Use `list_variables(feature_id=...)` to identify driving parameters from actual
names/notes and values, then `set_variable(value=...)` or `expression=...`.
Create a user variable at part scope with create=true. Changes commit with a full
document rebuild and return measurements. Discover generated feature-variable names
per model; do not reuse the names from an unrelated example.

Use `create_document(kind="drawing")`, `create_standard_views` for associative
projections, and drawing primitives/text/dimension tools for editable annotation.
Dimensions created from coordinates are measured native dimensions; these tools
do not claim automatic associative binding to particular model edges.

For assemblies, create an assembly document and `insert_component` with a saved
native part path. This returns component/placement handles. Placement/mates still
need documented SDK operations and verification. Insertion is verified; complete
mate-driven mechanism workflows are not yet verified.

All six native document kinds use `save_document` / `close_document` with API7
handles. A model document also returns document_id for API5 tools. Keep handles
and document IDs distinct. Closing refuses unsaved changes unless discard_changes=true.
