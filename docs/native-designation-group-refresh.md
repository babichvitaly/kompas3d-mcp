# Designation and identical grouped rows: synthetic v25 source refresh

2026-11-27. This extends the [unique-name experiment](native-stale-specification-refresh.md)
using separately generated fixtures. Engineering inputs and installed packages
are unchanged. Private raw receipts, CAD artifacts and transport configuration
are excluded from this public repository.

## Designation (property 4)

Changing only the saved source assembly's Marking while its owner was closed
left the owner's designation property cache and SP column4 old. FromSource=True
did **not** prove that the owner property value was current. The actual source
properties4/5 were read independently from a read-only source opening and its
saved file was SHA-pinned. Two owner read-only openings reproduced the stale
state before the refresh write.

The exact occurrence's property4 reset used:

```python
keeper.SetPropertyValue(property4, VARIANT(pythoncom.VT_EMPTY, None), False)
```

The unique-row fixture passed two result reopenings with a blank target position.
A separate, stronger direct-occurrence fixture refreshed **both UUID rows of an
identical group** with initial positions 10/10 and an untouched control at20.
Both calls returned native BOOL True. Complete final and two read-only result
snapshots passed, including the original positions 10/10/20 and group representative.
The selected inherited property4 values, SP column4 and display Marking caches
became current. Property5 and every captured FromSource flag stayed unchanged.

This is accepted as a source-backed **property-cache plus text refresh**, not as
a reproduction of stale designation with an already-current owner property4.
The detached oracle declares the selected cache-value changes in advance;
unselected property changes and arbitrary values remain failures.

## Identical grouped rows

The numbered direct fixture has three exact singleton-linked UUID rows: two
occurrences of the same source and one unique source. The two identical rows
share position 10, one is first/visible and the other subsequent/hidden. The
unique control has position 20. Native summary counts are checked through exact
UUID→numeric number→pointer→number roundtrips, not inferred from row count.
The visible groups have quantities 2 and1; the hidden member's own API summary
value is also preserved exactly.

A separate numbered property5 fixture reproduced **already-current** owner
properties4/5 with FromSource=True while both grouped SP names stayed old,
including through two baseline reopenings. Resetting property5 on each direct
occurrence refreshed both names and their display caches. The complete final
snapshot and two result reopenings preserved all three UUIDs, singleton links,
positions 10/10/20, native summary counts, first/visible membership and all
property values/FromSource flags. Each source closure remained unchanged during
refresh and only the owner A3D changed on Save. Both result volumes were 2640 mm³.

Selected occurrences are reset in visible-first order. Native grouping can split
temporarily while the two peers have different text. The intermediate oracle
permits only the selected rows' grouping flags/position text to vary; IDs,
singleton membership, inheritance, poses and control rows remain frozen. This
does **not** relax final acceptance: final grouping, representative, positions
and native summary counts must equal the baseline before Save and after each
of two result reopenings. Positions are never repaired during refresh.

## Numbered fixture preparation

Numbering is authored before any source metadata change or stale baseline.
API5 Edit→ksSpcPosition→End produced 10/10/20 but also changed properties4/5
FromSource flags to False. That first preparation was rejected before source
change and discarded without saving the rejected RAM.

A distinct fixture explicitly restored inherited properties4/5 with VT_EMPTY
after numbering. It then required the entire observed state to equal the
original except the three position texts. Only after this strict preparation
gate was the baseline saved and the source changed. This setup is separated
from the refresh under test; it is not an implicit repair of local overrides.

## Retained negative control and scope

For duplicate targets nested inside a product, resetting property5 directly at
the outer owner's nested occurrences returned True twice but did not update
their SP text or display Name. The strict final gate rejected this before Save;
only exact owned RAM was subsequently discarded. No general nested-owner route
is accepted. A direct-occurrence name-group fixture with blank positions passed;
numbered coverage is recorded separately.

The [official SetPropertyValue contract](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ipropertykeeper_setpropertyvalue.html)
defines the third argument as BaseUnit, not FromSource. VT_EMPTY inheritance
behavior remains empirical and scoped to these fixtures. The
[position authoring method](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_ksspcposition.html)
belongs to fixture preparation. The
[summary-count method](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_ksgetspcobjectsummarycount.html)
provides the independent native grouping observation.

Subsequent [two-owner nested-row experiments](native-nested-specification-refresh.md)
establish a separate source-owner refresh followed by explicit API5 text
authoring at the upper owner. They do not turn the rejected nested property
reset above into a successful operation or a general native resync command.

The runner is opt-in `scripts/validate_specification_group_refresh.py`; it uses
one exclusive STA worker, fresh session inventory, new synthetic GUID roots,
strict owned-document guards and no mutation replay. All result Saves are
checked by reopening, not by the void Save return. The source closure must stay
SHA-identical during refresh; only the owner A3D may change. No Geometry setter,
whole-row edit, row recreation or rebuild is used during refresh.

Acceptance covers the captured plain text, row flags, grouping observations,
persistent IDs/source paths, exact fresh singleton links, properties4/5 and their
FromSource flags, tree/poses and material volume 2640 mm³ in standard style1.
Unobserved tuning options, rich text, other styles, embodiments, intentional local
overrides, nested targets, cold process restart and production repair remain
outside this acceptance. This is detached SDK/test work, not installed integration.

Offline validation: 875 tests passed, including 13 new source-cache/intermediate/
final preservation contracts; Ruff passed. The five existing SWIG warnings remain.
Unit tests do not establish native acceptance.

A separate host audit rebuilt expected snapshot changes without importing the
oracle and verified all three accepted fixtures, two baseline/result reopenings,
native grouping equality and hash-checked baseline/result copies. A final
attach-only discovery matched the initial empty document set and process
identity; all owned documents were closed, 68 installed files were unchanged,
and the exclusive resource was explicitly returned to its coordinator.
