"""Register broad SDK and document-scoped native operations without a second server."""

from typing import Literal

from . import assemblies, audit, bridge, collisions, documents, features, parameters, sketches
from .advanced_models import ApiBatch, EdgeTreatment, FeatureSettings


def register(mcp, worker):
    @mcp.tool()
    async def place_components(
        handle: str, copy_root: str, placements: list[dict], dry_run: bool = True,
    ) -> dict:
        """Move explicit immediate components on an isolated assembly copy.

        Each change has index, expected (old 16-value matrix), and matrix (new).
        Uses SDK row-vector convention; only rigid rotations/translations. Defaults
        to dry run. Preserves fixed flags, sources and every unselected placement.
        Does not save or solve mates; verify interference and save/reopen separately.
        Partial failure requires discarding the owned copy's in-memory changes.
        """
        return await worker.call(lambda k: assemblies.place_components(
            k, handle, copy_root, placements, dry_run
        ))

    @mcp.tool()
    async def rebind_component_sources(
        handle: str, copy_root: str, replacements: dict[str, str], dry_run: bool = True,
    ) -> dict:
        """Replace explicit immediate component sources on an isolated assembly copy.

        Dry run defaults true. Both old/new sources and every assembly dependency
        must be inside copy_root. Save/rebuild subassemblies bottom-up first. Checks
        every immediate placement matrix and source after rebuild. Does not save,
        infer replacements, validate mates or certify body geometry. A partial
        failure requires discarding the owned in-memory assembly copy.
        """
        return await worker.call(lambda k: assemblies.rebind_sources(
            k, handle, copy_root, replacements, dry_run
        ))

    @mcp.tool()
    async def constrain_sketch(
        handle: str, copy_root: str, name: str, expected_geometry: dict,
        prefix: str = "Layout", dry_run: bool = True,
    ) -> dict:
        """Parameterize one unconstrained line/circle/arc sketch on an isolated copy.

        Default dry run returns a coordinate layout plan. Explicit apply uses one
        datum point, coincidences, axis alignments and editable driving dimensions;
        no primitive is frozen. Requires the expected geometry inventory. Verifies
        every primitive remains unchanged. Does not save or infer design intent,
        tangencies or manufacturing equations. On failure discard the owned copy's
        in-memory changes before retrying. Verify/reopen the part before promotion.
        """
        return await worker.call(lambda k: sketches.constrain_sketch(
            k, handle, copy_root, name, expected_geometry, prefix, dry_run
        ))

    @mcp.tool()
    async def inspect_sketches(
        handle: str, copy_root: str, names: list[str] | None = None,
        report_path: str | None = None,
    ) -> dict:
        """Read native sketch lines/circles/arcs and constraint states in one STA task.

        Requires an isolated part copy. Names must be unambiguous. Exports native
        FRW snapshots under copy_root/sketch-inventory and reads them read-only,
        avoiding source edit mode. References belong to snapshots, not the source.
        Verifies source constraint/dirty states. Does not save the source. An
        optional new JSON report preserves geometry and copied constraint data.
        """
        return await worker.call(
            lambda k: sketches.inspect_sketches(k, handle, copy_root, names, report_path)
        )

    @mcp.tool()
    async def check_collisions(
        handle: str, paths1: list[list[int]], paths2: list[list[int]], copy_root: str,
        assembly_as_one: bool = True, limit: int = 200,
    ) -> dict:
        """Exact collision counts on isolated copies, using explicit occurrence index paths.

        Verifies the entire dependency tree is inside copy_root, including excluded
        sources. Removes its own temporary diagnostic. Does not save; Changed may
        become true. Native ghost endpoints are explicitly inconclusive. A zero
        scoped count is not a universal certificate for nested selections or fit.
        Empty paths2 checks all selections in paths1 against each other.
        """
        return await worker.call(lambda k: collisions.check_collisions(
            k, handle, paths1, paths2, copy_root, assembly_as_one, limit
        ))

    @mcp.tool()
    async def audit_model(
        handle: str, report_dir: str, include_excluded: bool = False, max_nodes: int = 10000
    ) -> dict:
        """Audit occurrence paths, recursive feature states, dependencies and own bodies.

        Reads cached native state without rebuilding, saving or activating documents.
        report_dir must be a new absolute directory. Detailed JSONL and durable progress
        stay on disk; only a compact summary is returned. Does not certify geometry.
        """
        return await worker.call(
            lambda k: audit.audit_model(k, handle, report_dir, include_excluded, max_nodes)
        )

    @mcp.tool()
    def read_audit_report(report_dir: str, offset: int = 0, limit: int = 100) -> dict:
        """Read persisted audit progress and a bounded page, including after client reconnection."""
        return audit.read_report(report_dir, offset, limit)

    @mcp.tool()
    async def draw_line(
        drawing_handle: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        style: int = 1,
        view_number: int = 0,
    ) -> dict:
        """Draw a native editable line in a drawing/fragment view; coordinates in mm."""
        return await worker.call(
            lambda k: documents.draw_line(k, drawing_handle, x1, y1, x2, y2, style, view_number)
        )

    @mcp.tool()
    async def draw_circle(
        drawing_handle: str, x: float, y: float, radius: float, style: int = 1, view_number: int = 0
    ) -> dict:
        """Draw a native editable circle in a drawing/fragment view; radius in mm."""
        return await worker.call(
            lambda k: documents.draw_circle(k, drawing_handle, x, y, radius, style, view_number)
        )

    @mcp.tool()
    async def draw_linear_dimension(
        drawing_handle: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        text_x: float,
        text_y: float,
        orientation: Literal["horizontal", "vertical", "parallel"] = "parallel",
        view_number: int = 0,
    ) -> dict:
        """Create a native measured 2D linear dimension between points, with chosen text location."""
        return await worker.call(
            lambda k: documents.draw_linear_dimension(
                k, drawing_handle, x1, y1, x2, y2, text_x, text_y, orientation, view_number
            )
        )

    @mcp.tool()
    async def draw_text(
        drawing_handle: str, text: str, x: float, y: float, angle: float = 0, view_number: int = 0
    ) -> dict:
        """Add native editable text to a drawing/fragment view; position mm and angle degrees."""
        return await worker.call(
            lambda k: documents.draw_text(k, drawing_handle, text, x, y, angle, view_number)
        )

    @mcp.tool()
    async def list_variables(document_id: str, feature_id: str | None = None) -> dict:
        """Read user variables or a specific native feature's driving variables and expressions."""
        return await worker.call(lambda k: parameters.list_variables(k, document_id, feature_id))

    @mcp.tool()
    async def set_variable(
        document_id: str,
        name: str,
        value: float | None = None,
        expression: str | None = None,
        feature_id: str | None = None,
        create: bool = False,
        note: str = "",
    ) -> dict:
        """Set one numeric value OR native expression and rebuild. Explicit create enables new user variables."""
        return await worker.call(
            lambda k: parameters.set_variable(
                k, document_id, name, value, expression, feature_id, create, note
            )
        )

    @mcp.tool()
    async def set_material(document_id: str, name: str, density_g_cm3: float) -> dict:
        """Assign a part material and physical density in g/cm³, then report updated mass in kg."""
        return await worker.call(
            lambda k: parameters.set_material(k, document_id, name, density_g_cm3)
        )

    @mcp.tool()
    async def list_documents(details: bool = False) -> dict:
        """List document identity/state cheaply; expand typed model/view handles with details=true."""
        return await worker.call(lambda k: documents.list_documents(k, details),
                                 name="list_documents")

    @mcp.tool()
    async def create_document(kind: documents.DocumentKind, visible: bool = True) -> dict:
        """Create a native part, assembly, drawing, fragment, specification or text document.

        Returns API7 handles; use create_part when you need a document_id for typed API5 modeling tools.
        """
        return await worker.call(lambda k: documents.create_document(k, kind, visible))

    @mcp.tool()
    async def open_document(
        path: str, read_only: bool = False, visible: bool = True, reuse_existing: bool = True
    ) -> dict:
        """Open/reuse a canonical native path. Reject an existing writable doc if read-only requested."""
        return await worker.call(
            lambda k: documents.open_document(k, path, read_only, visible, reuse_existing)
        )

    @mcp.tool()
    async def save_document(handle: str, path: str, overwrite: bool = False) -> dict:
        """Save a native API7 document. Enforces matching extension, read-only state and overwrite policy."""
        return await worker.call(lambda k: documents.save_document(k, handle, path, overwrite))

    @mcp.tool()
    async def close_document(handle: str, discard_changes: bool = False) -> dict:
        """Close this document only. Refuses unsaved changes unless discard_changes is explicitly true."""
        return await worker.call(lambda k: documents.close_document(k, handle, discard_changes))

    @mcp.tool()
    async def insert_component(assembly_handle: str, path: str, linked: bool = True) -> dict:
        """Insert a native part/subassembly occurrence in an explicit assembly. Returns placement handle."""
        return await worker.call(
            lambda k: documents.insert_component(k, assembly_handle, path, linked)
        )

    @mcp.tool()
    async def create_standard_views(
        drawing_handle: str,
        model_path: str,
        projections: list[Literal["front", "rear", "top", "bottom", "left", "right", "isometric"]],
        x: float = 100,
        y: float = 150,
        scale: float = 1,
        gap_x: float = 30,
        gap_y: float = 30,
        orientation: str = "",
        draft_projection: bool = False,
    ) -> dict:
        """Create and verify associative views using exact projection by default.

        Coordinates/gaps are mm. draft_projection=true selects the SDK's draft
        projection mode. Empty/invalid views are reported as errors; any partial
        views remain for inspection. Returns handles and object counts for new views.
        """
        return await worker.call(
            lambda k: documents.create_standard_views(
                k, drawing_handle, model_path, projections, x, y, scale, gap_x, gap_y,
                orientation, draft_projection
            )
        )

    @mcp.tool()
    async def api_catalog(
        query: str = "",
        library: Literal["kAPI5", "kAPI7"] | None = None,
        offset: int = 0,
        limit: int = 40,
    ) -> dict:
        """Search/paginate every installed API5/API7 interface by name; discover hidden capabilities."""
        return await worker.call(lambda k: bridge.catalog(k, query, library, offset, limit))

    @mcp.tool()
    async def api_describe_interface(library: Literal["kAPI5", "kAPI7"], interface: str) -> dict:
        """Get schema for any installed interface without needing an object of that type first."""
        return await worker.call(
            lambda k: bridge.describe_type(bridge.interface_type(k, library, interface))
        )

    @mcp.tool()
    async def api_cast(
        handle: str, interface: str, library: Literal["kAPI5", "kAPI7"] = "kAPI7"
    ) -> dict:
        """QueryInterface to an additional installed SDK interface, e.g. IPart7 to IModelContainer.

        A known type does not guarantee that a given object supports it. COM failure is reported.
        """
        return await worker.call(lambda k: bridge.cast(k, handle, library, interface))

    @mcp.tool()
    async def api_batch(plan: ApiBatch) -> dict:
        """Execute up to 100 ordered SDK steps; stop on first failure and return partial results.

        Targets/arguments support {handle:id}, {ref:prior_step_id}, {constant:enum_name}.
        Typed arrays: {variant:{type:dispatch_array|int_array|double_array|variant_array,values:[...]}}.
        Set expect=truthy for BOOL operations or not_null for object creation. No rollback.
        This has the same unrestricted local COM authority as api_invoke.
        """
        return await worker.call(lambda k: bridge.batch(k, plan))

    @mcp.tool()
    async def list_entities(
        document_id: str,
        kind: str = "o3d_unknown",
        offset: int = 0,
        limit: int = 100,
        solid_only: bool = True,
        snapshot_id: str | None = None,
    ) -> dict:
        """Discover existing native entities, including imported/reopened models.

        kind is an installed o3d_ enum, e.g. o3d_edge, o3d_face, o3d_fillet.
        Edges include endpoint/bounds/length data; faces include area/surface type/bounds.
        solid_only defaults true to exclude sketch and datum geometry from edges/faces.
        Select by geometric evidence. Rediscover topology after modifications.
        """
        return await worker.call(
            lambda k: features.entities(k, document_id, kind, offset, limit, solid_only, snapshot_id)
        )

    @mcp.tool()
    async def create_feature(
        document_id: str, entity_type: str, settings: FeatureSettings, name: str = "Feature"
    ) -> dict:
        """Create any API5 NewEntity-supported feature using documented definition settings.

        entity_type is an o3d_ enum. properties maps writable names to values.
        calls contain member/arguments/expect and optional via zero-argument getters.
        References: {entity_id:id} within this document, {handle:id}, {constant:name}.
        Used for shells, lofts, sweeps, ribs, drafts, patterns, mirrors and more.
        API7-only operations require api_cast/api_batch. Read SDK first; no universal recipe is implied.
        """
        return await worker.call(
            lambda k: features.create(k, document_id, entity_type, name, settings)
        )

    @mcp.tool()
    async def update_feature(document_id: str, entity_id: str, settings: FeatureSettings) -> dict:
        """Modify an existing native feature definition and rebuild the model. Partial changes may remain on failure."""
        return await worker.call(lambda k: features.update(k, document_id, entity_id, settings))

    @mcp.tool()
    async def set_entity_state(
        document_id: str,
        entity_id: str,
        name: str | None = None,
        hidden: bool | None = None,
        excluded: bool | None = None,
    ) -> dict:
        """Rename, hide/show, or suppress/restore a native entity and rebuild."""
        return await worker.call(
            lambda k: features.state(k, document_id, entity_id, name, hidden, excluded)
        )

    @mcp.tool()
    async def delete_feature(document_id: str, entity_id: str) -> dict:
        """Delete the explicitly selected native feature. Dependents may be affected.

        Rejects face/edge/vertex deletion because API5 would silently delete its owner.
        """
        return await worker.call(lambda k: features.delete(k, document_id, entity_id))

    @mcp.tool()
    async def treat_edges(document_id: str, spec: EdgeTreatment) -> dict:
        """Fillet or chamfer selected current edges. size is radius or first chamfer leg in mm.

        second_size defaults to equal chamfer legs. Edges are IDs from list_entities(o3d_edge).
        """
        return await worker.call(lambda k: features.edge_treatment(k, document_id, spec))
