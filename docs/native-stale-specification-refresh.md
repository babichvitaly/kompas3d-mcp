# Stale model-SP name with current inherited properties: scoped native acceptance

2026-11-27, KOMPAS-3D v25. A new synthetic case reproduced a stale specification
name while native occurrence properties were already current and inherited. A
property-source reset updated it without a whole-row text edit. Two independent
result reopenings and a separate native grouping audit passed. No engineering
inputs, installed package/config changes or production acceptance are implied.

## Reproduction without changing SP synchronization

The owner contains three linked assembly occurrences: two identical occurrences
inside a nested product and one unique occurrence. Its own model-SP has three
independent UUID rows with Sync=True/EditSourceObject=False. The identical pair
provides a first/visible and a subsequent/hidden control row.

1. Save the owner and close it.
2. Open only the generated unique source assembly, change its Name, call its
   checked Update, save it at the same source filename and close it. Its geometry
   is unchanged. Only that source A3D changes during fixture preparation.
3. Read the saved source through IPropertyKeeper in a separate read-only opening.
   Compare properties 4/5 of the owner occurrence against these actual values,
   not against remembered strings or IPart7.Marking/Name alone.
4. Open the owner without Rebuild or occurrence Update. Property4 is unchanged;
   property5 is the new source name. Both owner FromSource flags are True, but
   SP column5 still contains the old name. The occurrence's display Name cache
   also still contains the old name.
5. Close/reopen the owner read-only twice. The same stale text/current-property
   state persists, with exact UUID/singleton links and the owner disk untouched.

This is a source-change scenario, not a forced stale-string mock. It establishes
one name-only case; it does not establish stale designation/property4 refresh.
A separate attempt changing both source Name and Marking left owner property4
cached despite FromSource=True. That attempt was rejected as a current-properties
fixture. FromSource alone is therefore not sufficient evidence of freshness.

## Rejected text-only attempt

On the established stale fixture, ksSetSpcPropertyFill(pointer,1) returned True
but left the complete observed state unchanged. API5 Edit/Set(column5)/End then
updated the text, but both property4/5 FromSource flags became False; the display
Name cache changed as well. Strict guards rejected the operation before Save.
Its RAM was discarded separately using the exact failed ledger/receipt/process
identity. The raw failed receipt remains failed; no mutation was replayed.

This does not overturn the [earlier externally accepted API5 text route](api5-existing-specification-text.md).
The tested states and cache values differ. No universal cause or equivalence is
inferred from the difference between these cases.

## Accepted property-source operation

An independent worker reopened the original saved stale baseline after the
rejected RAM had been discarded. All six native baseline files were SHA-pinned;
a hash-checked private baseline artifact copy was made before any write. The
source was independently opened read-only to verify its property values again.

The successful operation used the exact occurrence's IPropertyKeeper:

```python
# property5 is the verified name property of the exact owner document.
# Before this call, its value equals the current source and FromSource is True.
keeper.SetPropertyValue(property5, VARIANT(pythoncom.VT_EMPTY, None), False)
```

The call returned native BOOL True. It refreshed SP column5 and the selected
occurrence's display Name cache. Actual property4/5 values and both FromSource
flags stayed unchanged; no temporary local-value write was needed. No SP Edit/
End, row creation, Geometry assignment, clear/reinclude, source rewrite or model
rebuild was used during this refresh.

The third argument is **BaseUnit**, not FromSource. The official
[SetPropertyValue contract](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ipropertykeeper_setpropertyvalue.html)
documents the setter and its BOOL return; it does not promise inheritance reset
for VT_EMPTY. The empty-value behavior above is an empirical result scoped to
this v25 fixture. Do not apply it to intentional local overrides or complex
properties merely because the method exists.

## Preservation evidence

| Observation | Result |
|---|---|
| UUID set and row count | The same three rows |
| Geometry | Exact fresh singleton occurrence per row; no extra parent membership |
| Persistent occurrence identity | Object IDs, metadata keys and source paths unchanged |
| Positions | Exact, including the hidden control row and the unique row's blank position |
| Grouping | Draw/IsFirstObject, raw quantity and all non-target columns unchanged |
| Native printed summary audit | Same UUID/position/group flags; two print groups, quantities 2 and 1 |
| Properties/FromSource | All captured values and flags unchanged; target property4/5 remain inherited |
| Poses/flags | Matrices, Fixed/Hidden and captured tree identity unchanged |
| Deliberate output changes | Target column5 plus selected display Name cache in row geometry and both tree views |
| Material control | 2640 mm³ on both result reopenings |
| Native write boundary | Result Save changes only owner A3D; all source hashes unchanged |

The display cache correction is declared explicitly in the expected result.
It does not discard or normalize object IDs, metadata keys, source paths, poses
or arbitrary row fields. The generic text-only helper continues to reject such
non-text changes. The refresh oracle matches the selected occurrence by exact
persistent identity in each tree, with no basename matching.

The owner was saved and reopened read-only twice, comparing the complete observed
plain-text/flags/membership/property/pose snapshot against that expected result.
A separate read-only A/B worker compared a byte-identical stale baseline copy
against the refreshed result. It checked the documented
[ksGetSpcObjectSummaryCount(pointer,1,0)](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_ksgetspcobjectsummarycount.html)
for each exact UUID via a fresh numeric roundtrip, retaining the same grouping
and printed quantities. The audit wrote no CAD documents.

## Other retained controls

- Four attempts to disable synchronization on the automatically generated row
  did not change its True readback: direct API5 setter, API5 Edit/Set/End, API7
  property put inside API5 Edit/End, and API7 property put/Update. Returns were
  retained, including Update=True; none was accepted as an applied flag change.
- A newly created manually linked row also read Sync=True after fillTexts=False;
  its own property-put/Update trial did not disable it. No frozen fixture was
  claimed from these experiments. One preparation failed before row creation on
  an incorrect constant name; it was corrected to the installed ksAPI7Dual in a
  new fixture. That failed raw receipt was retained.
- A separate VT_EMPTY control deliberately created local overrides, then reset
  properties4/5. It restored the entire original observed state, including
  FromSource, through two result reopenings. It did not reproduce current-property
  stale text because each reset refreshed the corresponding text immediately.

All rejected own RAM was reconciled and closed without result Save. A final
separate attach-only inventory matched the initial empty document set and the
fresh CAD process identity. The installed package/TLB inventory of 68 files was
unchanged. The exclusive resource was explicitly returned to its coordinator.
Private raw receipts, manifests, native baseline/result copies, source snapshots,
transport failures and inventories remain outside this public repository.

## Code and limits

- `scripts/validate_specification_stale_text.py` retains the explicit experimental
  preparation cases; configuration selects the route. It never silently retries
  a failed mutation or saves around a rejected gate.
- `scripts/validate_specification_property_source.py` is the accepted-case runner
  on a pinned, saved synthetic stale fixture. It retains only the executed
  single-reset path, with no untested local-value fallback.
- `src/kompas_mcp/specification_refresh.py` is a detached oracle, not a native
  adapter or source-freshness detector. The caller must establish freshness and
  exact membership independently. Its cache-normalization option is explicit.

Offline suite: **862 passed**, five existing SWIG warnings; Ruff passed. The
24 additional tests cover stale/current oracles, hidden positions, grouping,
source inheritance, persistent identity versus display caches, unapplied True
returns and pending edit contexts. Unit tests are not native acceptance.

The native acceptance is limited to one unique plain name cell in standard
style1 with an unchanged duplicate control group. Complex/hypertext properties,
embodiments, stale designation, grouped target rows, arbitrary styles, a cold CAD
process restart and engineering use remain unestablished. Rich-text formatting
and unobserved native fields are outside the snapshot contract. No installed
MCP integration or automatic production repair was deployed.
