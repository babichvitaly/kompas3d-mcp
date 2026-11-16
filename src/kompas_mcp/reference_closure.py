"""RAM alias evidence is distinct from a saved native-reference closure."""

import ntpath
import posixpath
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated

from pydantic import Field, StrictBool

from .state_oracles import Evidence, Key, NonnegativeInt, _result
from .view_state import Finite, Sha256

Slot = Annotated[list[NonnegativeInt], Field(min_length=1)]


def path_key(value):
    windows = PureWindowsPath(value)
    if windows.is_absolute():
        if '..' in windows.parts:
            raise ValueError('Resolved Windows paths must be canonical, without parent traversal')
        return 'windows:' + str(windows).casefold()
    posix = PurePosixPath(value)
    if not posix.is_absolute() or '..' in posix.parts or '\\' in value:
        raise ValueError('Use explicit canonical absolute resolved paths')
    return 'posix:' + str(posix)


def _inside(path, root):
    p, r = path_key(path), path_key(root)
    separator = '\\' if p.startswith('windows:') else '/'
    return p == r or p.startswith(r.rstrip(separator) + separator)


def _stored_resolution(parent, raw):
    if PureWindowsPath(parent).is_absolute():
        # Drive-relative C:part and root-relative \\part are not a saved closure proof.
        p = PureWindowsPath(raw)
        if (p.drive or p.root) and not p.is_absolute():
            raise ValueError('Ambiguous saved Windows reference')
        return path_key(ntpath.normpath(ntpath.join(ntpath.dirname(parent), raw)))
    if '\\' in raw:
        raise ValueError('Foreign path syntax in a POSIX saved reference')
    return path_key(posixpath.normpath(posixpath.join(posixpath.dirname(parent), raw)))


class Alias(Evidence):
    path: Key
    sha256: Sha256


class LinkPlan(Evidence):
    slot: Slot
    destination: Key
    sha256: Sha256
    matrix: Annotated[list[Finite], Field(min_length=16, max_length=16)]
    ram_aliases: list[Alias]


class ClosurePlan(Evidence):
    owned_root: Key
    source_parent: Key
    parent_copy: Key
    bytecopy_sha256: Sha256
    immutable_sources: dict[Key, Sha256]
    semantics_sha256: Sha256
    links: Annotated[list[LinkPlan], Field(min_length=1)]
    direct_rebind_slots: list[Slot]


class ObservedLink(Evidence):
    slot: Slot
    parent_path: Key
    parent_sha256: Sha256
    raw_reference: Key
    resolved_path: Key
    sha256: Sha256
    matrix: Annotated[list[Finite], Field(min_length=16, max_length=16)]


class GraphSnapshot(Evidence):
    parent_path: Key
    parent_sha256: Sha256
    complete_scan: StrictBool
    semantics_sha256: Sha256
    immutable_source_hashes: dict[Key, Sha256]
    links: list[ObservedLink]


class SavedGraph(Evidence):
    open_id: Key
    read_only: StrictBool
    snapshot: GraphSnapshot


class SavedClosure(Evidence):
    ram_before_rebind: GraphSnapshot
    save_confirmed: StrictBool
    closed_after_save: StrictBool
    direct_rebind_slots: list[Slot]
    sealed_parent_sha256: Sha256
    cycles: Annotated[list[SavedGraph], Field(min_length=2, max_length=2)]


def _hashes(values):
    result = {path_key(path): sha for path, sha in values.items()}
    if len(result) != len(values):
        raise ValueError('Ambiguous canonical source-path identity')
    return result


def _plan(payload):
    p = ClosurePlan.model_validate(payload).model_copy(deep=True)
    originals = _hashes(p.immutable_sources)
    if (not _inside(p.parent_copy, p.owned_root) or path_key(p.parent_copy) in originals
            or originals.get(path_key(p.source_parent)) != p.bytecopy_sha256):
        raise ValueError('Parent must be an owned bytecopy of the pinned immutable source')
    links = {tuple(link.slot): link for link in p.links}
    if len(links) != len(p.links):
        raise ValueError('Ambiguous occurrence slot')
    for slot, link in links.items():
        if len(slot) > 1 and slot[:-1] not in links:
            raise ValueError('Closure plan omits a nested parent prefix')
        if not _inside(link.destination, p.owned_root) and originals.get(path_key(link.destination)) != link.sha256:
            raise ValueError('External canonical destinations must be explicitly immutable and SHA-pinned')
        ancestors = [p.parent_copy] + [links[slot[:i]].destination for i in range(1, len(slot))]
        if path_key(link.destination) in {path_key(a) for a in ancestors}:
            raise ValueError('Cyclic native reference graphs need a separate protocol')
        aliases = {path_key(a.path): a.sha256 for a in link.ram_aliases}
        if len(aliases) != len(link.ram_aliases):
            raise ValueError('Ambiguous RAM alias')
        if any(sha != link.sha256 or originals.get(path) != sha for path, sha in aliases.items()):
            raise ValueError('Every RAM alias requires independently pinned identical source bytes')
    direct = [tuple(slot) for slot in p.direct_rebind_slots]
    if len(direct) != len(set(direct)) or any(len(s) != 1 or s not in links for s in direct):
        raise ValueError('Only exact explicit direct references may be rebound')
    return p, links, originals


def _snapshot(p, links, originals, payload, saved, parent_sha):
    s = GraphSnapshot.model_validate(payload)
    if (not s.complete_scan or path_key(s.parent_path) != path_key(p.parent_copy)
            or s.parent_sha256 != parent_sha or s.semantics_sha256 != p.semantics_sha256
            or _hashes(s.immutable_source_hashes) != originals):
        raise ValueError('Incomplete graph, wrong parent bytes/semantics or changed original sources')
    observed = {tuple(link.slot): link for link in s.links}
    if observed.keys() != links.keys() or len(observed) != len(s.links):
        raise ValueError('Fresh graph must contain exactly all planned occurrence slots')
    alias_slots = []
    for slot, wanted in links.items():
        actual = observed[slot]
        if actual.sha256 != wanted.sha256 or actual.matrix != wanted.matrix:
            raise ValueError('Referenced file bytes or occurrence placement differs')
        parent = p.parent_copy if len(slot) == 1 else links[slot[:-1]].destination
        allowed_parents = {path_key(parent)}
        expected_parent_sha = parent_sha if len(slot) == 1 else links[slot[:-1]].sha256
        if not saved and len(slot) > 1:
            allowed_parents.update(path_key(a.path) for a in links[slot[:-1]].ram_aliases)
        if path_key(actual.parent_path) not in allowed_parents or actual.parent_sha256 != expected_parent_sha:
            raise ValueError('Native nested parent context/bytes differs')
        destination = path_key(wanted.destination)
        resolved = path_key(actual.resolved_path)
        if not saved and path_key(actual.parent_path) != path_key(parent):
            alias_slots.append(list(slot))
        if saved:
            if resolved != destination or _stored_resolution(parent, actual.raw_reference) != destination:
                raise ValueError('Saved RO reference still resolves/stores a legacy alias')
        elif resolved != destination:
            aliases = {path_key(a.path): a.sha256 for a in wanted.ram_aliases}
            if aliases.get(resolved) != actual.sha256:
                raise ValueError('Unproven RAM alias, even if display names or bytes look similar')
            if list(slot) not in alias_slots:
                alias_slots.append(list(slot))
    return alias_slots


def assess_ram_reference_aliases(plan, snapshot):
    try:
        p, links, originals = _plan(plan)
        aliases = _snapshot(p, links, originals, snapshot, False, p.bytecopy_sha256)
    except ValueError as exc:
        return _result([str(exc)])
    return {**_result([]), 'ram_alias_slots': aliases, 'persisted_closure_verified': False}


def assess_saved_reference_closure(plan, evidence):
    try:
        p, links, originals = _plan(plan)
        e = SavedClosure.model_validate(evidence)
        _snapshot(p, links, originals, e.ram_before_rebind, False, p.bytecopy_sha256)
        if (not e.save_confirmed or not e.closed_after_save
                or e.direct_rebind_slots != p.direct_rebind_slots
                or len({cycle.open_id for cycle in e.cycles}) != 2):
            raise ValueError('Exact direct rebind, Save/close and independent RO observations required')
        for cycle in e.cycles:
            if not cycle.read_only:
                raise ValueError('Fresh SavedRO required; RAM inspection is not persisted closure')
            _snapshot(p, links, originals, cycle.snapshot, True, e.sealed_parent_sha256)
    except ValueError as exc:
        return _result([str(exc)])
    return {**_result([]), 'persisted_paths_consistent_in_saved_evidence': True,
            'package_portability_verified': False}
