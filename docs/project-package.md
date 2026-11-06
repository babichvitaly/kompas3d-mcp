# Offline project package staging

`kompas_mcp.project_package` validates and stages an explicit set of files without
starting KOMPAS, importing COM, or rewriting a native document. The existing
`project_copy` module remains the native inspection/rebinding implementation.

```python
from kompas_mcp.project_package import preflight_package, materialize_package

plan = {
    "copy_mapping": [{
        "source": "/absolute/source/part.m3d",
        "source_sha256": "a complete expected SHA256",
        "destination_relative": "assets/part.m3d",
    }],
    "runtime_resources": [{
        "name": "STYLE.LYT",
        "policy": "Require the compatible installed style; verify during native preflight",
    }],
}
report = preflight_package(plan, "/existing/parent/new-project")
# No files or directories have been written by preflight.
report = materialize_package(plan, "/existing/parent/new-project")
assert report["phase"] == "files_staged_not_rebound"
assert report["portable"] is False
```

Use host-native absolute source paths and a new absolute destination whose parent
already exists. Each mapping requires `source`, `source_sha256` and
`destination_relative`; optional `source_bytes` is checked. No product names,
paths, dimensions or file-type assumptions are built into the implementation.

All source files are read and SHA-checked before destination creation. Symlinks
in source/destination ancestors are rejected. Relative targets reject traversal,
absolute/drive-relative/UNC paths, reserved Windows names, alternate data streams,
trailing dots/spaces, Unicode-normalized case-folding collisions and a file also
being another destination's parent directory. The `.cad-package` directory is
reserved for the ownership marker and atomic manifest. Staging never overwrites
an existing destination, including an earlier failed attempt.

Each copied file is verified against the same hash and its preflight identity;
all original sources are read again after copying. A source changed during
staging causes failure. This is a bounded file consistency check, not a global
filesystem snapshot or a lock on future source changes. Source protection and
exclusive native ownership still belong to the native caller.

Named-path `stat` and open-handle `fstat` metadata are compared within their own
channels before/after reading. The path and handle must agree on device/inode at
both boundaries. Their ctime fields are deliberately not compared across APIs:
Windows can expose different ctime values after a flushed NTFS write. The saved
preflight identity uses the named-path channel. Size, mtime, ctime and file identity
changes within a channel still fail, as does a path/handle identity mismatch;
independent pinned SHA checks are retained throughout staging.

An optional `dependency_graph` maps absolute planned source paths to explicit
lists of dependency paths. `roots` may contain several planned sources. External
installed resources are addressed as `resource:STYLE.LYT`, matching a named
`runtime_resources` declaration with an explicit `policy`. Unknown engineering
dependencies fail preflight. Cycles are reported explicitly; they do not prevent
safe byte staging, but no bottom-up rebind order is returned for a cyclic graph.
A partial supplied graph stays `supplied_partial_graph`; absent graph data stays
`not_scanned`. Even a complete supplied graph does not prove fresh native closure.
Resource declarations are not copied or marked verified by this offline module.

On an error after destination creation, `PackageMaterializationError.report`
contains `phase="files_staging_failed"`, ownership, attempted files and the error.
The directory is preserved for inspection. Its `.cad-package/manifest.json` is
updated atomically whenever possible; if writing the manifest itself fails, the
exception report records that too. A preflight error writes nothing. The caller
must never treat an interrupted/failed staging directory as ready or retry into
the same destination.

Native follow-up must inspect all model/specification/drawing roots, explicitly
resolve cycles and runtime resources, rebind only owned copies, verify UUID/BOM,
placements, geometry and native history, save and reopen, and then repeat from a
second location. Only that separate evidence can establish a relocatable project.
Successful staging alone does not establish usability, dynamic drawing updates,
geometric correctness, manufacturing approval or a speed improvement.
