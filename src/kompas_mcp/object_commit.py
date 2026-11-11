"""Offline object-level mutation -> own Update -> Save -> two RO contract."""

import json
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictStr, ValidationError

from .state_oracles import Evidence, Key, NonnegativeInt, _result
from .view_state import Finite, Sha256

Value = StrictBool | StrictStr | Finite
Properties = dict[Key, Value]


class ChangedObject(Evidence):
    key: Key  # fully scoped stable document/view/layer identity, not a cached COM ref
    interface: Literal['ILayer', 'IView', 'IDrawingObject']
    expected: Properties


class Setter(Evidence):
    target: Key
    property: Key
    value: Value
    epoch: NonnegativeInt


class OwnUpdate(Evidence):
    target: Key
    epoch: NonnegativeInt
    returned: StrictBool  # observed, never substitutes for saved persistence


class SavedProperties(Evidence):
    open_id: Key
    epoch: NonnegativeInt
    read_only: StrictBool
    artifact_sha256: Sha256
    objects: dict[Key, Properties]


class CommitEvidence(Evidence):
    expected_context: Key
    actual_context: Key
    context_committed_epoch: NonnegativeInt
    objects: Annotated[list[ChangedObject], Field(min_length=1)]
    setters: Annotated[list[Setter], Field(min_length=1)]
    updates: list[OwnUpdate]
    immediate_getters: dict[Key, Properties]
    save_epoch: NonnegativeInt
    sealed_sha256: Sha256
    reopens: Annotated[list[SavedProperties], Field(min_length=2, max_length=2)]


def _exact(value):
    # Prevent Python's False == 0 and True == 1 from hiding wrong getter types.
    return json.dumps(value, sort_keys=True, allow_nan=False)


def assess_object_commits(payload):
    """An ancestor's Update cannot commit a changed child's properties.

    Caller supplies real mutation/commit/save/readback observations. This function
    never launches CAD or establishes that reported events actually occurred.
    """
    try:
        e = CommitEvidence.model_validate(payload)
        expected = {obj.key: obj.expected for obj in e.objects}
        if len(expected) != len(e.objects) or any(not props for props in expected.values()):
            raise ValueError('Explicit unique changed-object keys and nonempty properties required')
        if e.actual_context != e.expected_context:
            raise ValueError('Editing context is not the explicitly committed current view')
        epochs = [s.epoch for s in e.setters] + [u.epoch for u in e.updates]
        if (len(epochs) != len(set(epochs)) or min(epochs) <= e.context_committed_epoch
                or max(epochs) >= e.save_epoch):
            raise ValueError('Each object mutation/commit must follow context and precede Save')
        actual_setters = {key: {} for key in expected}
        for setter in sorted(e.setters, key=lambda s: s.epoch):
            if setter.target not in expected or setter.property not in expected[setter.target]:
                raise ValueError('Setter outside explicit mutation scope')
            actual_setters[setter.target][setter.property] = setter.value
        if _exact(actual_setters) != _exact(expected):
            raise ValueError('Final setters do not match intended properties')
        if _exact(e.immediate_getters) != _exact(expected):
            raise ValueError('Immediate property readback differs')
        for key in expected:
            last_setter = max(s.epoch for s in e.setters if s.target == key)
            if not any(u.target == key and u.epoch > last_setter and u.returned is True for u in e.updates):
                raise ValueError(f'Missing own object Update after last setter: {key}')
        if len({r.open_id for r in e.reopens}) != 2:
            raise ValueError('Two distinct saved RO cycles required')
        if not e.save_epoch < e.reopens[0].epoch < e.reopens[1].epoch:
            raise ValueError('Save must precede ordered RO observations')
        for reopen in e.reopens:
            if (not reopen.read_only or reopen.artifact_sha256 != e.sealed_sha256
                    or _exact(reopen.objects) != _exact(expected)):
                raise ValueError('Saved object properties did not persist unchanged')
    except (ValueError, ValidationError) as exc:
        return _result([str(exc)])
    return _result([])
