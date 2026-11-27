# Exact-byte reference copies and a separately verified model-SP experiment

2026-11-27, KOMPAS-3D v25. A private archived assembly was staged under a new
exclusive test root without editing CAD file contents. This establishes a
particular **augmented copy**, not portability of the unchanged input archive.
Engineering files, UUIDs, paths and raw receipts are excluded from this report.

## Isolation result, before any SP write

The archive contained 612 manifest-pinned files. A full saved-path review found
relative reference candidates whose historical destinations were absent from the
archive layout. Exact historical mappings identified their canonical targets;
parent and target archive hashes were checked. No basename search or equal-hash
identity inference was used. Historical mappings locate targets; the sealed
current archive, not an older variant, defines the bytes to copy.

The staging plan preserves the original file hierarchy below an explicit payload
envelope and creates additional byte-identical files at the stored paths. It
recursively checks references from each additional parent location. These are
ordinary independent copies, with no symlinks/hardlinks to the originals and no
patching of an undocumented CAD binary format. The envelope matters: an initial
layout exposed ancestor-relative escapes and was rejected before CAD access.

The accepted plan had 1846 file placements and 2623 expanded serialized reference
candidates, with zero escapes and zero conflicting canonical origins. All 612
original file bytes stayed identical. Every staged file and candidate destination
was checked against the exact source pin. This includes potentially obsolete
Sources-table entries, without assuming they are all live dependencies.

Two independent read-only native openings then checked:

| Observation | Result |
|---|---|
| Own model-SP | Same 119 UUIDs, complete plain-text columns, sections, Sync and first-on-sheet flags as the historical saved receipt |
| Full assembly tree | Same 863 occurrence slots, canonical source identities, local/world matrices, Fixed/Hidden |
| Geometry links | All 119 rows had fresh exact singleton occurrence links; persistent object IDs roundtripped |
| Native dependency list | 546 project files resolved inside the new root, including the model's specification-source binding |
| Runtime resource | One installed standard layout was explicitly SHA-pinned; arbitrary outside files were not allowed |
| Geometry witnesses | Native assembly measurement and target bounds matched; no geometry edit/rebuild was used |
| Read-only persistence | Full captured state and native grouping stable over two openings; staged file hashes unchanged |
| Original protection | Archive, protected original tree and installed package/type libraries unchanged |

The actual occurrence tree and native
[recursive file/type enumeration](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ikompasdocument1_getexternalfilesnamesex.html) were
checked in addition to the serialized candidate table. A complete table alone
would not establish what the application loaded. The model description's SPW
binding was checked separately as well; it is not inferred from component paths.

The old SP text with current inherited property 4/5 values was reproduced on the
isolated copy before any text write. Each target's singleton membership and
FromSource=True were confirmed. This is native copy-only evidence, distinct from
an externally supplied receipt or an offline mapping assertion.

## Detached SDK planning contract

`reference_copy_plan.plan_reference_copies` accepts a canonical file/SHA inventory
and explicit parent/stored-path/target edges with endpoint hashes. It does not
parse CAD, guess targets, access files, stage data or connect to the application.

It expands a finite queue of exact destinations and rejects root escapes,
absolute/drive-relative/library paths, ambiguous Windows names, case collisions,
file/directory collisions, conflicting origins and bounded-expansion overruns.
Different canonical origins conflict even if their bytes have the same SHA.
Finite graph cycles are deduplicated as file-placement data; this does not
establish that a CAD application supports opening cyclic documents.

The planner's result keeps `native_acceptance='pending'` and
`portable_saved_verified=False`. A caller must create a new owned directory,
write only exclusive non-overwriting copies, verify the actual resulting hashes
and stored destinations, and independently prove fresh native resolution and
semantic preservation. The general planner reproduced the particular private
stage exactly, including its canonical origins; the public tests use synthetic
paths/data only.

Twenty offline tests cover recursive copies, explicit ancestor envelopes,
Windows device/stream/path collisions, hash mismatch, equal-SHA identity conflicts,
finite cycles and bounded infinite expansion. Unit tests do not establish native
isolation.

## Separate SP stage and limits

The text-authoring stage was a separate acceptance decision using the
[guarded current-cache helper](native-nested-specification-refresh.md). It requires
fresh runtime ownership, independently read current source values and hashes,
exact existing UUID/numeric mappings, full state/grouping gates, one explicit
owner Save and two result reopenings. Passing reference staging alone cannot
approve that write or establish a general properties-resynchronization command.

On this isolated copy, independent read-only openings of the two target source
files confirmed values 4/5 and pinned their hashes. The fresh RW capture matched
the accepted isolation snapshot. Default helper diagnostics performed no write;
explicit API5 execution updated eight cells in four existing rows. No source
reset, Geometry assignment, component replacement or 3D rebuild was called.

The entire observed 119-row/863-occurrence snapshot, inherited property flags and
native per-UUID group summaries passed before Save. One explicit owner SaveAs
returned None, as documented for this Automation contract; success was checked
through file/Changed evidence and two fresh result reopenings. On both openings,
the expected text was current and every other captured field remained exact:
UUIDs, singleton links, persistent IDs, raw positions, group flags/quantities,
all captured properties/FromSource, matrices and component flags. Native geometry
measurements and target bounds were unchanged.

Only the owner model file changed among 1846 staged files. All source/printed SPW
files and source assemblies kept their bytes. A separate post-save filesystem
audit confirmed all 2623 serialized candidate paths still resolved inside the
copy, with no absolute candidate paths. A private result ZIP retained the whole
augmented layout; CRC and every payload SHA were checked independently on the
host. Neither that archive nor raw engineering receipts are published here.

A separate host audit constructed the eight-cell expected delta without importing
the helper oracle and compared both saved snapshots against it. Reference-copy
acceptance and text-authoring acceptance have separate native receipts. The
private full collector used explicit project-specific bounds and verified the
entire expected inventories; public synthetic traversal limits were not loosened.
This establishes a copy-only model-SP text route for this case, not a released
engineering revision or synchronization of its SPW documents.

Final independent discovery matched the initial empty document set and CAD
process identity. All owned documents were closed and the exclusive resource
was explicitly returned. The protected original tree, input archive and 68
installed package/type-library files were unchanged. The result package remains
private; only generic code, synthetic tests and this anonymized report are
published. Offline suite: **930 passed**, five existing SWIG warnings; Ruff and
sdist/wheel build passed.

This protocol does not remove obsolete references, collapse duplicate source
files, replace components or prove an arbitrary package portable across machines.
The additional copies are part of the tested layout and must be retained. Standard
installed resources remain declared runtime dependencies. Model-SP text acceptance
does not by itself update source/printed SPW documents or authorize replacing a
product's accepted engineering package. Installed SDK/configuration is unchanged.
