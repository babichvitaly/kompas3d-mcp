# Saved pagination, owned writeback, per-Save checkpoints and marker batches

This checkpoint is offline-only SDK orchestration with synthetic adapters. It does
not touch an active product helper, installed toolkit, VM or CAD session. The
latest product receipt may still be running and is not inferred to pass from
intermediate evidence. New native integration requires exclusive handover and
fresh discovery. No RO source pool is introduced or claimed faster.

## 1. Two-phase saved pagination/header stabilization

`saved_pagination.stabilize_saved_pagination` accepts a pinned specification plan,
immutable input hashes, explicit owned-dependent snapshots and a bounded Save
budget (2..8, default 3).

- Discovery: guarded Save/Close/Open, then fresh saved API5/API7 pagination,
  physical `GetStampEx(...).SheetNumb`, styles, library, WordWrap and rows readback.
  Unsaved API7 page count is not consulted. Shared raw Stamp.Text7 remains diagnostic.
- Correction: if Text8 differs, assign the **saved** page count and perform the
  next explicit Save/Close/Open. Validate the saved count/header fixed point.
- Confirmation: use a fresh saved read-only observation, without another Save
  merely to confirm an already correct count/header. Instability or exhausted
  budget fails before CDW final serialization/seal; exceptions are never replayed.

The adapter must check real process/document/path/ownership and source read-only
state, verify save/reopen postconditions and raise on unreconciled native failures.
The result is `saved_pagination_stable_in_adapter`, ready_for_finalization=True,
not publication acceptance. The existing `finalization_order` SPW phase can use
this protocol before final CDW stamp/settings Save, seal and full saved-RO gate.

## 2. Immutable inputs versus owned dependents

Each save can reserialize attached **owned** CDWs. Their byte SHA may change in
this authorized writeback window while exact geometry, fields and frame fingerprints
must remain pinned. The window is scoped to explicitly listed owned dependencies;
unknown/missing dependencies or a semantic difference fail. The source/input hash
map is disjoint and must stay exact, with active read-only source guards retained.

The protocol records changed owned byte hashes and the final observed dependent
hashes after writeback. It does not automatically seal or rebaseline semantics.
The collector must compute these fingerprints with the unchanged strict native
geometry/field/frame oracles and preserve their evidence. Caller-supplied opaque
hashes alone do not establish native correctness.

This permission ends at final sealing: the publication oracle still requires byte
stability throughout final RO acceptance. It does not weaken the typed-field-copy
helper's unrelated-file hash gate, because that step does not authorize COMMON/SPW
writes. A pre-publication Save checkpoint is also not a final immutable byte seal.

## 3. Publish every saved job before the next authoring job

`authoring_jobs.author_jobs_checkpointed(names, author_one, journal)` supplies an
active `publish_saved` callback for the current job. Native authoring code must call
it immediately after that job's verified Save, before returning or starting the
next job. A later exception retains the current saved checkpoint. A missing,
duplicate, late or failed checkpoint blocks progression; nothing is reauthored.

`SavedJobJournal` reserves a new exclusive journal directory. Each job publishes
its own file-backed receipt before atomically replacing the aggregate checkpoint.
The artifact's absolute path and SHA at Save are verified, receipt contents are
fsynced, and directory/index durability follows the host filesystem's contracts
(POSIX directory fsync; Windows has no identical directory-fsync guarantee).

On failure, `checkpointed_jobs` identifies completed publication; `reported_saved_jobs`
retains author claims even when disk publication was uncertain. Individual receipts
remain recoverable if aggregate index writing fails. `recover_saved_jobs` returns
a saved prefix and separately reports malformed receipts. A torn last record does
not erase earlier jobs. Artifacts later changed by authorized owned writeback are
reported as changed, not treated as never authored. Missing/unreadable artifacts
remain explicit; none of these states authorizes an automatic rerun.

The journal is a single-owner progress mechanism, not a multi-writer lock or an
exactly-once distributed execution system. A crash after Save but before the
callback is an uncertain current job requiring artifact reconciliation, not replay.
Receipts must contain enough native job identity for the owning collector; the
SDK's small SavedJob schema does not itself establish geometry/manufacturing readiness.

## 4. Batch Local orphan CentreMarkers safely

`marker_cleanup_batch.cleanup_local_marker_batch` accepts explicit captured Local
circular-cut frames and installed type constants, plus an owned-scope adapter.
No project-specific identifiers, paths or helper imports are used.

The adapter captures one pre-snapshot of all protected material/axes/text/cuts and
selected immutable frames. Every marker across **all** selected cuts is classified
before the first deletion. Inside-crop markers and markers with a valid base are
retained. Only an outside-crop, valid, non-Temp CentreMarker of the exact owner,
not aliased to protected geometry, unassociated and linked to an explicitly invalid
line base may be deleted. Unknown outside states abort the whole whitelist.

Before each Delete, the owned scope, fresh Local source/matrix/pose/BaseObject/crop
and full marker properties must still match the whitelist. Delete must return True
and the marker must become invalid. One post-snapshot verifies the protected
geometry/axes/text/cuts and frames unchanged; fresh marker enumeration must match
the complete retained set. Source read-only/identity/hash protection belongs in
the adapter's explicit scope guard and captured source frame evidence; it is not
removed to improve speed.

Failures preserve attempted/deleted references and forbid retry, save, rollback or
scope expansion. If a mutation was attempted, one guarded exit diagnostic snapshot
is allowed; ownership loss prevents even that read. Native adapters must resolve
references freshly in the same exclusive session rather than cache stale COMs.
The bounded classifier covers circular Local crops only; ambiguous/other crop
geometry needs separate evidence.

Synthetic runs with 1, 2 and 7 cuts each use exactly two full protected snapshots,
with per-marker fresh checks retained. This is a call-count result, not a native
speedup measurement. A native adapter that calls an old whole-geometry fingerprint
inside every cheap guard would not implement this contract and would need review.
