# Offline view-update and sheet-history evidence oracles

`state_oracles.py` classifies **supplied observations**, without CAD/COM, files,
mutation, or native acceptance. It is not wired into native execution or installed
clients. Existing Update/Rebuild gates remain unchanged. Missing/malformed evidence
fails closed; unknown fields and implicit boolean conversions are rejected.

## An identical view restore can report Update=False

`assess_view_update(payload)` permits False only when before/requested Scale/X/Y
are identical and explicitly positive, with the before and all final sources
already equal to the caller's resolved canonical expected source and pinned SHA.
It does not waive a failed operation that actually changes pose/source. Even True
cannot bypass the downstream checks.

Required evidence uses the existing `ViewState` contract, including a proper 4x4
rotation matrix, positive scale, finite coordinates, positive-width/height bounds,
nonzero object count and a projected-geometry digest. The additional observation
fields require `valid=True` and nonzero `supported_geometry_objects`, no greater
than ObjectCount. Number/type must retain identity. Exact final pose is required;
this narrow exception requires X/Y > 0 as well as Scale > 0.

The explicit expected set of view numbers must match all successful per-view
rebuild rows without duplicates. The current view must be included; document
rebuild is mandatory. Exactly two distinct read-only open IDs must report the
same pinned saved drawing SHA and identical final ViewState/geometry count.
The synthetic matrix includes a derived section (view_type=7); the exception is
not an unconditional type-7 waiver.

Python API input schema is available through `ViewEvidence.model_json_schema()`.
`ViewEvidence` contains `before`/`after` observations, expected source/hash,
requested pose, update return, expected view numbers, rebuild rows, document
rebuild result, saved drawing hash and two reopen observations. JSON arrays are
accepted for the pose; their scalar numeric types remain strict.

## Excluded bend features require exact baseline evidence

`assess_sheet_history(payload)` compares the entire ordered `baseline_history`
and `actual_history`, including unique semantic keys, kind, excluded/rolled-back
flags, Valid, ObjectError and State. Semantic keys must be stable collector-owned
identities, not transient COM pointers. The sheet states must match exactly:
positive thickness, unfolded flag, positive solid-body count and zero errors.

Only excluded `sheet_bend` rows qualify for this exception. Their inactive native
flags/errors may match a known baseline without being classified as a new geometry
error. Rolled-back rows and other kinds of excluded feature are rejected in this
bounded contract. At least one active feature must remain; every active feature
must be Valid with ObjectError=0 even when a bad active state also exists in the
baseline. A changed identity/order/exclusion/error, or changed sheet state, fails.

Input schema: `SheetEvidence.model_json_schema()`. Empty or ambiguous histories
cannot establish the baseline condition. A caller must pin and independently
approve the baseline; copying current observations into a new baseline does not
establish historical validity.

## Interpretation and limits

A successful result is named `consistent_offline_evidence`, with
`native_acceptance='pending'` and `mutation_performed=False`. It does not claim
that supplied rebuilds/open IDs actually occurred, establish event chronology,
validate the collector's geometry digest, or prove full body/visual/manufacturing
acceptance. Those remain the native owner's responsibilities. This checkpoint
introduces no automatic exception in `drawings.rebind`, no SDK installation, and
no new MCP tool. Integrating a native gate requires separate owned-copy validation.

Synthetic regressions mutate individual required gates: stale source/hash,
changed pose, invalid matrix/bounds, empty geometry, missing/failed rebuilds,
reused/non-RO reopen evidence, saved-artifact mismatch, projection/unfold changes,
changed history and errors in active features. No engineering files are fixtures.
