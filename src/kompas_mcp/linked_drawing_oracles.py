"""Offline saved-evidence contracts for linked positions and dimension anchors."""

from typing import Annotated, Literal

from pydantic import Field, StrictBool, ValidationError, model_validator

from .state_oracles import Evidence, Key, NonnegativeInt, _result
from .view_state import Finite, Sha256, rotation_matrix


class CanonicalView(Evidence):
    source: Key
    source_sha256: Sha256
    owner: Key  # stable collector-owned view identity, not a transient COM Reference
    matrix: list[Finite]
    scope: Literal['canonical_view'] = 'canonical_view'
    part_uuid: None = None  # never fabricate a part identity from a view-level trace

    @model_validator(mode='after')
    def valid_matrix(self):
        rotation_matrix(self.matrix)
        return self


class GeometryRow(Evidence):
    native_uuid: str
    raw_reference: str
    valid: StrictBool
    generated: StrictBool
    geometry_digest: Sha256


def valid_geometry(rows):
    """Ignore unstable invalid refs; never silently drop valid generated geometry."""
    result = {}
    for row in rows:
        if not row.valid:
            continue
        if not row.native_uuid or row.native_uuid in result:
            raise ValueError('Missing/ambiguous valid geometry UUID')
        result[row.native_uuid] = row.geometry_digest
    if not result:
        raise ValueError('No valid geometry evidence')
    return result


class Anchor(Evidence):
    view: CanonicalView
    native_uuid: Key
    lookup_uuid: Key  # UUID actually returned by exact native UUID lookup
    point: Annotated[tuple[Finite, Finite], Field(strict=False)]
    point_on_curve: StrictBool
    valid: StrictBool
    temp: StrictBool
    in_association_view: StrictBool
    visible_in_association_view: StrictBool
    is_curve: StrictBool
    is_geometry_object: StrictBool


class Endpoint(Evidence):
    end: Literal['first', 'second']
    direct: StrictBool
    constraint_valid: StrictBool
    anchor: Anchor


class Dimension(Evidence):
    native_uuid: Key
    endpoints: Annotated[list[Endpoint], Field(min_length=2, max_length=2)]


class Position(Evidence):
    native_uuid: Key
    specification_object_uuid: Key
    property_key: Key
    semantic_digest: Sha256  # pinned non-text getters/metadata
    text: str
    valid: StrictBool


class Cycle(Evidence):
    open_id: Key
    read_only: StrictBool
    steps: list[Literal['read_saved_specification', 'read_saved_drawing']]
    hashes: dict[Key, Sha256]
    positions: list[Position]
    dimensions: list[Dimension]
    geometry: list[GeometryRow]


class LinkedEvidence(Evidence):
    expected_view: CanonicalView
    expected_positions: Annotated[list[Position], Field(min_length=1)]
    expected_dimensions: Annotated[list[Dimension], Field(min_length=1)]
    baseline_geometry: Annotated[list[GeometryRow], Field(min_length=1)]
    live_positions: list[Position]
    update_return: StrictBool  # neither True nor False decides acceptance
    live_changed: StrictBool  # never used as an on-disk seal
    hashes_before_writeback: dict[Key, Sha256]
    owned_files: Annotated[list[Key], Field(min_length=1)]
    write_steps: list[Literal['save_specification', 'rebuild_specification', 'transmit',
                             'writeback_complete', 'seal']]
    sealed_hashes: dict[Key, Sha256]
    original_hashes_before: dict[Key, Sha256]
    original_hashes_after: dict[Key, Sha256]
    association_query_target: Literal['not_called', 'explicit_occurrence']
    association_query_attempts: NonnegativeInt
    cycles: Annotated[list[Cycle], Field(min_length=2, max_length=2)]


def _unique(rows):
    by_uuid = {r.native_uuid: r for r in rows}
    if len(by_uuid) != len(rows):
        raise ValueError('Ambiguous native UUID')
    return by_uuid


def _positions(expected, actual, resolved):
    expected, actual = _unique(expected), _unique(actual)
    if expected.keys() != actual.keys():
        raise ValueError('Position UUID set differs')
    for uuid, wanted in expected.items():
        got = actual[uuid]
        if not wanted.valid or not got.valid:
            raise ValueError('Invalid position')
        if wanted.model_dump(exclude={'text'}) != got.model_dump(exclude={'text'}):
            raise ValueError('Position semantic getters/UUID metadata differ')
        if resolved and (not wanted.text.strip() or '?' in wanted.text or got.text != wanted.text):
            raise ValueError('Saved RO position text is unresolved or differs')


def _dimensions(expected, actual, view, geometry):
    expected, actual = _unique(expected), _unique(actual)
    if expected.keys() != actual.keys():
        raise ValueError('Dimension UUID set differs')
    for uuid, wanted in expected.items():
        got = actual[uuid]
        if got != wanted:
            raise ValueError('Saved endpoint constraints differ')
        if {ep.end for ep in got.endpoints} != {'first', 'second'}:
            raise ValueError('Both dimension ends require direct constraints')
        for ep in got.endpoints:
            a = ep.anchor
            if (not ep.direct or not ep.constraint_valid or a.view != view
                    or a.native_uuid != a.lookup_uuid or a.native_uuid not in geometry
                    or not a.point_on_curve or not a.valid or a.temp or not a.in_association_view
                    or not a.visible_in_association_view or not a.is_curve
                    or not a.is_geometry_object):
                raise ValueError('Invalid direct associative endpoint/UUID lookup')


def assess_linked_drawing(payload):
    """Check claims, not native execution, dynamic following or package portability."""
    try:
        e = LinkedEvidence.model_validate(payload)
        owned = set(e.owned_files)
        if len(owned) != len(e.owned_files) or owned != e.sealed_hashes.keys():
            raise ValueError('Seal must cover exactly the unique owned file set')
        if (set(e.hashes_before_writeback) != owned or not e.original_hashes_before
                or e.original_hashes_before != e.original_hashes_after
                or owned & e.original_hashes_before.keys()):
            raise ValueError('Original/owned provenance mismatch')
        if e.write_steps != ['save_specification', 'rebuild_specification', 'transmit',
                             'writeback_complete', 'seal']:
            raise ValueError('Seal must follow completed writeback')
        attempts = 0 if e.association_query_target == 'not_called' else 1
        if e.association_query_attempts != attempts:
            raise ValueError('No automatic root query or blind retry')
        geometry = valid_geometry(e.baseline_geometry)
        _positions(e.expected_positions, e.live_positions, resolved=False)
        if len({c.open_id for c in e.cycles}) != 2:
            raise ValueError('Two distinct saved RO cycles required')
        for cycle in e.cycles:
            if (not cycle.read_only or cycle.steps != ['read_saved_specification', 'read_saved_drawing']
                    or cycle.hashes != e.sealed_hashes):
                raise ValueError('RO order or post-seal hashes differ')
            actual_geometry = valid_geometry(cycle.geometry)
            if actual_geometry != geometry:
                raise ValueError('Valid geometry changed')
            _positions(e.expected_positions, cycle.positions, resolved=True)
            _dimensions(e.expected_dimensions, cycle.dimensions, e.expected_view, actual_geometry)
    except (ValidationError, ValueError) as exc:
        return _result([str(exc)])
    result = _result([])
    result.update(trace_scope='canonical_view', dynamic_renumbering_verified=False,
                  arrow_following_verified=False, package_portability_verified=False)
    return result
