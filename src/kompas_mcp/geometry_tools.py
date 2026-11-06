"""Register isolated project and native frame workflows on the existing worker."""

from . import body_diagnostics, collision_fixture, project_copy, sketch_frame


def register(mcp, worker):
    @mcp.tool()
    async def inspect_body_components(handle: str, max_faces: int = 5000) -> dict:
        """Read native disconnected-material flags and bounded own-body face graphs.

        No rebuild, rollback, edits or save. Retains canonical face identities and
        reports unknown neighbors/truncation as inconclusive. Measures boundary
        patch areas and edge-envelope bounds. Separate boundary shells can describe
        an internal cavity, so their count is never called a volumetric part count.
        Historical feature getters are deliberately skipped: they can dirty native
        caches even on read-only files. Causal investigation needs owned copies.
        """
        return await worker.call(lambda k: body_diagnostics.inspect_body_components(
            k, handle, max_faces
        ))

    @mcp.tool()
    async def create_isolated_copy(
        handle: str, destination: str, dry_run: bool = True, max_files: int = 5000,
    ) -> dict:
        """Copy a saved document's entire external dependency DAG into a new folder.

        Defaults to a no-write plan. Every source is copied once; native files
        are rebound bottom-up, saved/reopened and checked for outside links and
        occurrence transforms. Includes non-CAD resources and all SDK link types.
        Rejects unsaved sources, cycles, missing files and model-library paths.
        A failed apply returns a durable partial manifest, never false isolation.
        Never saves original documents. Cyclic specification links need a separate
        cycle-aware workflow; they are rejected before any copy is written.
        """
        return await worker.call(lambda k: project_copy.create_isolated_copy(
            k, handle, destination, dry_run, max_files
        ))

    @mcp.tool()
    async def create_collision_fixture(
        handle: str, occurrence_paths: list[list[int]], copy_root: str,
        destination: str, dry_run: bool = True,
    ) -> dict:
        """Flatten explicit file-backed nested occurrences into a top-level assembly.

        Source closure and destination must be inside copy_root. Rejects overlapping,
        excluded, mirrored/nonrigid and embedded inputs. Saves/reopens the fixture,
        verifies every composed world matrix and writes source/path/hash provenance.
        Does not run collisions or infer per-pair identity. Context-dependent cuts
        are not transferred by native source-file insertion; report that limitation.
        """
        return await worker.call(lambda k: collision_fixture.create_collision_fixture(
            k, handle, occurrence_paths, copy_root, destination, dry_run
        ))

    @mcp.tool()
    async def set_sketch_frame(
        handle: str, copy_root: str, name: str, translation: list[float], angle: float,
        expected_frame: dict | None = None, dry_run: bool = True,
    ) -> dict:
        """Set an isolated part sketch's absolute in-plane translation and angle.

        Dry run returns before/target frames. Apply requires that expected_frame,
        uses API5 SetLocation/angle and verifies API7 GetPoint3D origin and unit axes.
        Retains support/offset; no primitive-coordinate approximation. Intentionally
        changes world geometry, never asserts unchanged bounds/volume. Does not save;
        inspect downstream features and save/reopen before promoting the copy.
        """
        return await worker.call(lambda k: sketch_frame.set_sketch_frame(
            k, handle, copy_root, name, expected_frame, translation, angle, dry_run
        ))
