# Linked drawing evidence: positions, writeback and dimension endpoints

This checkpoint provides offline rules and synthetic receipt regressions. It does
not execute CAD, change installed clients or weaken existing native gates.
`assess_linked_drawing` returns `consistent_offline_evidence` only for a complete
consistent receipt, always with `native_acceptance='pending'`. It does not certify
that the native observations happened. The exclusive native owner must produce
and independently verify those observations on owned copies.

## Saved position text is the text oracle

A position can retain `?` in live memory after save and specification Rebuild.
`partPropertyByKey` may resolve only after reading the saved specification and
then reopening the saved drawing read-only. Consequently the live text is not a
failure gate. Live and saved native UUID, specification-object UUID, property key,
validity and pinned semantic getter/metadata digest must still match the expected
position. Update's boolean return is recorded without deciding success by itself.

Each of two distinct saved RO cycles must record `read_saved_specification` before
`read_saved_drawing`, and report the exact expected resolved text. Unresolved `?`,
missing positions or a changed UUID/metadata fail even if Update returned True.
The schema requires nonempty expected positions and dimensions; it has no fixed
product-specific counts or engineering values.

## Seal after all writeback, then verify read-only stability

Transmit from an owned specification may change an owned drawing's serialized
bytes while its live Changed getter remains false. `Changed=False` is never an
on-disk hash or a promise that writing has finished. The normalized phase order is:

```text
save_specification -> rebuild_specification -> transmit -> writeback_complete -> seal
```

Sealed hashes must cover exactly the explicit unique owned-file set. Earlier
writeback hashes may differ. Both RO cycles compare their observed file hashes
after the cycle against that final seal. Originals are disjoint from the owned
set and must retain their independently pinned hashes. The function compares
supplied snapshots without reading or writing files; timestamps/event truth and
writeback completeness are the collector's responsibility. It does not initiate
Transmit, SaveAs, reopen or any retry.

## Typed 2D identity

`model_identity.drawing_reference(k, obj, expected_reference=None)` casts to
`IDrawingObject` before reading Reference. A generated `IPositionLeader` wrapper
need not expose Reference. The helper has no dynamic Dispatch fallback; cast or
identity failure propagates. It does not confer document ownership or mutate an
object. Read native UUID separately when stable saved identity is required.

## Preserve valid geometry and separately look up exact UUIDs

Inherited Geometry collections can contain invalid/generated references that vary
across sessions. Raw numeric references and enumeration order are not persistence
identities. The oracle compares all **valid** rows by native UUID and geometry
digest, rejecting empty/ambiguous valid sets. Invalid rows can disappear or vary.
A valid generated row is still checked; `generated=True` never exempts valid
geometry from preservation. Missing/changed valid UUID or curve digest fails.

For each selected endpoint, exact native lookup must return the requested UUID
and that UUID must belong to the preserved valid geometry. A retained geometry
fingerprint alone cannot substitute for that independent lookup observation.

## Honest canonical-view trace, no invented part UUID

An anchor can claim only `scope='canonical_view'`, with the exact pinned source,
source SHA, projection matrix and stable owner-view identity. It may not claim a
part UUID: `part_uuid` must be null. The recorded point must be reported on the
curve, and the target must satisfy all native predicates:

- Valid and not Temp;
- IsInAssociationView and IsVisibleInAssociationView;
- IsCurve and IsGeometryObject;
- exact UUID lookup and ownership by the expected canonical view.

These are evidence predicates, not permission to fabricate a component mapping.
The collector must use proper typed interfaces and real geometric getters to
establish point membership. Matrix validation reuses the existing proper 4x4
rotation contract. The oracle cannot infer a primitive or part identity from a
view, match a point geometrically from a digest alone, or evaluate actual COM.

## Both dimension endpoints need direct saved constraints

Each dimension's exact native UUID must have exactly one `first` and one `second`
endpoint, with valid **direct** constraints onto qualifying actual associative
geometry in both saved RO observations. Coordinates, a dimension label/value,
a whole-view relation, or an indirect chain alone do not establish this contract.
The expected endpoint bindings and canonical trace must persist exactly.

No automatic `AssociationObjects(MainTopPart)` query is introduced. Receipt mode
is `not_called` with zero attempts or an explicit occurrence with exactly one
attempt. A root query or blind retry is rejected. A native server error must be
reconciled by the owner rather than retried automatically. Existing component
anchor tools are not silently redirected to a root query or used as canonical
part-UUID proof.

## Input and limitations

Input schema: `LinkedEvidence.model_json_schema()`. Synthetic examples live only
in `tests/test_linked_drawing_oracles.py`. The metadata digest represents a pinned
native semantic getter set whose composition the collector must document; merely
matching an opaque caller-provided digest is not independent verification.
`raw_reference` is diagnostic text and never compared as saved identity.

Dynamic renumbering, following of leader tips after geometry changes, and full
CAD-package portability remain unproved. The success receipt reports all three
as false. This bounded contract compares existing saved observations; integration
and native acceptance require fresh process/document discovery and explicit
coordination of exclusive CAD ownership. A historical report of zero open
documents does not establish present runtime state.
