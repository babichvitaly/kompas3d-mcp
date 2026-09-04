# Tested feature recipes

All values below are mm. Tool responses supply IDs; substitute the actual IDs, never example labels.

## Plate with a hole

`create_part(name="Mounting plate")`, then `create_sketch(document_id=..., spec=...)`:

```json
{
  "name": "80 x 50 outline",
  "plane": "XY",
  "curves": [{"kind":"polyline","points":[[0,0],[80,0],[80,50],[0,50]]}]
}
```

Pass the sketch ID to `extrude` with `depth=8`, `name="Plate thickness"`.
Create another XY sketch with a circle centered at `[20,25]`, `radius=5`.
Extrude it with `operation="cut"`, `depth=8`, `reverse=false`, `name="Through hole Ø10"`.

Expected bounds: `[0,0,0]` to `[80,50,8]`. Expected volume:
`80*50*8 - pi*5*5*8 = 31371.681469282 mm³`. Expect one body.
For a blind pocket from the top, sketch at `offset=8`, then cut with `reverse=true` and depth less than 8.

## Sleeve without a separate cut

Make two concentric circles, radii 15 and 10, on XY. Extrude 40.
Expected bounds: `[-15,-15,0]` to `[15,15,40]`.
Expected volume: `pi*(15²-10²)*40`. This preserves both diameters in one profile.

## Turned cylinder or stepped shaft

Use `revolve` for an axial section, especially when shoulders and grooves will follow:

```json
{
  "name": "Axial section",
  "plane": "XY",
  "curves": [
    {"kind":"polyline","points":[[0,0],[10,0],[10,30],[0,30]]},
    {"kind":"polyline","points":[[0,-5],[0,35]],"closed":false,"construction":true}
  ]
}
```

Revolve 360°. Axis is the sketch Y axis. Expected world bounds are
`[-10,0,-10]` to `[10,30,10]`, volume `pi*10²*30`.
For shoulders, change the radial profile at the specified axial stations.
For a sleeve, keep the inner edge at a positive radius rather than on the axis.

## Slots and curved outlines

Use tangent arcs and straight segments with exactly coincident endpoints.
An arc has `center`, `radius`, `start_angle`, `end_angle` in degrees and
`counterclockwise`. An arc alone is open, so include closing geometry.
For a capsule slot along X, use two semicircles about the end centers and two
tangent horizontal lines. Check the overall length includes both end radii.

## Pattern coordinates

For equally spaced holes on a bolt circle: center_i = datum +
`[R*cos(theta0 + i*360/n), R*sin(theta0 + i*360/n)]`.
Use a single sketch of circles when the count is small. For a user-editable
feature pattern, use the SDK pattern interface and explicit count/spacing.
Do not guess whether a specified PCD is a radius: PCD is a diameter.
