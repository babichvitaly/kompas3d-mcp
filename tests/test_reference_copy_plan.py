import pytest

from kompas_mcp.reference_copy_plan import plan_reference_copies

FILES = {'models/owner.a3d': 'a'*64, 'parts/child.a3d': 'b'*64, 'leaf.m3d': 'c'*64}


def edge(parent, stored, target, files=FILES):
    return {'parent': parent, 'stored': stored, 'target': target,
            'parent_sha256': files[parent], 'target_sha256': files[target]}


def test_recursive_alias_copy_closes_paths_without_rewriting_or_native_claim():
    edges = [edge('models/owner.a3d', '../legacy/child.a3d', 'parts/child.a3d'),
             edge('parts/child.a3d', '../leaf.m3d', 'leaf.m3d')]
    p = plan_reference_copies(FILES, edges, prefix='payload')
    assert p['placements']['payload/legacy/child.a3d'] == {
        'origin': 'parts/child.a3d', 'sha256': 'b'*64}
    assert p['placements']['payload/leaf.m3d']['origin'] == 'leaf.m3d'
    assert len(p['placements']) == 4 and len(p['edges']) == 3
    assert p['cad_bytes_rewritten'] == 0 and p['native_acceptance'] == 'pending'
    assert p['portable_saved_verified'] is False


def test_ancestor_path_can_resolve_inside_an_explicit_payload_envelope():
    edges = [edge('models/owner.a3d', '../../legacy/child.a3d', 'parts/child.a3d')]
    p = plan_reference_copies(FILES, edges, prefix='payload')
    assert p['placements']['legacy/child.a3d']['origin'] == 'parts/child.a3d'


@pytest.mark.parametrize('stored', ['../../../outside.m3d', 'C:\\outside.m3d', 'C:relative.m3d',
                                   '\\root-relative.m3d', '/outside.m3d', 'library|object'])
def test_external_ambiguous_or_escaping_paths_fail(stored):
    with pytest.raises(ValueError):
        plan_reference_copies(FILES, [edge('models/owner.a3d', stored, 'leaf.m3d')], prefix='payload')


def test_different_canonical_origin_is_not_accepted_by_same_sha():
    files = {'owner.a3d': 'a'*64, 'one.m3d': 'b'*64, 'two.m3d': 'b'*64}
    edges = [edge('owner.a3d', 'one.m3d', 'two.m3d', files)]
    with pytest.raises(ValueError, match='same SHA is insufficient'):
        plan_reference_copies(files, edges, prefix='payload')


def test_hash_or_identity_pin_mismatch_is_not_guessed_by_filename():
    e = edge('models/owner.a3d', '../legacy/child.a3d', 'parts/child.a3d')
    e['target_sha256'] = 'd'*64
    with pytest.raises(ValueError, match='hashes'):
        plan_reference_copies(FILES, [e], prefix='payload')


def test_unbounded_alias_expansion_and_edge_counts_are_rejected():
    files = {'self.a3d': 'a'*64}
    e = edge('self.a3d', 'child/self.a3d', 'self.a3d', files)
    with pytest.raises(ValueError, match='file-placement bound'):
        plan_reference_copies(files, [e], prefix='payload', max_files=4)
    with pytest.raises(ValueError, match='edge bound'):
        plan_reference_copies(files, [e], prefix='payload', max_edges=2)


def test_finite_cycle_is_deduplicated_without_claiming_cad_support():
    files = {'A.a3d': 'a'*64, 'B.a3d': 'b'*64}
    edges = [edge('A.a3d', 'B.a3d', 'B.a3d', files), edge('B.a3d', 'A.a3d', 'A.a3d', files)]
    p = plan_reference_copies(files, edges, prefix='payload')
    assert len(p['placements']) == len(p['edges']) == 2
    assert p['native_acceptance'] == 'pending'


def test_file_directory_and_case_collisions_fail_before_staging():
    with pytest.raises(ValueError, match='collide'):
        plan_reference_copies({'A.m3d': 'a'*64, 'a.m3d': 'a'*64}, [], prefix='payload')
    with pytest.raises(ValueError, match='File/directory'):
        plan_reference_copies({'a': 'a'*64, 'a/file.m3d': 'b'*64}, [], prefix='payload')


@pytest.mark.parametrize('name', ['owner.a3d:stream', 'NUL.m3d', 'COM1.a3d', 'LPT².m3d',
                                'a*/file.m3d', 'model.m3d.', 'model.m3d '])
def test_windows_alias_device_and_stream_names_are_rejected(name):
    with pytest.raises(ValueError, match='Windows'):
        plan_reference_copies({name: 'a'*64}, [], prefix='payload')
