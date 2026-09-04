# Interpreting engineering sources

## Evidence hierarchy

Explicit dimension and manufacturing note > consistent derived dimension >
geometry inferred across views > scaled pixel estimate. A scale in the title
block describes the drawing, not necessarily a resized scan. Never override an
explicit number because the picture looks slightly different.

Cross-check the projection symbol and alignment of corresponding features;
do not assume first-angle or third-angle solely from the language or country.
A section shows cut material with hatching. Unhatched regions can be bores,
cavities, or excluded components, depending on conventions. A hidden line is
evidence of a feature, not a surface to extrude.

## Russian drawing vocabulary

| Mark or term | Modeling interpretation |
| --- | --- |
| Ø / ⌀ | Diameter; radius is half the stated value |
| R | Radius of the indicated arc or fillet |
| отв. / отверстие | Hole; check number, depth, and whether through |
| сквозное / насквозь | Through feature |
| глухое | Blind feature; requires depth |
| фаска | Chamfer; read length/angle convention from the callout |
| скругление | Fillet/round |
| разрез / сечение | Section view / cross-section |
| вид А / местный вид | Named view / local view |
| паз / проточка | Slot / groove or undercut |
| резьба | Thread; preserve designation, pitch, hand, and engagement length |
| соосно / симметрично | Coaxial / symmetric |

Keep decimal comma interpretation consistent (`12,5` is 12.5 in Russian
dimension text). Check whether a leading symbol is Ø, zero, or a scan artifact.
For `4 отв. Ø6`, make four holes of diameter 6, not a 4 mm deep feature.
For `2×45°`, confirm the leader indicates a chamfer rather than two occurrences.
Do not derive a thread standard's minor diameter from memory: consult the
specified standard or SDK/library data. Use cosmetic thread representation when
appropriate; actual helical geometry is a separate modeling choice.

## Ambiguity handling

Overall and chained dimensions can conflict due to tolerances or transcription.
Record the conflict rather than averaging it. A tolerance controls allowable
variation; nominal geometry usually uses the nominal value unless the user asks
for a limit condition. Dimensioning to a theoretical sharp corner is not the same
as dimensioning to the fillet tangency point.

For a missing dimension, determine whether symmetry or another view constrains
it. Ask for clarification when it affects wall thickness, mating fit, hole depth,
or the topology of the object. For a visual concept only, choose a dimension and
record it as estimated. Do not add mechanical details merely because they are
common on similar parts.

## Photos and perspective images

A single photograph does not determine exact 3D geometry or scale. Ask for one
known size if absolute scale matters. Perspective foreshortening invalidates a
single pixels-per-mm factor across different depths. Use multiple views when
available. Label reconstructed hidden surfaces as assumptions. Do not claim a
manufacturing-ready reconstruction from an uncalibrated photograph alone.

## Ledger example

| Feature | Nominal mm | Evidence | Status |
| --- | --- | --- | --- |
| Plate length | 80 | Sheet 1, plan view | Explicit |
| Thickness | 8 | Sheet 1, side view | Explicit |
| Bore diameter | 10 | Sheet 1, Ø10 leader | Explicit |
| Bore depth | 8 | Through note and plate thickness | Derived |
| Unspecified edge break | None modeled | No callout | Unresolved, omitted |
