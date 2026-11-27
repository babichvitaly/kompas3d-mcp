# Nested model-SP rows: separate source refresh from existing text authoring

2026-11-27, KOMPAS-3D v25, standard style 1. Separate synthetic name and designation
fixtures establish a bounded two-document route. Direct resets at an outer
owner's nested occurrences previously returned True without updating its text;
that unsuccessful route was not repeated. No engineering model was opened or
changed for this acceptance. Installed packages/configuration remain unchanged.

## What the two-owner experiment establishes

Each generated immediate owner contains two occurrences of one linked assembly source
and one unique control. Its three independent model-SP UUID rows have exact
singleton Geometry and positions 10/10/20. A separately generated upper owner
reveals that assembly's composition. Its own three SP UUIDs, raw positions,
first/visible flags and native summaries are recorded separately: the two owners
are not assumed to share UUIDs or raw position values.

1. With both owners closed, change only the selected source's Name (property 5)
   or Marking (property 4). Read actual source values 4/5 from an independent
   read-only opening and bind them to the saved source SHA.
2. Establish both owners' stale states through two read-only baseline openings.
   For name, occurrence properties are already current with FromSource=True.
   For designation, the property 4 value cache is stale despite FromSource=True;
   correcting this value must be declared explicitly in the source-reset plan.
3. Open the immediate owner read/write and bind the plan to its **current**
   document Reference and exact description. Reset the two **direct** occurrences'
   selected property with VT_EMPTY/BaseUnit=False. Verify the entire expected
   snapshot and native summary before Save and through two result reopenings.
4. Open the upper owner read-only twice. Source properties and display Name/
   Marking caches are now current, but both selected SP text cells remain old.
   All other captured evidence remains exact. **Child Save alone fails the upper
   text-refresh gate.** No upper rebuild or Save is used to conceal this result.
5. In a separate worker, pin that saved state/closure and open only the upper
   owner read/write. Resolve each existing UUID through UniqueNumber→API5
   pointer→numeric roundtrip; verify exact getter column addresses. API5
   Edit→SetColumnText→End authors the two existing text cells. Final acceptance
   requires exact full payload and native grouping, then Save and two read-only
   result reopenings.

Designation and name passed this full route through the guarded helpers, each
on its own new fixture. An earlier independent name control passed the same
operations as an explicit native recipe. Source
resets and text authoring are separate operations; the second is **literal text
writing from independently verified current properties**, not a general native
property-resynchronization command.

## Preservation gates and write boundary

| Gate | Accepted observation |
|---|---|
| Row identity | Each owner's original complete UUID set, no recreation |
| Membership | Fresh exact singleton per existing row, no Geometry assignments/extra parents |
| Persistent occurrence data | Object IDs, metadata keys, source paths, matrices, Fixed/Hidden exact |
| Properties | Name values unchanged during name refresh; selected designation cache correction explicit |
| Inheritance | All captured property 4/5 FromSource flags stay True during both accepted operations |
| Grouping/positions | Original raw positions, Draw/IsFirst, quantities and native summary count per UUID exact |
| Immediate-owner Save | Changes only the immediate owner A3D |
| Upper-owner text Save | Changes only the upper owner A3D; sources and already accepted child unchanged |
| Geometry | 2640 mm³ on both result reopenings at each owner |
| Persistence | Two baseline and two result RO cycles per accepted operation; no RO disk writes |

Native grouping is read with
[ksGetSpcObjectSummaryCount](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_ksgetspcobjectsummarycount.html)
for exact UUID/numeric mappings. Intermediate regrouping of selected peers may
be observed, but final positions, representatives, all captured fields and
summary values are never relaxed or repaired after the fact.

The source-reset behavior of VT_EMPTY remains empirical. The documented
[SetPropertyValue](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ipropertykeeper_setpropertyvalue.html)
third argument is BaseUnit, not FromSource. API7
[ISpecificationObject.Edit](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ispecificationobject_edit.html)
starts visual editing according to the installed SDK and is not used. API5
[ksSpcObjectEdit](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksspecification_ksspcobjectedit.html)
is the separate bounded text route.

## Helpers default to read-only diagnostics

- `specification_source.plan_owned_source_refresh` requires a saved assembly,
  exact description 0/style 1 context, complete UUID bindings, fresh singleton
  membership, direct occurrence paths, independently read source values plus
  SHA256 and a complete native group summary. Nested occurrence resets and
  intentional local overrides are rejected. Property-cache correction requires
  an explicit policy and is limited to the selected source-backed properties.
- `specification_source.refresh_owned_sources` defaults to `dry_run=True`.
  Explicit execution guards ownership before every adapter call, rechecks
  source evidence, rejects false/non-BOOL returns and checks the complete final
  snapshot plus native summaries. It returns **unsaved** evidence.
- `specification_cached_text.plan_cached_text_refresh` additionally requires
  source values, owner properties **and display caches** to be current before
  allowing text-only changes. It rejects a remaining cache mismatch.
- `specification_cached_text.author_cached_text_owned` defaults to diagnostics.
  Explicit API5 execution pins runtime context, exact UUID/numeric mapping and
  column execution/block addresses, and preserves pending edit state on failure.
  No automatic End, retry, Save, rebuild or recovery follows a rejection.

The adapter must prove completeness of native observations and exclusive STA
ownership; detached Python data cannot establish these facts itself. Neither
helper connects to CAD or is registered as an automatic installed MCP repair.
Caller-owned Save plus two independent reopenings remain necessary.

One helper integration preparation correctly rejected a plan carrying the old
RO document Reference after the owner was reopened RW. No reset was invoked.
The clean own RAM was closed through an exact pinned failure ledger, leaving the
raw receipt failed. A new fixture prepared its live plan from the fresh RW
capture; reopening-stable semantic identity was not weakened to bypass ownership.
A stateful regression covers rejection and explicit runtime rebinding.

## Scope and next boundary

These fixtures do not establish a universal cause for earlier API5 authoring
trials that changed FromSource to False. Their different cache states are
observations, not proof of causality. Unobserved tuning fields, rich text,
embodiments, arbitrary styles, cold process restart and installed integration
remain outside acceptance. No engineering repair or release is implied.

A real archived candidate was reviewed **offline only**: archive CRC/SHA and
its manifest passed and historical native-resolved source files were present.
Some serialized Sources-table candidate paths did not resolve lexically inside
that archive. Such entries may include obsolete/cache records; this does not
prove missing live geometry. It does mean that copied bytes plus historical RAM
resolution do not independently prove a safely isolated, portable saved closure.
Engineering acceptance remains pending exact reference resolution in a separate
owned copy and an adapter sized for its full row/tree inventory. The small
synthetic runner's traversal limits were not silently expanded for engineering
files, and no real UUIDs/paths/receipts are included here.

An exact historical crosswalk was subsequently supplied and its candidate parent/
target archive hashes were checked offline, without basename selection. This
identifies historical destinations; it still does not establish the required
stored-to-live resolution, preserved Geometry or a passing bounded relocation.
The engineering RW stage was unstarted at that checkpoint. The subsequent
[exact-byte isolated-copy experiment](native-reference-copy-isolation.md)
separately accepted an augmented reference layout and eight-cell model-SP text
authoring through two result reopenings. It does not certify the original ZIP
as portable or replace an accepted engineering package.

Offline suite: **910 passed**, including 35 additional stateful source/text
contracts; Ruff and sdist/wheel build passed. Five existing SWIG warnings remain.
The tests cover dry-run without mutation, unapplied successful returns, source
revision drift, intentional overrides, nested-source-reset rejection, current-cache
text preflight, numeric mapping, pending edits and strict final preservation.
Unit tests alone do not establish native acceptance.

A separate host audit rebuilt the allowed snapshot differences without importing
the oracle: both properties, each owner's two baseline/result reopenings, exact
native grouping and baseline/intermediate/final artifact hashes passed. Final
attach-only discovery matched the initial empty document set and process identity.
All own documents were closed, 68 installed files were unchanged, and exclusive
CAD/COM/VM access was explicitly returned to its coordinator. Private raw and
artifact evidence remain outside the public repository.
