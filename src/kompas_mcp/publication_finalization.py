"""Offline publication plan and saved-evidence oracle. No CAD or file operations."""

import json
from typing import Annotated

from pydantic import Field, JsonValue, StrictBool, ValidationError

from .state_oracles import Evidence, Key, PositiveInt, _result
from .view_state import Sha256


class Library(Evidence):
    path: Key
    sha256: Sha256


class SpecificationPlan(Evidence):
    key: Key
    library: Library  # verified actual installed path, not merely a same-GUID clone
    descriptor_style: PositiveInt
    first_page_style: PositiveInt
    continuation_style: PositiveInt
    word_wrap: StrictBool
    rows_digest: Sha256


class DrawingPlan(Evidence):
    key: Key
    family: Key
    logical: PositiveInt
    family_total: PositiveInt
    library: Library  # independent CDW library policy
    mapped_stamp: dict[Key, str]
    preserved_semantics_digest: Sha256


class PublicationPlan(Evidence):
    common_specification: Key
    specifications: Annotated[list[SpecificationPlan], Field(min_length=1)]
    drawings: Annotated[list[DrawingPlan], Field(min_length=1)]
    original_hashes: dict[Key, Sha256]


def checked_plan(payload):
    p = PublicationPlan.model_validate(payload).model_copy(deep=True)
    keys = [s.key for s in p.specifications] + [d.key for d in p.drawings]
    if len(keys) != len(set(keys)) or p.common_specification not in {s.key for s in p.specifications}:
        raise ValueError('Explicit unique owned files and common specification required')
    if not p.original_hashes or set(keys) & p.original_hashes.keys():
        raise ValueError('Pinned originals must be distinct from the owned publication')
    for family in {d.family for d in p.drawings}:
        members = [d for d in p.drawings if d.family == family]
        total = members[0].family_total
        if (any(d.family_total != total for d in members) or len(members) != total
                or {d.logical for d in members} != set(range(1, total+1))):
            raise ValueError('One CDW per logical sheet requires complete unambiguous family numbering')
    for drawing in p.drawings:
        if (drawing.mapped_stamp.get('7') != str(drawing.logical)
                or drawing.mapped_stamp.get('8') != str(drawing.family_total)):
            raise ValueError('Mapped CDW Text7/Text8 must match explicit logical family numbering')
    return p


def finalization_order(payload):
    """Build explicit ordered phases; native execution requires an owned adapter.

    SPW save/readback may require separate reconciliation on mismatch. This plan
    never loops by itself, patches only a hash, or automatically reseals a failure.
    """
    p = checked_plan(payload)
    operations = [{'phase': 'finalize_common_format_and_save', 'key': p.common_specification}]
    for s in p.specifications:
        operations += [{'phase': 'finalize_spw_and_save', 'key': s.key},
                       {'phase': 'verify_saved_spw_pagination_header_library', 'key': s.key}]
    for d in p.drawings:
        operations.append({'phase': 'serialize_final_cdw_and_save', 'key': d.key,
                           'settings': {'SheetAutoNumber': False, 'SheetFirstNumber': d.logical,
                                        'SheetAutoCount': False, 'SheetsCount': d.family_total},
                           'stamp': dict(d.mapped_stamp), 'stamp_update_required': True})
    operations += [{'phase': 'seal_all_owned_files'}, {'phase': 'full_saved_ro_gate', 'cycle': 1},
                   {'phase': 'full_saved_ro_gate', 'cycle': 2}, {'phase': 'verify_final_hashes'}]
    return operations


class SpecificationState(Evidence):
    saved_api5_pages: PositiveInt
    layout_sheets: PositiveInt
    physical_sheet_numbers: list[PositiveInt]  # API5 GetStampEx(i+1).SheetNumb
    page_styles: list[PositiveInt]
    descriptor_style: PositiveInt
    text8: str
    raw_shared_text7: str  # diagnostic only, not a physical page-number oracle
    library: Library
    configured_library_path: Key
    word_wrap: StrictBool
    rows_digest: Sha256


class DrawingState(Evidence):
    sheet_auto_number: StrictBool
    sheet_first_number: PositiveInt
    sheet_auto_count: StrictBool
    sheets_count: PositiveInt
    physical_sheets: PositiveInt
    stamp: dict[Key, str]
    library: Library
    preserved_semantics_digest: Sha256


class SavedCycle(Evidence):
    open_id: Key
    read_only: StrictBool
    hashes: dict[Key, Sha256]
    original_hashes: dict[Key, Sha256]
    specifications: dict[Key, SpecificationState]
    drawings: dict[Key, DrawingState]


class FinalEvidence(Evidence):
    operations: list[dict[str, JsonValue]]  # exact detached operation sequence returned by finalization_order
    saved_spw_probes: dict[Key, SpecificationState]
    sealed_hashes: dict[Key, Sha256]
    cycles: Annotated[list[SavedCycle], Field(min_length=2, max_length=2)]
    final_hashes: dict[Key, Sha256]


def _spw(plan, actual):
    count = actual.saved_api5_pages
    if (actual.layout_sheets != count or actual.physical_sheet_numbers != list(range(1, count+1))
            or actual.text8 != str(count)
            or actual.page_styles != [plan.first_page_style] + [plan.continuation_style]*(count-1)
            or actual.descriptor_style != plan.descriptor_style
            or actual.library != plan.library or actual.configured_library_path != plan.library.path
            or actual.word_wrap != plan.word_wrap or actual.rows_digest != plan.rows_digest):
        raise ValueError('Saved SPW pagination/header/style/actual-library/rows mismatch')


def assess_finalized_publication(plan, evidence):
    try:
        p, e = checked_plan(plan), FinalEvidence.model_validate(evidence)
        if json.dumps(e.operations, sort_keys=True, allow_nan=False) != json.dumps(
                finalization_order(plan), sort_keys=True, allow_nan=False):
            raise ValueError('Finalization order differs; all SPW writes must precede final CDW serialization/seal')
        spw_keys, cdw_keys = {s.key for s in p.specifications}, {d.key for d in p.drawings}
        if e.saved_spw_probes.keys() != spw_keys:
            raise ValueError('Saved SPW readback is required before final CDW sealing')
        for s in p.specifications:
            _spw(s, e.saved_spw_probes[s.key])
        if e.sealed_hashes.keys() != spw_keys | cdw_keys or e.final_hashes != e.sealed_hashes:
            raise ValueError('Final byte seal is incomplete or changed after writeback')
        if len({c.open_id for c in e.cycles}) != 2:
            raise ValueError('Two distinct full saved RO observations required')
        for cycle in e.cycles:
            if (not cycle.read_only or cycle.hashes != e.sealed_hashes
                    or cycle.original_hashes != p.original_hashes
                    or cycle.specifications.keys() != spw_keys or cycle.drawings.keys() != cdw_keys):
                raise ValueError('RO scope/hash/source-preservation mismatch')
            for s in p.specifications:
                actual = cycle.specifications[s.key]
                _spw(s, actual)
                if actual != e.saved_spw_probes[s.key]:
                    raise ValueError('SPW repaginated or changed after final saved pagination probe')
            for d in p.drawings:
                a = cycle.drawings[d.key]
                if (a.sheet_auto_number or a.sheet_auto_count or a.physical_sheets != 1
                        or a.sheet_first_number != d.logical or a.sheets_count != d.family_total
                        or a.stamp != d.mapped_stamp or a.library != d.library
                        or a.preserved_semantics_digest != d.preserved_semantics_digest):
                    raise ValueError('Saved CDW settings/logical stamp/library/semantic mismatch')
    except (ValueError, ValidationError) as exc:
        return _result([str(exc)])
    return {**_result([]), 'dynamic_renumbering_verified': False,
            'package_portability_verified': False}
