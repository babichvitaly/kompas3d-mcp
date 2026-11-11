# Bounded metadata batch: full boundary snapshots and fresh cheap guards

`metadata_batch.run_metadata_batch` is an explicit orchestration API for an
injected synchronous adapter. It addresses repeated full row/Columns/Text reads
inside ownership/state/restore callbacks. No CAD/COM connection, installed SDK
change, active project helper patch, persistent cache or native speed claim is
part of this checkpoint.

## Boundary contract

The caller pins the owned target and distinct read-only source references/paths,
source hashes, a finite named step plan and the exact expected ViewState after
each step. A batch captures full source and owned metadata at entry and exit:
UUID, section, all supplied columns, sync and EditSourceObject. Native adapters
must enumerate the **complete intended scope**, not silently truncate it or
return precomputed hashes in place of fresh rows.

Source rows and pinned original file hashes must remain unchanged. Owned rows
must match the entry snapshot by default; an explicit complete expected-owned
payload can permit a planned change. It cannot waive source preservation. Missing,
extra, reordered or altered metadata rows fail exact comparison. Duplicate UUIDs
are rejected within each metadata scope.

Snapshots are detached validated data local to this single call. There are no
cached COM interfaces, cache reuse across jobs or a global metadata-valid flag.
Success is `batch_verified_in_adapter`, with native acceptance pending, no save,
and retry_allowed=False. This is not an atomic/rollback transaction.

## Fresh checks inside the batch

Before executing each named step, after its mutation, after reading its view
state, and around each full snapshot, the adapter must freshly read exact owned
identity/path/ownership/readOnly and source identity/path/readOnly/sourceChanged.
Those fields must equal the pinned state: writable owned copy, separate read-only
source and SourceChanged=False. These checks must stay cheap; they must not
re-enumerate BOM rows or columns. A native adapter must be audited to establish
that boundary rather than reusing a legacy heavy guard under a new method name.

Every completed step also reads and compares the full expected ViewState:
source/hash, number/type, matrix, pose, bounds, object count, unfold and actual
projected geometry digest. This API does not replace exact geometry/pose checks
with a metadata cache or line-count-only acceptance. Source hash/row checks remain
fresh at full boundaries even if Changed remains False.

## Limits, failures and concurrency

Limits bound named step count (default 32, maximum 128), total source+owned rows,
column cells and a cooperative elapsed-time budget. `read_metadata(limits)` must
honor enumeration bounds **before** expensive native traversal; the runner also
checks the returned size. Time is checked between callbacks and after exit
verification. It cannot preempt a blocked native call, terminate CAD, or promise a
hard timeout. Choose the budget using measured native boundary costs.

On a step/postcondition failure the runner retains the original failure and
attempts one guarded exit snapshot if it has not already attempted exit. No
mutation is replayed. Ownership/reference/path/readOnly/sourceChanged failure
blocks even that diagnostic read. A failed exit snapshot is never retried.
Uncertain mutated copies remain for explicit reconciliation; the API neither
saves, rolls back, closes documents nor discards changes.

Exclusive STA/session ownership remains mandatory. The batch creates no lock and
cannot detect a transient external metadata change restored before exit, or prove
the truth of adapter observations. Read-only source protection must therefore
remain in the native collector and actual filesystem/ownership controls. All
mutations must be from the explicit plan; native adapter methods must raise on
unreconciled errors and must not silently run unrelated jobs.

## Adapter and measured synthetic coverage

Required methods:

```text
read_guard_state()          -> GuardState-compatible detached fields
read_metadata(limits)       -> complete Metadata-compatible source+owned rows/hash
execute_step(name)          -> one explicit scoped operation, no implicit retries
read_view_state(name)       -> fresh complete ViewState-compatible observation
```

Synthetic tests use two 127-row metadata scopes with text columns. Batches of 1,
6 and 24 steps each read the full payload **exactly twice**, while retaining
per-step cheap guards and exact view reads. Tests inject unexpected owned payload
mutation at batch exit, source metadata/hash change despite unchanged cheap flags,
all eight cheap-guard field changes, wrong geometry/pose, partial native-like
exceptions, planned owned changes, traversal limits and cooperative deadline expiry.

These are call-count and correctness results only. Native speedup, callback costs,
SDK interface freshness and saved-copy persistence remain unmeasured/unaccepted
here. Integrate into an inactive owned-copy native pilot only after explicit CAD
handover and fresh runtime discovery. Do not rewrite an active authoring helper.
