# Synthetic versioned ZIP pack benchmark and helper decision

Decision: keep Git-pack optimization an **explicit, measured publication experiment**.
Do not add it to project staging, CAD operations or every release. A full external
pack with a bitmap can greatly shrink ordinary thin output, leave it unchanged,
or make it much larger. A production helper is deferred; the synthetic benchmark
and regression are available now. No existing repository is accepted as input.

## Current SDK boundary and criteria

`project_package.py` validates explicit file mappings, dependency declarations,
SHA checks and new-directory staging. It does not build ZIPs or push Git refs.
That boundary is retained. Must-haves: preserve sources/config/refs/index,
no automatic repack/prune/reset, no network writes, exact receiver reconstruction,
and compare actual ordinary thin bytes before selecting a candidate. Preparation
CPU/disk and Git-version sensitivity are additional decision criteria.

## Measured matrix

Synthetic fixture: 24 deterministic pseudorandom 256 KiB payloads, ZIP_DEFLATED;
one payload changes, both internal root folder names change. Base ZIP has one
additional payload in the shrinking cases. New ZIP: 6,296,998 bytes. Unrelated
case replaces all payloads. Fixed archive timestamps and commit dates.

Both Apple Git 2.54.0 (Apple Git-157) and Homebrew Git 2.56.0 produced these sizes
in bytes. These are measured pack streams for `new ^base`, not network traffic or
an estimate for an arbitrary remote's advertised haves.

| Fixture | Baseline thin | Pair cache only | Full without bitmap | Full with bitmap |
|---|---:|---:|---:|---:|
| Renamed archive, larger new ZIP, different suffixes | 6,297,663 | 6,297,663 | 6,297,663 | 6,297,663 |
| Same pathname, changed internal root | 265,494 | 265,494 | 265,494 | 6,297,625 |
| Renamed archive, unrelated contents | 6,297,654 | 6,297,654 | 6,297,654 | 6,297,654 |
| Renamed, same long suffix, smaller new ZIP | 6,297,672 | 6,297,672 | 6,297,672 | 265,564 |

The positive case reduces the stream by 95.78% (23.71x). Disabling bitmap use in
the same external cache returns 6,297,672 bytes. The stable-path counterexample
increases output by about 23.72x; disabling bitmap restores 265,494 bytes.
These changes affect transmission representation, not ZIP content.

`verify-pack` shows why size alone is insufficient: in the first case the old
ZIP is a delta of the new ZIP. That cannot reduce transmission of the new blob.
A useful candidate needs the new blob represented against a receiver-held base.
In the positive case the full pack holds precisely that relation. This mechanism
is an inference supported by the stored delta-base rows and bitmap-disable control.

An additional shrinking fixture with different suffixes tests a pair-seeded full
pack. Pair cache by itself is still ineffective. Its delta can be reused during
full-pack construction, then a bitmap permits a small thin stream; the extra
pair and full packs approximately double cache storage. Consult the JSON rows
for these variants, preparation time and cache size; they are not recommendations
to warm every repository.

## Procedure and evidence

`scripts/benchmark_zip_packs.py` creates a new disposable synthetic repository and
uses process-local, isolated Git environment values. It accepts only a new output
directory, a Git executable and a fixture scenario, never a production repo path.
System/global Git configuration is excluded; no user's configuration is rewritten.
All experiment directories remain available on failure.

For each independent variant, `GIT_OBJECT_DIRECTORY` points to a new external
cache and `GIT_ALTERNATE_OBJECT_DIRECTORIES` reads the source object directory.
Full cache command: `pack-objects --all --revs --write-bitmap-index <external-prefix>`.
Pair input contains the two synthetic blob IDs. All cached packs are checked by
`index-pack --verify` and `verify-pack`; bitmap variants also run
`rev-list --test-bitmap <new>`. No `--use-bitmap-index` is explicitly enabled for
the ordinary stream:

```text
pack-objects --revs --stdout --thin --delta-base-offset
stdin: <new commit> followed by ^<base commit>
```

A fresh bare local receiver is seeded with **only base history**, then consumes
the stream through `index-pack --stdin --fix-thin`. Reading the new commit's ZIP
must reproduce its bytes exactly. It has no alternate access to the source/new
blob. Hash snapshots compare every file in the synthetic source repository before
and after all measurements, including HEAD, refs, config, index, worktree and
object files. This is a content/path check, not a timestamp comparison.

Raw source-free results: [matrix](benchmarks/git-zip-packs-20261107.json).
Preparation timing covers cache pack generation (including pair seeding where
used); verification, fixture creation and receiver reconstruction are additional
costs. Local 6 MiB timings do not predict costs for a large production history.
No remote push or receive-pack negotiation was performed.

## Proposed safe helper, before implementation

1. Explicit opt-in publication command, separate from CAD. Accept pinned new tip,
   receiver-have/base IDs, Git executable and a fresh private owned cache root.
   Reject unsupported shallow/partial/missing-object or linked-worktree layouts
   until separately tested; snapshot the actual common Git directory as well as
   working-tree metadata. Do not silently change pack/window/config heuristics.
2. Measure the baseline with exactly the intended revision input. Build external
   candidates with read-only alternates; bound time/disk and leave failed evidence.
   Inspect delta direction, verify packs/bitmap and reconstruct in a base-only
   receiver. Never infer effectiveness merely from a pairpack's compressed size.
3. Measure ordinary candidate thin output, compare with baseline, and select only
   a verified improvement within the preparation/storage budget. If remote haves
   or local refs change, expire the result and remeasure. No helper should prune,
   reset, install a cache in the source store, change config or publish by itself.
4. Before any separately authorized push, retain a source-state receipt and
   preserve the external cache through the consuming process. Re-check source
   state after execution. Network transport/remote acceptance and ref verification
   are separate evidence. Cache cleanup must target only its own marked directory.

Production helper implementation is deferred because this experiment intentionally
does not establish real negotiation, linked-worktree/shallow/partial clone behavior,
concurrency safety, filesystem permissions or representative large-history cost.

## Primary sources and interpretation

Git documents thin packs and `index-pack --fix-thin`, object grouping by name hash,
size heuristics, and reuse of stored deltas whose bases the receiver has.
[git-pack-objects](https://git-scm.com/docs/git-pack-objects).
Git defines the external object directory and read-only alternate search semantics.
[Git environment variables](https://git-scm.com/docs/git#Documentation/git.txt-GITOBJECTDIRECTORY).
These are mechanism references, not a guarantee of byte savings; the matrix above
is direct synthetic evidence from the two installed executables.
