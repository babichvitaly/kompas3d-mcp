# Call-scoped STEP import and RAM versus SavedRO reference closure

This checkpoint adds offline contracts/regressions only. No CAD/COM/VM session,
frozen helper, installed toolkit or product export is changed. Native performance
is not measured or claimed. Real product evidence remains outside public tests.

## STEP conversion is a specific import result, not ordinary path reuse

`tracked_import.import_step` is the explicit controlled import/SaveAs operation.
It permits an imported writable document's actual PathName to be the requested
STEP stem with native `.m3d`/`.a3d` extension, with Changed=True after import.
That does not require or justify relaxing normal native-open path guards.

Before Documents.Open, the function creates a unique invocation ID and captures a
fresh document inventory. The returned document reference must be absent before,
the inventory delta must contain exactly that one new document, and every prior
document's path/type/Changed/ReadOnly must remain unchanged. The returned object's
state must match the fresh inventory entry. Actual kind/native extension/path
must agree with the bounded import conversion contract.

Only an explicit non-overwriting SaveAs inside the requested owned root can
complete ownership registration. Native path/Changed/write evidence and source
hash are checked, then the complete inventory is checked again. No unknown
existing document is adopted and no failed/uncertain document is closed/retried.

The receipt separates `import_source`, `converted_path` and `saved_path`, and adds
`import_call_id`, `created_reference`, imported kind/Changed and before/open/save
inventories. A caller integrating a Session must consume this controlled result's
actual native/owned path and fresh reference, not compare PathName literally with
input.step. The invocation token is audit correlation, not a transferable ownership
credential. Never register an arbitrary document from a stale or fabricated JSON
receipt: live session/process identity and fresh inventory still belong to the
exclusive owner. The SDK does not patch an external frozen Session implementation.

The ordinary `documents.open_document` path contract is unchanged and still rejects
STEP before connecting. Import fixtures cover Changed=True, part/assembly conversion,
call-specific IDs/paths, unexpected/reused documents, changed prior state, wrong
native path/kind, source changes and unconfirmed SaveAs.

## Phase one: bytecopied parent and measured RAM aliases

`reference_closure.assess_ram_reference_aliases` consumes an explicit owned parent
bytecopy and complete occurrence-slot graph. Each planned reference pins its
canonical destination, bytes SHA and placement matrix. Nested parent prefixes
must exist; cyclic graphs require a separate protocol. No number of direct links
or project path is hardcoded.

A RAM-resolved legacy path is allowed only when it is explicitly listed for that
exact occurrence, its observed SHA equals the canonical destination's pinned SHA,
and the alias's source bytes are independently pinned as immutable. Nested parent
contexts can similarly use declared SHA-identical RAM aliases. Unknown same-name
or same-SHA paths do not pass by approximation. Parent-copy bytes, full declared
source hashes and preserved assembly-semantic fingerprint must match the baseline.

The result explicitly keeps `persisted_closure_verified=False`. A byte-identical
source alias or acceptable current RAM resolution does not establish what the
copied parent serialized or what a fresh reopen will resolve.

## Phase two: explicit direct rebind, Save/Close and fresh SavedRO

`assess_saved_reference_closure` requires the initial RAM snapshot, exact planned
direct-rebind slot list, confirmed Save/close and two independent read-only saved
observations of the sealed parent. Rebind applies only to explicit direct slots;
this oracle never mutates nested files or guesses missing links.

Every saved occurrence must resolve to the exact planned destination. Its stored
reference, interpreted against the actual expected saved parent directory, must
also resolve there; an old stored path cannot be hidden by a newer RAM resolver.
Saved nested parent paths must be canonical, not a legacy parent alias. Child file
hashes, placement matrices, complete slot set, parent seal, immutable inputs and
preserved semantic fingerprint remain pinned. Unknown/missing/extra links fail.

Paths are handled without filesystem access as explicit absolute Windows or POSIX
paths. Windows comparisons account for case/slash conventions; ambiguous drive-
relative/root-relative saved paths and noncanonical resolved traversal are rejected.
Native collectors must resolve real aliases/symlinks and hash the actual files;
lexical normalization or caller-provided opaque digests alone are not evidence.

An external canonical dependency is permitted only when explicitly SHA-pinned as
an immutable input. Therefore even consistent SavedRO evidence does not establish
a self-contained portable package. The result reports saved-path consistency in
the supplied observations, native acceptance pending and portability=False.

## Native integration boundary

These tests use synthetic path/slot graphs and placement matrices only. A native
collector must prove fresh Open/close identity, complete bounded dependency scans,
file kind/existence/hash and actual geometry/metadata invariants with unchanged
strict oracles. This module cannot certify that supplied Open IDs or observations
actually occurred. Do not skip existing source protection or final SavedRO gates.

Before integration: obtain explicit CAD handover, discover the runtime/documents
afresh, and test on new owned copies. The existing visible RO review document and
current product deliverables remain with the owning CAD chat. No live speedup or
product release success follows from this offline SDK checkpoint.
