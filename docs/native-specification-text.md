# Synthetic API5 text authoring: two rejected preservation gates

Later work reproduced a source-change stale-name fixture and accepted a separate
[property-source refresh](native-stale-specification-refresh.md). The literal-text
failures below remain negative and are not relabeled by that different operation.

2026-11-27, KOMPAS-3D v25. Two independent synthetic fixtures were built under
new isolated roots after explicit exclusive handover and fresh discovery. No
engineering inputs were used. Initial and independently discovered final open
document sets were both empty, with the same freshly verified CAD process identity.
One STA worker ran at a time; the installed package and configuration were not changed.

## Question and exact scope

Can explicit text changes on an existing own model-specification row preserve the
observed non-text payload, UUID, exact singleton Geometry, positions, occurrence
properties/FromSource and poses? The experiment writes deliberately different
literal text, rather than copying already-current native properties into stale
cells. It therefore does not reproduce production stale text or general resync.

Each fixture contains a nested product with two identical source-assembly
occurrences, plus a separate unique control occurrence in the owner. The owner
has three independent rows, Sync=True, EditSourceObject=False. The identical
pair includes first/visible and subsequent/hidden rows. Prism source volumes
were measured as 800 and 1040 mm³ during fixture creation. Those measurements
do not establish post-edit geometry or result persistence.

The baseline was saved and reopened read-only before editing. The adapter then
verified the exact writable owner Reference/path/type, explicit description
index/layout/style/source, API5 long1/stateTrue description return, UUID→double
UniqueNumber→API5 pointer→number mapping, and API5/API7 column text agreement at
the declared execution/block. No API7 row.Update or Geometry assignment was used.

## Observations before any result Save

| Independent case | Native calls | Preserved observations | Unexpected changes |
|---|---|---|---|
| Edit the hidden member of the identical pair first | Edit=1; two Set=1; End is a positive pointer with exact numeric roundtrip | Existing UUID set, singleton membership, positions, poses and captured properties | That row's Draw and IsFirstObject changed False→True along with the two requested text cells |
| Edit the unique row, leaving the identical pair untouched | Edit=1; two Set=1; End is a positive pointer with exact numeric roundtrip | Existing UUID set, singleton membership, positions and poses | Occurrence property4/5 values and Name/Marking changed to the literal text; property4/5 FromSource changed True→False |

The first case is consistent with separating a formerly identical row into its
own print group; it is not evidence of a general grouping defect. Only the first
planned row edit ran: the full group was not edited or accepted. The second
case demonstrates that literal text authoring with synchronization enabled can
also author occurrence properties in this fixture. It is not a text-only update.
Neither observation establishes behavior for every style, embodiment or owner.

Both complete-payload gates correctly returned failure. No result Save or result
SavedRO cycles were performed, and no automatic retries, fallback setters,
grouping changes, source-inheritance repairs or extra End calls followed.
Successful Edit/Set/End returns were retained without relabeling them full success.

## Reconciliation and preservation

Each failed RAM document was discarded in a separately scoped cleanup operation:
the exact failed receipt SHA, fresh process identity, document Reference/path/
kind/read-only/state and own remainder ledger had to match. A valid End pointer
had already closed the editing step in each case. No foreign document was adopted.
After each cleanup, own remainder was empty. A final separate attach-only
discovery confirmed no open documents. The installed package/TLB inventory of
68 files was unchanged at both worker boundaries.

A separate non-COM audit compared every own disk file to the pre-edit inventory
and SHA: all six files per fixture matched. Rejected RAM was never persisted.
Private artifact copies were hash-checked; raw failed receipts, source snapshots,
transport logs and inventories stay outside this public repository.

The first discovery launch was rejected by Parallels before a worker receipt was
created. A separate non-COM transport check succeeded; a newly named read-only
discovery then completed. The transport cause is not established. The initial
disk-audit comparison also failed because it compared raw path casing to the
native manifest's normalized keys; comparing the same normalized identities
confirmed exact inventory/SHA equality. Neither event caused a CAD mutation replay.

## Code, tests and remaining acceptance

`src/kompas_mcp/specification_text.py` is an opt-in, injected-adapter helper with
no COM imports or automatic connection/save. It bounds each plan to one existing
UUID and one or two explicitly addressed designation/name cells. It checks strict
native long returns, distinguishes End pointers from booleans, preserves partial
failures and compares the complete caller-observed state against the exact plan.
It does not supply a production MCP tool or prove completeness of an adapter's
snapshot. Rich-text formatting and unobserved native attributes are outside this
plain-text/flags/membership/property/pose snapshot contract.

The helper passed 23 stateful offline tests, including hidden position changes,
extra parent membership, property inheritance, UUID and pose drift, loss of
ownership, wrong numeric mapping/column address, false native returns and pending
edit contexts. Full offline suite: 838 passed, with five pre-existing SWIG
warnings; Ruff passed. Unit tests establish guard behavior, not CAD acceptance.
`scripts/validate_specification_text.py` is the opt-in acceptance runner; it requires
private explicit handover/config and a fresh synthetic root. Its two observed
cases above are negative, so no native text-only acceptance is claimed for
this adapter. The public runner's explicit target_case distinguishes the cases.

The earlier [external accepted text-authoring receipt](api5-existing-specification-text.md)
remains separate: its desired text came from already-current actual properties.
These different-input experiments do not overturn that scoped result or establish
its applicability to arbitrary literal values. The next native acceptance case
would require a new proven stale-text fixture with current properties already
equal to the desired text, preserving every declared flag/position/property and
dependency write boundary through two independent result SavedRO cycles. Editing
an entire identical group would require an explicit group plan and a final full
payload gate; the current single-row helper must not silently permit regrouping.
