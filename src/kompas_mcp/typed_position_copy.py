"""Typed IText.Assign orchestration and saved-evidence checks. No CAD connection."""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, JsonValue, StrictBool, TypeAdapter

from .state_oracles import Evidence, Key, NonnegativeInt, _result
from .view_state import Sha256


class PropertyField(Evidence):
    key: Key
    prop: Literal['position']
    type: Literal['partPropertyByKey']


class TextItem(Evidence):
    item_type: NonnegativeInt
    properties: dict[Key, JsonValue]
    property_field: PropertyField | None = None


class TextLine(Evidence):
    properties: dict[Key, JsonValue]
    items: list[TextItem]


class TypedText(Evidence):
    properties: dict[Key, JsonValue]
    lines: Annotated[list[TextLine], Field(min_length=1)]


class BackupIdentity(Evidence):
    path: Key
    sha256: Sha256
    owned: StrictBool
    read_only: StrictBool
    canonical_row_uuid: Key


class CopyPlan(Evidence):
    target_path: Key
    canonical_row_uuid: Key
    backup: BackupIdentity
    untouched_hashes: dict[Key, Sha256]


class RowLookup(Evidence):
    leader_uuid: Key
    matched_row_uuids: list[Key]
    included_in_row: StrictBool


def _snapshot(value, row_uuid):
    snapshot = TypedText.model_validate(value).model_copy(deep=True)
    fields = []
    for line in snapshot.lines:
        for item in line.items:
            if item.item_type == 8192:
                if item.property_field is None or item.property_field.key != row_uuid:
                    raise ValueError('Native property field identity missing or differs')
                fields.append(item.property_field)
            elif item.property_field is not None:
                raise ValueError('Property metadata attached to a non-field item')
    if not fields:
        raise ValueError('Typed text must contain a native position field, not a numeric literal')
    return snapshot


def _canonical(snapshot):
    return json.dumps(snapshot.model_dump(mode='json'), sort_keys=True, allow_nan=False)


def _plan(value):
    p = CopyPlan.model_validate(value).model_copy(deep=True)
    if (not p.backup.owned or not p.backup.read_only
            or p.backup.canonical_row_uuid != p.canonical_row_uuid
            or p.backup.path == p.target_path or p.target_path in p.untouched_hashes
            or p.untouched_hashes.get(p.backup.path) != p.backup.sha256):
        raise ValueError('Exact own RO backup/row identity and disjoint hash scope required')
    return p


def _binding(value, leader_uuid, row_uuid):
    lookup = RowLookup.model_validate(value)
    if (lookup.leader_uuid != leader_uuid or not lookup.included_in_row
            or lookup.matched_row_uuids != [row_uuid]):
        raise ValueError('Leader must belong to exactly the canonical native row')


def copy_position_field_owned(plan, target_leader, backup_leader, adapter):
    """Only target.Positions.Assign(backup.Positions), then target.Update.

    Adapter supplies cheap exact ownership/STA guards, typed snapshots, fresh
    native row lookup and read-only backup/hash checks. No delete/create, Str
    setter, ITextItem.Assign, COMMON Rebuild, Transmit, save, fallback or retry.
    """
    result = {'status': 'failed', 'operation': 'typed_position_copy', 'mutation_possible': False,
              'retry_allowed': False, 'saved': False, 'native_acceptance': 'pending'}
    phase = 'preflight'
    try:
        p = _plan(plan)
        required = ('guard_copy_scope', 'backup_identity', 'snapshot_text',
                    'leader_uuid', 'lookup_native_row', 'untouched_hashes')
        if any(not callable(getattr(adapter, name, None)) for name in required):
            raise TypeError('Incomplete typed-copy adapter')

        def guard():
            adapter.guard_copy_scope(p.model_copy(deep=True), target_leader, backup_leader)

        phase = 'backup_provenance'
        guard()
        if BackupIdentity.model_validate(adapter.backup_identity(backup_leader)) != p.backup:
            raise ValueError('RO backup path/hash/identity differs')
        if adapter.untouched_hashes() != p.untouched_hashes:
            raise ValueError('Unrelated files already differ before copy')
        phase = 'typed_backup_snapshot'
        source_text = backup_leader.Positions
        wanted = _snapshot(adapter.snapshot_text(source_text), p.canonical_row_uuid)
        before = _canonical(wanted)
        uuid = adapter.leader_uuid(target_leader)
        if not isinstance(uuid, str) or not uuid:
            raise ValueError('Expected exact target native UUID')
        phase = 'exact_native_row_before'
        _binding(adapter.lookup_native_row(target_leader), uuid, p.canonical_row_uuid)
        phase = 'IText.Assign'
        guard()
        result['mutation_possible'] = True
        if target_leader.Positions.Assign(source_text) is not True:
            raise ValueError('IText.Assign did not confirm typed copy')
        phase = 'leader.Update'
        guard()
        if target_leader.Update() is not True:
            raise ValueError('Leader.Update did not confirm commit')
        phase = 'typed_readback_and_native_row'
        guard()
        actual = _snapshot(adapter.snapshot_text(target_leader.Positions), p.canonical_row_uuid)
        if _canonical(actual) != before or adapter.leader_uuid(target_leader) != uuid:
            raise ValueError('Complete IText/ITextLine/ITextItem structure or leader UUID differs')
        _binding(adapter.lookup_native_row(target_leader), uuid, p.canonical_row_uuid)
        phase = 'backup_and_untouched_preservation'
        if (BackupIdentity.model_validate(adapter.backup_identity(backup_leader)) != p.backup
                or _canonical(_snapshot(adapter.snapshot_text(backup_leader.Positions),
                                        p.canonical_row_uuid)) != before
                or adapter.untouched_hashes() != p.untouched_hashes):
            raise ValueError('Backup or unrelated files changed during typed copy')
        guard()
        result.update(status='typed_copy_verified_in_adapter', leader_uuid=uuid,
                      typed_structure_sha256=hashlib.sha256(before.encode()).hexdigest())
    except Exception as exc:  # noqa: BLE001 - preserve partial mutation; never flatten/fallback/retry
        result.update(failed_phase=phase, error=f'{type(exc).__name__}: {exc}',
                      recovery='Reconcile the owned unsaved leader; do not repeat an uncertain mutation')
    return result


class SavedTypedCycle(Evidence):
    open_id: Key
    read_only: StrictBool
    target_path: Key
    target_sha256: Sha256
    typed_text: TypedText
    binding: RowLookup
    untouched_hashes: dict[Key, Sha256]


def assess_saved_typed_copy(plan, backup_snapshot, target_uuid, sealed_target_sha256, cycles):
    try:
        p = _plan(plan)
        sealed = TypeAdapter(Sha256).validate_python(sealed_target_sha256)
        target_uuid = TypeAdapter(Key).validate_python(target_uuid)
        expected = _canonical(_snapshot(backup_snapshot, p.canonical_row_uuid))
        observations = TypeAdapter(list[SavedTypedCycle]).validate_python(cycles)
        if len(observations) != 2 or len({c.open_id for c in observations}) != 2:
            raise ValueError('Two independent saved RO observations required')
        for c in observations:
            if (not c.read_only or c.target_path != p.target_path or c.target_sha256 != sealed
                    or c.untouched_hashes != p.untouched_hashes
                    or _canonical(_snapshot(c.typed_text, p.canonical_row_uuid)) != expected):
                raise ValueError('Saved typed field, target seal or unrelated hashes differ')
            _binding(c.binding, target_uuid, p.canonical_row_uuid)
    except ValueError as exc:
        return _result([str(exc)])
    return {**_result([]), 'dynamic_renumbering_verified': False, 'pdf_visual_acceptance': 'pending'}
