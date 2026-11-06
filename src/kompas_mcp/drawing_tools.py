"""Typed drawing operations; all native work stays on the existing COM worker."""

from . import drawings, view_state
from .view_state import ViewState


def register(mcp, worker):
    @mcp.tool()
    async def inspect_drawing_view_state(
        handle: str, view_number: int, max_objects: int = 50000,
    ) -> dict:
        """Read an associative camera, Unfold, pose, bounds and actual projected curves.

        Never activates, updates, rebuilds or saves. Rejects empty/invalid geometry,
        zero scale and missing source bytes. Disk SHA is provenance, not proof of
        regeneration. References are session-local; state can be compared after RO
        reopen. Coverage is line segments, circles and arcs, not all 2D object types.
        """
        return await worker.call(lambda k: view_state.inspect_view_state(
            k, handle, view_number, max_objects
        ))

    @mcp.tool()
    async def compare_drawing_view_state(
        handle: str, view_number: int, expected: ViewState, max_objects: int = 50000,
    ) -> dict:
        """Reinspect and compare against an explicit typed state, including camera/Unfold.

        Returns matches/differences; it does not repair mismatches or certify saved
        or visual results. Each independent RO cycle must be performed separately.
        """
        return await worker.call(lambda k: view_state.compare_view_state(
            k, handle, view_number, expected.model_dump(mode="json"), max_objects
        ))

    @mcp.tool()
    async def find_visible_view_anchor(
        handle: str, view_number: int, source_document_handle: str, component_handle: str,
        expected_fingerprint: str, near_point: tuple[float, float] | None = None,
        max_objects: int = 5000,
    ) -> dict:
        """Resolve a real visible component curve through native AssociationObjects.

        Requires an already-current view and a clean explicit source document;
        component handle must have that document's scope. Does not activate or
        repair pose. Matches native visibility, owner view, Valid and non-Temp;
        line/circle candidates only. near_point is view-space XY, not source XYZ.
        A projection coordinate alone is never accepted. Re-resolve after any
        update/reopen; returned native reference is not a persistent feature ID.
        """
        return await worker.call(lambda k: view_state.find_visible_anchor(
            k, handle, view_number, source_document_handle, component_handle,
            expected_fingerprint, near_point, max_objects
        ))

    @mcp.tool()
    async def inspect_drawing(
        handle: str, include_geometry: bool = True, report_path: str | None = None,
        max_objects: int = 50000,
    ) -> dict:
        """Inventory native views, linear dimensions, editable text, leaders and stamp.

        Read only: no activation, rebuild or save. Includes line/circle/arc geometry
        and a stale-plan fingerprint by default. Other 2D geometry is outside the
        quantitative coverage. Optional JSON report must be a new absolute path.
        """
        return await worker.call(lambda k: drawings.inspect_drawing(
            k, handle, include_geometry, report_path, max_objects
        ))

    @mcp.tool()
    async def rebind_drawing_views(
        handle: str, copy_root: str, replacements: list[dict], expected_fingerprint: str,
        dimension_changes: list[dict] | None = None, view_changes: list[dict] | None = None,
        geometry_checks: list[dict] | None = None, dry_run: bool = True,
        report_path: str | None = None,
        remove_new_auto_captions: list[int] | None = None,
    ) -> dict:
        """Rebind existing associative views on a saved owned drawing copy; dry run default.

        Each replacement: view_number, expected_source, source. Sources and drawing
        must exist inside copy_root. Each view needs a geometry_check: view_number
        plus line_bounds [xmin,ymin,xmax,ymax], geometry_digest, or angle (degrees
        from X) with min_length/min_angle_count; optional tolerance <=0.1 and
        different_from_before. A line count or successful Rebuild alone is inadequate.

        Optional dimension_changes: view_number, index, expected (full inspected
        dimension), endpoints (only X1/Y1/X2/Y2), expected_after (all X1/Y1/X2/Y2/
        X3/Y3/Orientation/NominalValue). Native automatic view shifts need explicit
        view_changes: view_number, expected_x, expected_y. No automatic repositioning.

        Preserves view/dimension identities, editable text, leader identities,
        sheet/stamp content; rejects unexpected changes. Does not save or reopen.
        Optional remove_new_auto_captions explicitly lists rebound view numbers.
        Only NEW native IViewDesignation.DrawingText scale-only markup matching
        the view scale can be deleted; every existing text/caption is protected.
        Before-cleanup snapshot and exact removed identities/markup are reported.
        Default strict mode deletes nothing. Other new user text still fails.
        A failed mutation leaves its partial copy inspectable; discard/reconcile
        before retry. Save/reopen and render exports separately before promotion.
        """
        return await worker.call(lambda k: drawings.rebind_drawing_views(
            k, handle, copy_root, replacements, expected_fingerprint, dimension_changes,
            view_changes, geometry_checks, dry_run, report_path, remove_new_auto_captions
        ))

    @mcp.tool()
    async def export_drawing(
        handle: str, copy_root: str, paths: list[str], report_path: str | None = None,
    ) -> dict:
        """Export a saved owned CDW copy to new PDF/DXF paths within copy_root.

        Refuses dirty documents and existing outputs. Native API5 ASCII DXF export
        and installed Pdf2d manifest command; scoped HideMessage=No restored in
        finally. Parses PDF pages/content and DXF EOF/ENTITIES/DIMENSION counts,
        hashes all dependencies and verifies unchanged files. The native converter
        can close or replace its input document: observes/reconciles this lifecycle,
        reopens only the owned copy with matching read-only/visibility flags, checks
        complete inventoried contents and returns fresh document_after_export.
        Callers must refresh their document handle from this returned information.
        Native close/reopen effects are explicit in native_lifecycle receipts.
        Retains partial outputs on failure with a durable report when requested.
        Never saves the drawing or closes user documents.
        Structural checks do not certify visual layout; render/inspect separately.
        """
        return await worker.call(lambda k: drawings.export_drawing(
            k, handle, copy_root, paths, report_path
        ))
