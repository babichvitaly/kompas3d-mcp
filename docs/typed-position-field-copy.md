# Typed position-field copy from an exact owned RO backup

`typed_position_copy.copy_position_field_owned` implements a narrow typed-copy
step through an injected owner-side adapter. It never connects to CAD or obtains
a document on its own. The helper has exactly two native mutation calls:

```text
target_leader.Positions.Assign(backup_leader.Positions)
target_leader.Update()
```

No Str setter or getter roundtrip, numeric literal replacement, invented serialized
property-field grammar, ITextItem.Assign, COMMON Rebuild or Transmit is used. The
cached local typelib evidence lists Assign on IText/ITextLine; it does not provide
ITextItem.Assign. This code uses whole IText.Assign only, and requires True from
Assign and from the owning leader's Update. A False return/exception does not
trigger a string fallback or automatic retry.

## Preconditions and native row identity

The caller pins the exact backup path/SHA and canonical row UUID. The backup must
be owned and read-only, distinct from the writable owned target, and included in
the unchanged-file hash scope. The adapter must check actual process/STA/document
identity, ownership, paths and read-only/source state before mutation and during
readback. It must not turn a same-name document or approximate backup into a match.

Before Assign, a fresh native lookup must report that the new leader is included
in exactly the intended native row. IncludeGeometry/replacement of the old leader
must already have been performed and accepted by the owner; this helper does not
delete/create leaders or add geometry. The lookup is repeated after Update, and
the target leader UUID must remain unchanged during this copy step. The old backup
leader and new leader can have different UUIDs: the shared identity being preserved
is the native property field's canonical **row** key, not an invented equality of
the replaced leader identities.

## Full captured typed structure

Detached observations contain IText properties, ordered ITextLine properties and
ordered ITextItem properties. Native ItemType 8192 must carry a position property
field with the exact canonical key, prop=position and type=partPropertyByKey.
At least one such item must be present. A numeric literal without a native field,
an item with missing field metadata or a changed key is rejected before assignment.
Plain prefix/suffix items and their formatting are preserved too.

All captured line/item properties, cached values, ordering, counts and field
metadata must match the backup after Assign/leader.Update. Comparison is structural
JSON, not flattened display-text equality. The native adapter must capture the
complete agreed typed getter scope and document how field metadata was obtained;
an arbitrary incomplete DTO or hand-constructed field string cannot establish
native acceptance. This module has no serialized field parser or serializer.

## Source preservation and saved acceptance

The backup identity, typed backup structure and full caller-pinned untouched-file
hash map are checked before/after. The target is excluded from that map; unrelated
CDWs, specifications and source models must remain included at the owner's chosen
complete scope. No fixed number of files or product parameters is built in.

The in-memory result is `typed_copy_verified_in_adapter`, saved=False and native
acceptance pending. It does not save or export anything. A later explicit saved
oracle, `assess_saved_typed_copy`, requires two distinct read-only observations of
the pinned target path and sealed SHA, the exact typed structure and unique native
row binding, plus all untouched hashes unchanged. The collector must obtain those
observations from real saved files; the oracle cannot establish that supplied
claims happened.

The synthetic tests make Str access raise, execute whole-IText.Assign with a deep
copy of multiple typed items, and reject flattened fields, format loss, missing
metadata, wrong backup/row, failed Assign/Update and unrelated writes. Saved tests
cover structural drift, changed field keys, ambiguous lookup, lost row membership,
wrong seal and original-file changes. No native product CAD file or receipt is a
fixture; local field-display values are synthetic.

The root-reported successful native case is evidence from that specific owner
workflow; this SDK checkpoint has no new native execution. PDF/visible resolution
requires separate export and visual evidence and remains pending in the synthetic
oracle. Dynamic renumbering, arrow following and full package portability are not
established by copying a typed field. A new native pilot needs explicit exclusive
CAD handover and fresh runtime discovery; the active session stays with its owner.
